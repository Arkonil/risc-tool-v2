"""View model for the Data Explorer UI component.

Manages data source, target variable, and input variable selections,
and orchestrates the calculation of Information Value (IV) across sources.
"""

import pandas as pd
import polars as pl

from risc_tool.data.models.changes import ChangeTracker
from risc_tool.data.models.enums import (
    ComparisonOperation,
    PercentileOptions,
    Signature,
    VariableType,
)
from risc_tool.data.models.filter import Filter
from risc_tool.data.models.json_models import DataExplorerViewModelJSON
from risc_tool.data.models.outlier import OutlierRule
from risc_tool.data.models.types import ChangeIDs, DataSourceID, FilterID
from risc_tool.data.repositories.data import DataRepository
from risc_tool.data.repositories.filter import FilterRepository
from risc_tool.data.services.iv_calculation import calculate_iv


class DataExplorerViewModel(ChangeTracker):
    """View model managing the state and calculations for the Data Explorer page.

    Subscribes to DataRepository changes to keep selections synchronized.
    """

    @property
    def signature(self) -> Signature:
        """Get the component signature for change tracking.

        Returns:
            Signature.DATA_EXPLORER_VIEW_MODEL
        """
        return Signature.DATA_EXPLORER_VIEW_MODEL

    def __init__(
        self, data_repository: DataRepository, filter_repository: FilterRepository
    ) -> None:
        """Initialize the DataExplorerViewModel.

        Args:
            data_repository: The DataRepository dependency.
            filter_repository: The FilterRepository dependency.
        """
        super().__init__(dependencies=[data_repository, filter_repository])
        self.data_repository = data_repository
        self.filter_repository = filter_repository

        # Selections
        self.__iv_data_sources: list[DataSourceID] = []
        self.iv_current_target: str | None = None
        self.iv_current_variables: list[str] = []
        self.iv_current_filter_ids: list[FilterID] = []
        self.iv_remove_outliers: bool = True

        # Error and Warning Tracking
        self.iv_errors: list[Exception] = []
        self.iv_warnings: list[str] = []
        self.ol_errors: dict[FilterID, Exception] = {}

        # IV Cache: {(target_col, input_col, sorted_sources_tuple, filter_hash): iv_value}
        self.__iv_cache: dict[
            tuple[str, str, tuple[DataSourceID, ...], int], float
        ] = {}

        # Auto-initialize inputs
        self._update_iv_inputs()

    def _update_iv_inputs(self) -> None:
        """Synchronize selections with current repository state and clear cache."""
        self.logger.debug(
            "Syncing IV inputs: %d data sources, %d variables, %d filters",
            len(self.__iv_data_sources),
            len(self.iv_current_variables),
            len(self.iv_current_filter_ids),
        )
        # Remove selected sources that no longer exist
        self.__iv_data_sources = list(
            set(self.__iv_data_sources) & set(self.data_repository.data_sources)
        )

        # Reset target if it's no longer available
        if self.iv_current_target not in self.available_target_columns:
            self.iv_current_target = None

        # Filter out input variables that are no longer available
        self.iv_current_variables = list(
            set(self.iv_current_variables) & set(self.available_input_columns)
        )

        # Sync filter ids
        self.iv_current_filter_ids = list(
            set(self.iv_current_filter_ids) & set(self.filter_repository.filters.keys())
        )

        # Prune outlier errors
        all_filter_ids = self.filter_repository.filters.keys()
        self.ol_errors = {
            k: v
            for k, v in self.ol_errors.items()
            if k in all_filter_ids or k == FilterID.TEMPORARY
        }

        # Invalidate cache and clear messages
        self.__iv_cache.clear()
        self.iv_errors.clear()
        self.iv_warnings.clear()

    def on_dependency_update(self, change_ids: ChangeIDs) -> None:
        """Handle updates from DataRepository or FilterRepository.

        Args:
            change_ids: Set of change IDs from the dependency.
        """
        self._update_iv_inputs()

    # Common Properties for Data Explorer
    @property
    def data_loaded(self) -> bool:
        """Check if any data sources are successfully loaded and configured.

        Returns:
            True if at least one data source has a schema, False otherwise.
        """
        return self.data_repository.has_valid_sources

    @property
    def all_data_source_ids(self) -> list[DataSourceID]:
        """Get all available data source IDs in the repository.

        Returns:
            List of DataSourceIDs.
        """
        return list(self.data_repository.data_sources.keys())

    def get_data_source_label(self, data_source_id: DataSourceID) -> str:
        """Get the label for a specific data source.

        Args:
            data_source_id: The ID of the data source.

        Returns:
            The human-readable label of the data source.
        """
        if data_source_id in self.data_repository.data_sources:
            return self.data_repository.data_sources[data_source_id].label
        return str(data_source_id)

    @property
    def common_columns(self):
        return self.data_repository.common_columns()

    @property
    def all_filters(self) -> dict[FilterID, Filter]:
        """Get user defined filters (excluding outliers)."""
        return self.filter_repository.get_filters(outliers=False)

    # IV Calculation Properties
    @property
    def iv_data_sources(self):
        return self.__iv_data_sources

    @iv_data_sources.setter
    def iv_data_sources(self, value: list[DataSourceID]):
        self.__iv_data_sources = value

        self._update_iv_inputs()

    @property
    def available_target_columns(self) -> list[str]:
        """Get columns available to be selected as the target variable.

        Restricts targets to numerical and boolean columns.

        Returns:
            List of column names.
        """
        if not self.data_loaded or not self.__iv_data_sources:
            return []

        common_cols: set[tuple[str, VariableType]] = (
            self.data_repository.common_columns(self.__iv_data_sources)
        )

        targets: list[str] = []
        for col, _ in common_cols:
            dtype = self.data_repository.data_config.schema[col]
            if dtype.is_numeric() or isinstance(dtype, pl.Boolean):
                targets.append(col)

        return sorted(targets)

    @property
    def available_input_columns(self) -> list[str]:
        """Get all columns available in the intersection of selected data sources.

        Returns:
            List of column names.
        """
        if not self.data_loaded or not self.__iv_data_sources:
            return []

        common_cols = self.data_repository.common_columns(self.__iv_data_sources)
        return sorted([col for col, _ in common_cols])

    def get_iv_df(
        self,
        target_variable: str | None,
        input_variables: list[str],
        filter_ids: list[FilterID] | None = None,
        remove_outliers: bool = False,
    ) -> pl.DataFrame | None:
        """Calculate and return Information Value (IV) for input variables.

        Loads and combines selected data sources using Polars, then runs IV calculations.

        Args:
            target_variable: The binary target variable name.
            input_variables: List of independent variable names.
            filter_ids: Optional list of active Filters to apply.
            remove_outliers: Optional outlier removal flag.

        Returns:
            A Polars DataFrame with columns ['variable', 'iv'] sorted by iv desc,
            or None if no calculation was performed.
        """
        self.iv_errors.clear()
        self.iv_warnings.clear()

        if target_variable is None or not input_variables:
            self.logger.debug("IV calculation skipped: missing target or inputs")
            self.iv_warnings.append(
                "Please select a target variable and at least one input variable to calculate IV."
            )
            return None

        if not self.data_loaded:
            self.logger.warning("IV calculation skipped: no valid data sources")
            self.iv_errors.append(
                ValueError("No valid data sources loaded. Please import data first.")
            )
            return None

        if not self.__iv_data_sources:
            self.logger.debug("IV calculation skipped: no data sources selected")
            self.iv_errors.append(ValueError("Please select at least one data source."))
            return None

        # Check target variable validity
        available_targets = self.available_target_columns
        if target_variable not in available_targets:
            self.iv_errors.append(
                ValueError(
                    f"Target variable `{target_variable}` is not found in the selected data sources or is not binary."
                )
            )
            return None

        # Filter valid input columns
        available_inputs: list[str] = self.available_input_columns
        input_cols_available: list[str] = []
        for input_col in input_variables:
            if input_col not in available_inputs:
                self.iv_errors.append(
                    ValueError(
                        f"Variable `{input_col}` is not found in at least one of the selected data sources."
                    )
                )
            else:
                input_cols_available.append(input_col)

        if not input_cols_available:
            self.iv_errors.append(
                ValueError(
                    "Please select at least one valid input variable to calculate IV."
                )
            )
            return None

        filter_ids_available: list[FilterID] = []
        if filter_ids:
            for fid in filter_ids:
                if fid not in self.filter_repository.filters:
                    self.iv_errors.append(ValueError(f"Filter `{fid}` is not found."))
                else:
                    filter_ids_available.append(fid)

        # Retrieve combined filter expression
        combined_expr = self.filter_repository.get_combined_expression(
            filter_ids_available, remove_outliers=remove_outliers
        )

        # Hash filter expression config for caching
        filter_hash = hash(str(combined_expr)) if combined_expr is not None else 0

        sources_key = tuple(sorted(self.__iv_data_sources))
        iv_records: list[dict[str, str | float]] = []

        try:
            unified_lf = self.data_repository.get_lazyframe(self.__iv_data_sources)
            if combined_expr is not None:
                unified_lf = unified_lf.filter(combined_expr)

            height: int = unified_lf.select(pl.len()).collect().item()
            if height == 0:
                self.logger.warning(
                    "Filter criteria left no records available for IV analysis"
                )
                self.iv_warnings.append(
                    "The filter criteria left no records available for analysis."
                )
                return None

        except (
            FileNotFoundError,
            KeyError,
            TypeError,
            ValueError,
            pl.exceptions.PolarsError,
        ) as error:
            self.logger.error("Failed to load/concatenate data: %s", error)
            self.iv_errors.append(
                ValueError(f"Failed to load data for IV calculation: {error}")
            )
            return None

        # Validate target is binary (0 or 1)
        target_series = unified_lf.select(target_variable).collect().to_series()
        if target_series.dtype == pl.Boolean:
            unique_targets = target_series.cast(pl.Int8).drop_nulls().unique().to_list()
        else:
            unique_targets = target_series.drop_nulls().unique().to_list()

        if not set(unique_targets).issubset({0, 1}):
            self.logger.warning(
                "Target '%s' is not binary; found values: %s",
                target_variable,
                unique_targets,
            )
            self.iv_errors.append(
                ValueError(
                    f"Target variable must be binary (0 or 1).\n\n"
                    f"Following values were found: {unique_targets}"
                )
            )
            return None

        # Calculate IV for each variable
        for input_col in input_cols_available:
            try:
                cache_key = (target_variable, input_col, sources_key, filter_hash)
                if cache_key in self.__iv_cache:
                    iv = self.__iv_cache[cache_key]
                else:
                    var_series = unified_lf.select(input_col).collect().to_series()

                    # Warn if categorical column has more than 10 unique values
                    if (
                        not var_series.dtype.is_numeric()
                        and var_series.drop_nulls().n_unique() > 10
                    ):
                        self.iv_warnings.append(
                            f"Variable `{input_col}` is not numerical and has more than 10 unique values. "
                            f"Total unique values: {var_series.drop_nulls().n_unique()}"
                        )
                        continue

                    iv = calculate_iv(var_series, target_series)
                    self.__iv_cache[cache_key] = iv

                iv_records.append({"variable": input_col, "iv": iv})

            except (
                AttributeError,
                KeyError,
                TypeError,
                ValueError,
                pl.exceptions.PolarsError,
            ) as error:
                self.logger.error("Error calculating IV for %s: %s", input_col, error)
                self.iv_errors.append(error)

        if not iv_records:
            self.logger.warning(
                "No IV records computed (all variables failed or were skipped)"
            )
            return None

        self.logger.info("IV computed for %d variables", len(iv_records))
        # Return sorted Polars DataFrame
        return pl.DataFrame(iv_records).sort("iv", descending=True)

    # Outlier Rule Properties
    @property
    def current_outlier_rules(self) -> list[OutlierRule]:
        """Get all currently registered outlier rules."""
        return [
            r
            for r in self.filter_repository.filters.values()
            if isinstance(r, OutlierRule)
        ]

    @property
    def total_outlier_count(self) -> int:
        """Calculate the total outlier instances count across unified valid data sources."""
        if not self.data_repository.has_valid_sources:
            return 0

        lf = self.data_repository.get_lazyframe()

        combined_outliers_expr = self.filter_repository.get_combined_expression(
            filter_ids=[], remove_outliers=True
        )
        if combined_outliers_expr is None:
            return 0

        try:
            freq_df = lf.select(
                (~combined_outliers_expr).sum().alias("outliers_count")
            ).collect()
            return freq_df.item(0, 0) if freq_df.height > 0 else 0
        except Exception:
            self.logger.exception("Failed to compute total outlier count")
            return 0

    def get_boxplot_data(
        self, variable_name: str
    ) -> tuple[pl.DataFrame, pl.DataFrame] | tuple[None, None]:
        """Get data for boxplot visualization of a variable across selected sources.

        Args:
            variable_name: The name of the variable to visualize.
            quantiles: List of quantiles to compute (e.g., [0.25, 0.5, 0.75]).

        Returns:
            A tuple containing two Polars DataFrames: the first for the boxplot data and the second for the quantile data, or None if the variable is not found.
        """
        if not self.data_loaded:
            return None, None

        common_cols = self.data_repository.common_columns()
        if not any(
            col == variable_name and dtype == VariableType.NUMERICAL
            for col, dtype in common_cols
        ):
            return None, None

        try:
            lf = self.data_repository.get_lazyframe().select([variable_name])
            boxplot_df = lf.select(pl.col(variable_name).alias("Value")).collect()

            stats_df = lf.select(
                pl.col(variable_name).mode().cast(pl.Float64).head(1).alias("mode"),
                pl.col(variable_name).skew().cast(pl.Float64).head(1).alias("skew"),
            ).collect()

            mode: float | None = (
                stats_df.item(0, "mode") if stats_df.height > 0 else None
            )
            skew: float | None = (
                stats_df.item(0, "skew") if stats_df.height > 0 else None
            )

            if isinstance(skew, (int, float)) and skew > 0.1:
                quantiles = [0.25, 0.5, 0.75, 0.9, 0.95, 0.99]
            elif isinstance(skew, (int, float)) and skew < -0.1:
                quantiles = [0.01, 0.05, 0.1, 0.25, 0.5, 0.75]
            else:
                quantiles = [0.01, 0.05, 0.1, 0.25, 0.5, 0.75, 0.9, 0.95, 0.99]

            perc_df = (
                lf
                .filter(
                    pl.col(variable_name).is_not_null()
                    & (pl.col(variable_name) != mode)
                )
                .select(
                    pl
                    .col(variable_name)
                    .quantile(quantiles, interpolation="linear")
                    .explode()
                    .alias("Value"),
                    pl
                    .lit(quantiles)
                    .explode()
                    .map_elements(lambda q: f"{q * 100}%", return_dtype=pl.Utf8)
                    .alias("Percentile"),
                )
                .with_columns(
                    pl
                    .col("Value")
                    .map_elements(lambda v: f"{v:.2f}", return_dtype=pl.Utf8)
                    .alias("Value_Str")
                )
                .collect()
            )

            return boxplot_df, perc_df
        except Exception:
            self.logger.exception(
                "Failed to retrieve boxplot data for variable '%s'", variable_name
            )
            return None, None

    def get_quantile_table(
        self, variable_name: str, quantiles: list[float]
    ) -> pd.DataFrame | None:
        """Get a table of specified quantiles for a variable across selected sources.

        Args:
            variable_name: The name of the variable to analyze.
            quantiles: List of quantiles to compute (e.g., [0.25, 0.5, 0.75]).

        Returns:
            A Polars DataFrame containing the specified quantiles for the variable, or None if an error occurs.
        """
        if not self.data_loaded:
            return None

        common_cols = self.data_repository.common_columns()
        if not any(
            col == variable_name and dtype == VariableType.NUMERICAL
            for col, dtype in common_cols
        ):
            return None

        try:
            lf = self.data_repository.get_lazyframe().select([variable_name])

            mode = (
                lf
                .select(
                    pl.col(variable_name).mode().cast(pl.Float64).head(1).alias("mode"),
                )
                .collect()
                .item(0, "mode")
            )
            mode: float | None = mode if mode is not None else None

            quantile_df = (
                lf
                .filter(
                    pl.col(variable_name).is_not_null()
                    & (pl.col(variable_name) != mode)
                )
                .select(
                    pl
                    .col(variable_name)
                    .quantile(quantiles, interpolation="linear")
                    .explode()
                    .alias("Value"),
                    pl
                    .lit(quantiles)
                    .explode()
                    .map_elements(
                        lambda q: f"{q * 100:.0f}th Percentile", return_dtype=pl.Utf8
                    )
                    .alias("Percentile"),
                )
                .collect()
                .to_pandas()
                .set_index("Percentile")
                .T.rename_axis(index="Percentile")
            )
            return quantile_df
        except Exception:
            self.logger.exception(
                "Failed to retrieve quantile table for variable '%s'", variable_name
            )
            return None

    def validate_outlier(
        self,
        outlier_id: FilterID,
        variable_name: str,
        comparison_op: ComparisonOperation,
        comparison_base: PercentileOptions | str,
    ) -> OutlierRule:
        if variable_name == "":
            self.logger.warning("Outlier validation failed: empty variable name")
            raise ValueError("Variable name cannot be empty.")

        comparison_base_f: PercentileOptions | float
        if isinstance(comparison_base, PercentileOptions):
            comparison_base_f = comparison_base
        else:
            try:
                comparison_base_f = float(comparison_base)
            except ValueError:
                self.logger.warning(
                    "Invalid comparison_base for outlier: %s", comparison_base
                )
                raise ValueError(
                    f"comparison_base is neither a PercentileEnum nor a float: {comparison_base}"
                )

        outlier_cache = self.filter_repository.validate_outlier_rule(
            variable_name, comparison_op, comparison_base_f
        )
        outlier_cache.uid = outlier_id
        return outlier_cache

    def save_outlier(
        self,
        outlier_id: FilterID,
        variable_name: str,
        comparison_op: ComparisonOperation,
        comparison_base: PercentileOptions | str,
    ) -> None:
        self.logger.info(
            "Request to save outlier rule ID %s for variable '%s'",
            outlier_id,
            variable_name,
        )
        try:
            validated_outlier_rule = self.validate_outlier(
                outlier_id, variable_name, comparison_op, comparison_base
            )
        except Exception as e:
            self.logger.exception("Failed to save outlier rule ID %s", outlier_id)
            self.ol_errors[outlier_id] = e
            return

        if outlier_id == FilterID.TEMPORARY:
            self.filter_repository.create_outlier_rule(
                variable_name=validated_outlier_rule.variable_name,
                comparison_op=validated_outlier_rule.comparison_op,
                comparison_base=validated_outlier_rule.comparison_base,
            )
        else:
            self.filter_repository.modify_outlier_rule(
                filter_id=outlier_id,
                variable_name=validated_outlier_rule.variable_name,
                comparison_op=validated_outlier_rule.comparison_op,
                comparison_base=validated_outlier_rule.comparison_base,
            )

        self.logger.info(
            "Outlier rule saved for '%s' with op=%s, base=%s",
            variable_name,
            comparison_op,
            comparison_base,
        )
        if outlier_id in self.ol_errors:
            del self.ol_errors[outlier_id]

    def delete_outlier_rule(self, outlier_id: FilterID) -> None:
        self.logger.info("Request to delete outlier rule ID %s", outlier_id)
        self.filter_repository.remove_filter(outlier_id)

    def to_dict(self) -> DataExplorerViewModelJSON:
        """Serialize DataExplorerViewModel state to DataExplorerViewModelJSON Pydantic model."""
        return DataExplorerViewModelJSON(
            iv_data_sources=self.__iv_data_sources,
            iv_current_target=self.iv_current_target,
            iv_current_variables=self.iv_current_variables,
            iv_current_filter_ids=self.iv_current_filter_ids,
            iv_remove_outliers=self.iv_remove_outliers,
        )

    @classmethod
    def from_dict(
        cls,
        data: DataExplorerViewModelJSON,
        data_repository: DataRepository,
        filter_repository: FilterRepository,
    ) -> "DataExplorerViewModel":
        """Reconstruct DataExplorerViewModel from DataExplorerViewModelJSON Pydantic model or dict."""
        vm = cls(
            data_repository=data_repository,
            filter_repository=filter_repository,
        )

        vm.iv_current_filter_ids = data.iv_current_filter_ids
        vm.__iv_data_sources = data.iv_data_sources
        vm.iv_current_target = data.iv_current_target
        vm.iv_current_variables = data.iv_current_variables
        vm.iv_remove_outliers = data.iv_remove_outliers

        return vm

    @classmethod
    def validate_json(
        cls, data_repository: DataRepository, data: DataExplorerViewModelJSON
    ) -> list[str]:
        """Return variables referenced in the JSON that are missing from the data schema."""
        available_columns = {col for col, _ in data_repository.common_columns()}
        variables = set(data.iv_current_variables)
        if data.iv_current_target is not None:
            variables.add(data.iv_current_target)

        missing = sorted(v for v in variables if v not in available_columns)
        return missing
