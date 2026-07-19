"""View model for the Data Explorer UI component.

Manages data source, target variable, and input variable selections,
and orchestrates the calculation of Information Value (IV) across sources.
"""

import polars as pl

from risc_tool.data.models.changes import ChangeTracker
from risc_tool.data.models.enums import Signature, VariableType
from risc_tool.data.models.types import ChangeIDs, DataSourceID
from risc_tool.data.repositories.data import DataRepository
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

    def __init__(self, data_repository: DataRepository) -> None:
        """Initialize the DataExplorerViewModel.

        Args:
            data_repository: The DataRepository dependency.
        """
        super().__init__(dependencies=[data_repository])
        self.data_repository = data_repository

        # Selections
        self.iv_data_sources: list[DataSourceID] = []
        self.iv_current_target: str | None = None
        self.iv_current_variables: list[str] = []

        # Error and Warning Tracking
        self.iv_errors: list[Exception] = []
        self.iv_warnings: list[str] = []

        # IV Cache: {(target_col, input_col, sorted_sources_tuple): iv_value}
        self.__iv_cache: dict[tuple[str, str, tuple[DataSourceID, ...]], float] = {}

        # Auto-initialize inputs
        self._update_iv_inputs()

    @property
    def has_valid_sources(self) -> bool:
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
    def available_target_columns(self) -> list[str]:
        """Get columns available to be selected as the target variable.

        Restricts targets to numerical and boolean columns.

        Returns:
            List of column names.
        """
        if not self.has_valid_sources or not self.iv_data_sources:
            return []

        common_cols: set[tuple[str, VariableType]] = (
            self.data_repository.data_config.available_columns(self.iv_data_sources)
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
        if not self.has_valid_sources or not self.iv_data_sources:
            return []

        common_cols = self.data_repository.data_config.available_columns(
            self.iv_data_sources
        )
        return sorted([col for col, _ in common_cols])

    def _update_iv_inputs(self) -> None:
        """Synchronize selections with current repository state and clear cache."""
        # Remove selected sources that no longer exist
        self.iv_data_sources = [
            ds_id
            for ds_id in self.iv_data_sources
            if ds_id in self.data_repository.data_sources
        ]

        # Default to selecting all data sources if none are selected
        if not self.iv_data_sources and self.data_repository.data_sources:
            self.iv_data_sources = list(self.data_repository.data_sources.keys())

        # Reset target if it's no longer available
        available_targets = self.available_target_columns
        if self.iv_current_target not in available_targets:
            self.iv_current_target = None

        # Filter out input variables that are no longer available
        available_inputs = self.available_input_columns
        self.iv_current_variables = [
            var for var in self.iv_current_variables if var in available_inputs
        ]

        # Invalidate cache and clear messages
        self.__iv_cache.clear()
        self.iv_errors.clear()
        self.iv_warnings.clear()

    def on_dependency_update(self, change_ids: ChangeIDs) -> None:
        """Handle updates from the DataRepository dependency.

        Args:
            change_ids: Set of change IDs from the dependency.
        """
        changed_dependencies = {sig for sig, _ in change_ids}
        if Signature.DATA_REPOSITORY in changed_dependencies:
            self.logger.info("DataRepository updated, refreshing explorer inputs")
            self._update_iv_inputs()

    def get_iv_df(
        self,
        target_variable: str | None,
        input_variables: list[str],
        filter_ids: list[int] | None = None,
        remove_outliers: bool = False,
    ) -> pl.DataFrame | None:
        """Calculate and return Information Value (IV) for input variables.

        Loads and combines selected data sources using Polars, then runs IV calculations.

        Args:
            target_variable: The binary target variable name.
            input_variables: List of independent variable names.
            filter_ids: Optional filters list (ignored for now).
            remove_outliers: Optional outlier removal flag (ignored for now).

        Returns:
            A Polars DataFrame with columns ['variable', 'iv'] sorted by iv desc,
            or None if no calculation was performed.
        """
        self.iv_errors.clear()
        self.iv_warnings.clear()

        if target_variable is None or not input_variables:
            self.iv_warnings.append(
                "Please select a target variable and at least one input variable to calculate IV."
            )
            return None

        if not self.has_valid_sources:
            self.iv_errors.append(
                ValueError("No valid data sources loaded. Please import data first.")
            )
            return None

        if not self.iv_data_sources:
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

        sources_key = tuple(sorted(self.iv_data_sources))
        iv_records: list[dict[str, str | float]] = []

        try:
            # Optimize data loading: load only required columns from selected sources in one pass
            cols_to_load = [target_variable] + input_cols_available
            lazy_frames: list[pl.LazyFrame] = []

            for ds_id in self.iv_data_sources:
                ds = self.data_repository.data_sources[ds_id]

                # Load full schema first and Select only the needed columns to minimize parsing overhead
                lf = ds.get_lazyframe(self.data_repository.data_config.schema).select(
                    cols_to_load
                )
                lazy_frames.append(lf)

            # Concatenate lazy frames and collect in a single pass
            unified_lf = pl.concat(lazy_frames, how="vertical_relaxed")
            df = unified_lf.collect()

        except Exception as error:
            self.logger.error("Failed to load/concatenate data: %s", error)
            self.iv_errors.append(
                ValueError(f"Failed to load data for IV calculation: {error}")
            )
            return None

        # Validate target is binary (0 or 1)
        target_series = df[target_variable]
        if target_series.dtype == pl.Boolean:
            unique_targets = target_series.cast(pl.Int8).drop_nulls().unique().to_list()
        else:
            unique_targets = target_series.drop_nulls().unique().to_list()

        if not set(unique_targets).issubset({0, 1}):
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
                cache_key = (target_variable, input_col, sources_key)
                if cache_key in self.__iv_cache:
                    iv = self.__iv_cache[cache_key]
                else:
                    var_series = df[input_col]

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

            except Exception as error:
                self.logger.error("Error calculating IV for %s: %s", input_col, error)
                self.iv_errors.append(error)

        if not iv_records:
            return None

        # Return sorted Polars DataFrame
        return pl.DataFrame(iv_records).sort("iv", descending=True)
