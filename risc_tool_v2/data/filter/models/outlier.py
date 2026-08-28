"""Outlier rule model extending Filter with statistical threshold calculation."""

import logging
import re
import typing as t
from uuid import NAMESPACE_URL, uuid5

import polars as pl
from pydantic import ConfigDict, PrivateAttr, model_validator

from risc_tool_v2.data.core.enums import ComparisonOperation, PercentileOptions
from risc_tool_v2.data.core.uid import FilterID
from risc_tool_v2.data.core.utils.logging import get_logger
from risc_tool_v2.data.filter.models.filter import Filter

if t.TYPE_CHECKING:
    from risc_tool_v2.data.filter.json.filter_json import FilterJSON


class OutlierRule(Filter):
    model_config = ConfigDict(extra="forbid", frozen=True)

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
        if not self.name:
            object.__setattr__(self, "name", self._display_name())

        if self.uid is FilterID.UNSET:
            object.__setattr__(self, "uid", self.create_hash())
        return self

    def _display_name(self) -> str:
        if isinstance(self.comparison_base, PercentileOptions):
            base_str = PercentileOptions.format_perc(str(self.comparison_base))
        else:
            base_str = str(self.comparison_base)
        return f"{self.variable_name} {self.comparison_op.value} {base_str}"

    def create_hash(self) -> FilterID:
        payload = (
            f"{self.variable_name}|{self.comparison_op.value}|{self.comparison_base}"
        )
        return FilterID(uuid5(NAMESPACE_URL, payload))

    @property
    def mode(self) -> float | int | None:
        return self._mode

    @property
    def threshold_val(self) -> float | int | None:
        return self._threshold_val

    @property
    def frequency(self) -> int:
        return self._frequency

    @property
    def is_outlier(self) -> bool:
        return True

    def recalculate_thresholds(self, lf: pl.LazyFrame) -> None:
        self._logger.info(
            "Recalculating outlier thresholds for variable '%s' (base=%s)",
            self.variable_name,
            self.comparison_base,
        )
        col_expr = pl.col(self.variable_name)

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

        if isinstance(self.comparison_base, PercentileOptions):
            try:
                lf_filtered = lf.select(col_expr).drop_nulls()
                if mode is not None:
                    lf_filtered = lf_filtered.filter(col_expr != mode)

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

        if mode is not None:
            query = f"~((`{self.variable_name}` {self.comparison_op.value} {threshold_val}) & (`{self.variable_name}` != {mode}) & (`{self.variable_name}`.notna()))"
        else:
            query = f"~((`{self.variable_name}` {self.comparison_op.value} {threshold_val}) & (`{self.variable_name}`.notna()))"

        object.__setattr__(self, "query", query)

        self.validate_query()

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

    def to_dict(self) -> "FilterJSON":
        from risc_tool_v2.data.filter.json.filter_json import FilterJSON

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
    def from_dict(cls, data: "FilterJSON") -> "OutlierRule":
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
