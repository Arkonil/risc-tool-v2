import re
import typing as t

import polars as pl

from risc_tool.data.models.enums import ComparisonOperation, PercentileOptions
from risc_tool.data.models.filter import Filter
from risc_tool.data.models.types import FilterID
from risc_tool.utils.logging import get_logger


class OutlierRule(Filter):
    """Filter subclass representing outlier handling rules calculated using Polars."""

    def __init__(
        self,
        uid: FilterID,
        variable_name: str,
        comparison_op: ComparisonOperation,
        comparison_base: PercentileOptions | float,
    ) -> None:
        super().__init__(uid, "", "")
        self.logger = get_logger(self.__class__.__name__)
        self.variable_name: str = variable_name
        self.comparison_op: ComparisonOperation = comparison_op
        self.comparison_base: PercentileOptions | float = comparison_base

        self.mode: t.Union[float, int, None] = None
        self.threshold_val: t.Union[float, int, None] = None
        self.frequency: int = 0

        # Set default name
        if isinstance(comparison_base, PercentileOptions):
            self.name = f"{variable_name} {comparison_op.value} {PercentileOptions.format_perc(comparison_base.value)}"
        else:
            self.name = f"{variable_name} {comparison_op.value} {comparison_base}"

    def recalculate_thresholds(self, lf: pl.LazyFrame) -> None:
        """Run aggregation queries on the LazyFrame to calculate mode and thresholds."""
        self.logger.info(
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
        except Exception as e:
            self.logger.error("Failed to compute mode: %s", e)
            mode = None

        self.mode = mode

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
            except Exception as e:
                self.logger.error("Failed to compute percentile quantile: %s", e)
                threshold_val = 0.0

            # Update name based on resolved percentile value
            self.name = f"{self.variable_name} {self.comparison_op.value} {PercentileOptions.format_perc(str(self.comparison_base))}"
        else:
            threshold_val = float(self.comparison_base)
            self.name = f"{self.variable_name} {self.comparison_op.value} {self.comparison_base}"

        self.threshold_val = threshold_val

        # 3. Build Query String
        if mode is not None:
            self.query = f"~((`{self.variable_name}` {self.comparison_op.value} {threshold_val}) & (`{self.variable_name}` != {mode}) & (`{self.variable_name}`.notna()))"
        else:
            self.query = f"~((`{self.variable_name}` {self.comparison_op.value} {threshold_val}) & (`{self.variable_name}`.notna()))"

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
            self.frequency = freq_df.item(0, 0) if freq_df.height > 0 else 0
        except Exception as e:
            self.logger.error("Failed to compute outlier count (frequency): %s", e)
            self.frequency = 0

    def duplicate(
        self, uid: FilterID | None = None, name: str | None = None
    ) -> "OutlierRule":
        if uid is None:
            uid = self.uid
        if name is None:
            name = self.name

        new_instance = OutlierRule(
            uid=uid,
            variable_name=self.variable_name,
            comparison_op=self.comparison_op,
            comparison_base=self.comparison_base,
        )
        new_instance.mode = self.mode
        new_instance.threshold_val = self.threshold_val
        new_instance.frequency = self.frequency
        new_instance.query = self.query
        new_instance.filter_expr = self.filter_expr
        new_instance.used_columns = list(self.used_columns)
        return new_instance

    def to_dict(self) -> dict[str, t.Any]:
        return {
            "uid": int(self.uid),
            "name": self.name,
            "query": self.query,
            "used_columns": self.used_columns,
            "variable_name": self.variable_name,
            "comparison_op": self.comparison_op,
            "comparison_base": self.comparison_base,
            "is_outlier": True,
        }


__all__ = ["OutlierRule"]
