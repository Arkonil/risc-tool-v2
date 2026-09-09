"""Outlier rule model extending Filter with statistical threshold calculation.

OutlierRule is a frozen Filter subclass that flags rows falling outside
computed mode/percentile thresholds for a numeric column. Its identity is
content-addressed from the rule parameters (variable_name, comparison_op,
comparison_base) only — the data-dependent query and statistics recomputed
by :meth:`recalculate_thresholds` never affect the ID.
"""

import logging
import re
from uuid import NAMESPACE_URL, uuid5

import polars as pl
from pydantic import ConfigDict, PrivateAttr, model_validator

from risc_tool.data.models.enums import ComparisonOperation, PercentileOptions
from risc_tool.data.models.filter import Filter
from risc_tool.data.models.json_models import FilterJSON
from risc_tool.data.models.uid import FilterID
from risc_tool.utils.logging import get_logger


class OutlierRule(Filter):
    """Filter subclass representing outlier handling rules calculated using Polars.

    Attributes:
        uid: Content-addressed unique identifier derived from the rule parameters.
        name: Human-readable name derived from the rule parameters.
        query: The raw outlier expression string (rebuilt on recalculation).
        variable_name: The numeric column the rule applies to.
        comparison_op: Comparison operator used to flag outliers.
        comparison_base: The percentile option or fixed threshold value.
        mode: Most frequent value of the column (computed).
        threshold_val: Resolved percentile/fixed threshold (computed).
        frequency: Number of rows flagged as outliers (computed).
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    # Name/query are recomputed from parameters; they default to empty and
    # are filled in by the validators below / recalculate_thresholds.
    name: str = ""
    query: str = ""

    variable_name: str
    comparison_op: ComparisonOperation
    comparison_base: PercentileOptions | float

    _mode: float | int | None = PrivateAttr(default=None)
    _threshold_val: float | int | None = PrivateAttr(default=None)
    _frequency: int = PrivateAttr(default=0)
    _logger: logging.Logger = PrivateAttr(
        default_factory=lambda: get_logger("OutlierRule")
    )

    @model_validator(mode="after")
    def _derive_uid_and_name(self) -> "OutlierRule":
        """Derive the display name and parameter-hashed uid when unset.

        The display name is deterministic from the rule parameters; it is
        filled in whenever left empty so deserialized names survive. Passing
        UNSET explicitly behaves like omission for the uid.

        Returns:
            This instance with name/uid derived when not provided.
        """
        if not self.name:
            # Frozen model: bypass immutability to fill in the derived name.
            object.__setattr__(self, "name", self._display_name())

        if self.uid is FilterID.UNSET:
            object.__setattr__(self, "uid", self.create_hash())
        return self

    def _display_name(self) -> str:
        """Build the human-readable rule name from its parameters.

        Returns:
            A name of the form ``"<column> <op> <base>"`` with percentiles
            formatted via :meth:`PercentileOptions.format_perc`.
        """
        if isinstance(self.comparison_base, PercentileOptions):
            base_str = PercentileOptions.format_perc(str(self.comparison_base))
        else:
            base_str = str(self.comparison_base)
        return f"{self.variable_name} {self.comparison_op.value} {base_str}"

    def create_hash(self) -> FilterID:
        """Return a content-addressed FilterID derived from the rule parameters.

        Only (variable_name, comparison_op, comparison_base) participate in
        the hash: the recomputed query embeds data-dependent thresholds and
        must not change the identity when the underlying data changes.

        Returns:
            A FilterID whose value is a UUIDv5 hash of the parameters.
        """
        payload = (
            f"{self.variable_name}|{self.comparison_op.value}|"
            f"{self.comparison_base}"
        )
        return FilterID(uuid5(NAMESPACE_URL, payload))

    @property
    def mode(self) -> float | int | None:
        """Get the computed most frequent value of the column."""
        return self._mode

    @property
    def threshold_val(self) -> float | int | None:
        """Get the computed percentile/fixed threshold value."""
        return self._threshold_val

    @property
    def frequency(self) -> int:
        """Get the computed count of rows flagged as outliers."""
        return self._frequency

    def recalculate_thresholds(self, lf: pl.LazyFrame) -> None:
        """Run aggregation queries on the LazyFrame to calculate mode and thresholds.

        Computes the mode (most frequent value) and the threshold value
        (percentile or fixed number) from the data, builds a query string
        that flags rows as outliers, compiles it into a Polars expression,
        and counts the number of outlier rows.

        Args:
            lf: A Polars LazyFrame containing the variable column.
        """
        self._logger.info(
            "Recalculating outlier thresholds for variable '%s' (base=%s)",
            self.variable_name,
            self.comparison_base,
        )
        col_expr = pl.col(self.variable_name)

        # 1. Compute Mode
        try:
            mode_df = (
                lf
                .select(col_expr)
                .drop_nulls()
                .group_by(self.variable_name)
                .len()
                .sort("len", descending=True)
                .limit(1)
                .collect()
            )
            mode = mode_df.item(0, 0) if mode_df.height > 0 else None
        except Exception:
            self._logger.exception("Failed to compute mode")
            mode = None

        self._mode = mode

        # 2. Compute Threshold
        if isinstance(self.comparison_base, PercentileOptions):
            try:
                lf_filtered = lf.select(col_expr).drop_nulls()
                if mode is not None:
                    lf_filtered = lf_filtered.filter(col_expr != mode)

                # Parse percentile value
                m = re.match(r"PERC_(\d+)", self.comparison_base.value)
                if not m:
                    raise ValueError(
                        f"Invalid PercentileOption format: {self.comparison_base.value}"
                    )
                perc_val = float(m.group(1)) / 100.0

                q_df = lf_filtered.select(
                    col_expr.quantile(perc_val, interpolation="linear")
                ).collect()
                threshold_val = q_df.item(0, 0) if q_df.height > 0 else 0.0
            except Exception:
                self._logger.exception("Failed to compute percentile quantile")
                threshold_val = 0.0
        else:
            threshold_val = float(self.comparison_base)

        self._threshold_val = threshold_val

        # 3. Build Query String
        if mode is not None:
            query = f"~((`{self.variable_name}` {self.comparison_op.value} {threshold_val}) & (`{self.variable_name}` != {mode}) & (`{self.variable_name}`.notna()))"
        else:
            query = f"~((`{self.variable_name}` {self.comparison_op.value} {threshold_val}) & (`{self.variable_name}`.notna()))"

        # Frozen field: bypass immutability for the recomputed query.
        object.__setattr__(self, "query", query)

        # 4. Validate and compile the query expression
        self.validate_query()

        # 5. Compute Frequency (count of outliers)
        try:
            assert self.filter_expr is not None, (
                "Filter expression must be compiled before computing frequency."
            )
            freq_df = lf.select(
                (~self.filter_expr).sum().alias("outlier_count")
            ).collect()
            self._frequency = freq_df.item(0, 0) if freq_df.height > 0 else 0
        except Exception:
            self._logger.exception("Failed to compute outlier count (frequency)")
            self._frequency = 0

    def duplicate(
        self, uid: FilterID | None = None, name: str | None = None
    ) -> "OutlierRule":
        """Create a deep copy of this outlier rule with optional new ID and name.

        Computed state (mode, threshold, frequency) and the compiled
        expression are carried over without recalculation.

        Args:
            uid: Explicit FilterID for the copy. When omitted, the copy
                derives its content hash from the rule parameters.
            name: New name for the copy. Defaults to this rule's name;
                leaving it empty re-derives the parameter-based display name.

        Returns:
            A new OutlierRule instance with the same configuration and
            computed values (mode, threshold, frequency, query, expression).
        """
        new_instance = OutlierRule(
            **({"uid": uid} if uid is not None else {}),
            name=self.name if name is None else name,
            variable_name=self.variable_name,
            comparison_op=self.comparison_op,
            comparison_base=self.comparison_base,
            query=self.query,
        )
        new_instance._mode = self.mode
        new_instance._threshold_val = self.threshold_val
        new_instance._frequency = self.frequency
        new_instance._used_columns = list(self.used_columns)
        new_instance._filter_expr = self.filter_expr
        return new_instance

    def to_dict(self) -> FilterJSON:
        """Serialize the outlier rule to a dictionary for storage or export.

        Returns:
            A FilterJSON with uid, name, query, used_columns, variable_name,
            comparison_op, comparison_base, and is_outlier flag.
        """
        return FilterJSON(
            uid=self.uid,
            name=self.name,
            query=self.query,
            used_columns=self.used_columns,
            variable_name=self.variable_name,
            comparison_op=self.comparison_op,
            comparison_base=self.comparison_base,
            is_outlier=True,
        )

    @classmethod
    def from_dict(cls, data: FilterJSON) -> "OutlierRule":
        """Create an OutlierRule instance from a FilterJSON object.

        Args:
            data: A FilterJSON object containing the outlier rule's properties.

        Returns:
            An OutlierRule instance initialized with the provided data.
        """

        assert data.is_outlier, "FilterJSON must represent an outlier rule"
        assert data.variable_name is not None, "FilterJSON must have a variable_name"
        assert data.comparison_op is not None, "FilterJSON must have a comparison_op"
        assert data.comparison_base is not None, (
            "FilterJSON must have a comparison_base"
        )

        return cls(
            uid=data.uid,
            name=data.name,
            variable_name=data.variable_name,
            comparison_op=data.comparison_op,
            comparison_base=data.comparison_base,
        )


__all__ = ["OutlierRule"]
