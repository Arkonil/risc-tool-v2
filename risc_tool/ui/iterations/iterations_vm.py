"""View Model for the Iterations page and its metric tables/grids."""

import typing as t

import pandas as pd
import polars as pl
from pandas.io.formats.style import Styler
from pydantic import BaseModel

from risc_tool.data.models.changes import ChangeTracker
from risc_tool.data.models.enums import (
    Colors,
    IterationType,
    LossRateTypes,
    RangeColumn,
    RowIndex,
    RSDetCol,
    Signature,
    VariableType,
)
from risc_tool.data.models.iteration import Iteration
from risc_tool.data.models.iteration_graph import IterationGraph
from risc_tool.data.models.iteration_metadata import IterationMetadata
from risc_tool.data.models.json_models import IterationsViewModelJSON
from risc_tool.data.models.object_id import (
    FilterID,
    GroupID,
    IterationID,
    MetricID,
    RiskSegmentID,
)
from risc_tool.data.models.types import (
    ChangeIDs,
    ColorTheme,
    GridEditorViewComponents,
    GridMetricView,
    IterationView,
)
from risc_tool.data.repositories.data import DataRepository
from risc_tool.data.repositories.filter import FilterRepository
from risc_tool.data.repositories.iterations import IterationsRepository
from risc_tool.data.repositories.metric import MetricRepository
from risc_tool.data.repositories.options import OptionRepository
from risc_tool.data.repositories.scalar import ScalarRepository


class IterationViewStatus(BaseModel):
    view: IterationView = "graph"
    iteration_id: IterationID | None = None


def style_df_edge(
    styler_data: pd.DataFrame,
    style_row: bool,
    style_col: bool,
    color_theme: t.Literal["light", "dark"] = "dark",
) -> pd.DataFrame:
    """Apply styling for summary total rows/columns."""
    if color_theme == "dark":
        style = f"color: {Colors.F_TABLE_TOTAL_DARK.value}; background-color: {Colors.B_TABLE_TOTAL_DARK.value}; font-weight: bold;"
    else:
        style = f"color: {Colors.F_TABLE_TOTAL_LIGHT.value}; background-color: {Colors.B_TABLE_TOTAL_LIGHT.value}; font-weight: bold;"

    style_df = pd.DataFrame("", index=styler_data.index, columns=styler_data.columns)
    if style_row and len(style_df) > 0:
        style_df.iloc[-1, :] = style
    if style_col and len(style_df.columns) > 0:
        style_df.iloc[:, -1] = style

    return style_df


def style_from_dfs(
    styler_data: pd.DataFrame,
    font_df: pd.DataFrame,
    bg_df: pd.DataFrame,
) -> pd.DataFrame:
    """Generate CSS strings for dataframe cells."""
    font_df = font_df.copy()
    font_df.columns = styler_data.columns
    font_df.index = styler_data.index

    bg_df = bg_df.copy()
    bg_df.columns = styler_data.columns
    bg_df.index = styler_data.index

    return (
        "color: "
        + font_df.astype(str)
        + "; background-color: "
        + bg_df.astype(str)
        + ";"
    )


class IterationsViewModel(ChangeTracker):
    """ViewModel encapsulating iterations state, LazyFrame evaluation, and Styler construction."""

    @property
    def signature(self) -> Signature:
        """Get the component signature for change tracking.

        Returns:
            Signature.ITERATION_VIEW_MODEL
        """
        return Signature.ITERATION_VIEW_MODEL

    def __init__(
        self,
        data_repository: DataRepository,
        iterations_repository: IterationsRepository,
        options_repository: OptionRepository,
        filter_repository: FilterRepository,
        metric_repository: MetricRepository,
        scalar_repository: ScalarRepository,
    ) -> None:
        """Initialize the IterationsViewModel.

        Args:
            data_repository: Repository for data sources and lazyframes.
            iterations_repository: Repository for iterations and risk segments.
            options_repository: Repository for risk segment options.
            filter_repository: Repository for filters and outlier rules.
            metric_repository: Repository for metrics.
            scalar_repository: Repository for loss rate scalars.
        """
        super().__init__(
            dependencies=[
                data_repository,
                iterations_repository,
                options_repository,
                filter_repository,
                metric_repository,
                scalar_repository,
            ]
        )

        self.__data_repository = data_repository
        self.__iterations_repository = iterations_repository
        self.__options_repository = options_repository
        self.__filter_repository = filter_repository
        self.__metric_repository = metric_repository
        self.__scalar_repository = scalar_repository

        self.__view_status = IterationViewStatus()
        self.__metadata: dict[IterationID, IterationMetadata] = {}
        self.__editable_range_cache: dict[tuple[IterationID, bool], pd.DataFrame] = {}
        self.__editable_grid_cache: dict[tuple[IterationID, bool], pd.DataFrame] = {}

    def on_dependency_update(self, change_ids: ChangeIDs) -> None:
        """Prune cached metadata when iterations, filters, or metrics change.

        Args:
            change_ids: The change IDs of the updated dependencies.
        """
        # Pruning metadata
        all_iterations = self.__iterations_repository.iterations
        all_filters = self.__filter_repository.filters
        all_metrics = self.__metric_repository.metrics

        # 1. Prune iterations
        self.__metadata = {
            k: v for k, v in self.__metadata.items() if k in all_iterations
        }

        # 2. Prune filters and metrics within metadata
        for metadata in self.__metadata.values():
            metadata.metric_ids = [
                m_id for m_id in metadata.metric_ids if m_id in all_metrics
            ]
            metadata.initial_filter_ids = [
                f_id for f_id in metadata.initial_filter_ids if f_id in all_filters
            ]
            metadata.current_filter_ids = [
                f_id for f_id in metadata.current_filter_ids if f_id in all_filters
            ]

        if self.current_iteration is None:
            self.set_current_status("graph")

    @property
    def current_status(self) -> tuple[IterationView, IterationID | None]:
        """The current view state and selected iteration ID.

        Returns:
            A tuple of (view, iteration_id). "view" falls back to ("graph", None)
            if the selected iteration no longer exists.
        """
        if self.__view_status.view == "view":
            if (
                self.__view_status.iteration_id is None
                or self.__view_status.iteration_id
                not in self.__iterations_repository.iterations
            ):
                return "graph", None
            return "view", self.__view_status.iteration_id
        return self.__view_status.view, self.__view_status.iteration_id

    @property
    def current_iteration(self) -> Iteration | None:
        """The iteration currently being viewed, or None if not in view mode."""
        v_type, i_id = self.current_status

        if v_type != "view" or i_id is None:
            return None

        return self.__iterations_repository.iterations.get(i_id)

    @property
    def current_iteration_type(self) -> IterationType | None:
        """The iteration type of the current iteration, or None if not in view mode."""
        current_iteration = self.current_iteration

        if current_iteration is None:
            return None

        return current_iteration.iter_type

    @property
    def current_iteration_create_mode(self) -> IterationType:
        """The iteration type to create in the current create view.

        Returns:
            IterationType.DOUBLE if a parent iteration is selected, otherwise SINGLE.
        """
        view, i_id = self.current_status

        if view != "create":
            self.logger.warning(
                "Current view is not 'create'; returning SINGLE by default."
            )
            return IterationType.SINGLE

        if i_id is None:
            return IterationType.SINGLE

        return IterationType.DOUBLE

    @property
    def current_iteration_create_parent_id(self) -> IterationID | None:
        """The parent iteration ID for the current create view.

        Returns:
            The parent IterationID when creating a double-variable iteration,
            otherwise None.
        """
        view, i_id = self.current_status

        if view != "create":
            self.logger.warning(
                "Current view is not 'create'; returning None by default."
            )
            return None

        return i_id

    def set_current_status(
        self,
        view: IterationView,
        current_iteration_id: IterationID | None = None,
        selected_iteration_id: IterationID | None = None,
        iteration_create_parent_id: IterationID | None = None,
    ) -> None:
        """Set the current view state.

        Args:
            view: The target view ("view", "create", or "graph").
            current_iteration_id: The iteration to view (required for "view").
            selected_iteration_id: The iteration to highlight on the graph.
            iteration_create_parent_id: The parent for a new double-variable iteration.

        Raises:
            ValueError: If view is "view" without a current_iteration_id.
        """
        if view == "view":
            if current_iteration_id is None:
                raise ValueError("Must provide a current iteration ID")
            self.__view_status.view = "view"
            self.__view_status.iteration_id = current_iteration_id
        elif view == "create":
            self.__view_status.view = "create"
            self.__view_status.iteration_id = iteration_create_parent_id
        elif view == "graph":
            self.__view_status.view = "graph"
            self.__view_status.iteration_id = selected_iteration_id

    def get_iteration_metadata(self, iteration_id: IterationID) -> IterationMetadata:
        """Get the metadata cache for an iteration.

        Args:
            iteration_id: The ID of the iteration.

        Returns:
            The IterationMetadata for the iteration.

        Raises:
            ValueError: If no metadata exists for the iteration.
        """
        if iteration_id not in self.__metadata:
            raise ValueError(f"Iteration {iteration_id} does not exist.")

        return self.__metadata[iteration_id]

    def set_metadata(self, iteration_id: IterationID, **kwargs: t.Any) -> None:
        """Update metadata fields for an iteration.

        Args:
            iteration_id: The ID of the iteration.
            **kwargs: Metadata fields to update. "filter_ids" is mapped to
                "current_filter_ids".
        """
        meta = self.get_iteration_metadata(iteration_id)
        if "filter_ids" in kwargs:
            kwargs["current_filter_ids"] = kwargs.pop("filter_ids")
        meta.update(**kwargs)

    @property
    def data_loaded(self) -> bool:
        """Whether valid data sources are loaded."""
        return self.__data_repository.has_valid_sources

    @property
    def common_columns(self) -> list[str]:
        """Common column names across all loaded data sources.

        Returns:
            A list of column names.
        """
        return [c[0] for c in self.__data_repository.common_columns()]

    @property
    def iterations(self) -> dict[IterationID, Iteration]:
        """All iterations managed by the iterations repository.

        Returns:
            A mapping of IterationID to Iteration.
        """
        return self.__iterations_repository.iterations

    @property
    def iteration_graph(self) -> IterationGraph:
        """The iteration dependency graph.

        Returns:
            The IterationGraph of the iterations repository.
        """
        return self.__iterations_repository.graph

    def can_have_child(self, iteration_id: IterationID) -> bool:
        """Check whether an iteration exists and can have a child.

        Args:
            iteration_id: The ID of the iteration.

        Returns:
            True if the iteration exists.
        """
        return iteration_id in self.iterations

    def delete_iteration(self, iteration_id: IterationID) -> None:
        """Delete an iteration and reset the view to the graph.

        Args:
            iteration_id: The ID of the iteration to delete.
        """
        self.__iterations_repository.delete_iteration(iteration_id)
        self.set_current_status("graph")

    def rename_iteration(self, iteration_id: IterationID, name: str) -> None:
        """Rename an iteration and select it on the graph.

        Args:
            iteration_id: The ID of the iteration to rename.
            name: The new iteration name.
        """
        self.__iterations_repository.rename_iteration(iteration_id, name)
        self.set_current_status("graph", selected_iteration_id=iteration_id)

    def get_iteration_name(self, iteration_id: IterationID) -> str:
        """Get the name of an iteration.

        Args:
            iteration_id: The ID of the iteration.

        Returns:
            The iteration name.
        """
        return self.__iterations_repository.get_iteration(iteration_id).name

    def get_iteration(self, iteration_id: IterationID) -> Iteration:
        """Get an iteration by ID.

        Args:
            iteration_id: The ID of the iteration.

        Returns:
            The Iteration model.
        """
        return self.__iterations_repository.get_iteration(iteration_id)

    def global_risk_segment_details(self):
        """Get the global risk segment details as a styled pandas Styler."""
        return self.__options_repository.risk_segments.to_pandas_styler(
            apply_colors_to_name_col=True,
            format_numbers=True,
            all_selected=True,
        )

    def get_risk_segment_details(self, iteration_id: IterationID):
        """Get an iteration's risk segment details as a styled pandas Styler.

        Args:
            iteration_id: The ID of the iteration.

        Returns:
            A styled Styler for the iteration's risk segment details.
        """
        return self.__iterations_repository.get_risk_segment_details(
            iteration_id
        ).to_pandas_styler(
            apply_colors_to_name_col=True,
            format_numbers=True,
            all_selected=True,
        )

    def get_variable_schema(self, variable_name: str):
        """Get the schema entry for a variable.

        Args:
            variable_name: The column name.

        Returns:
            The column schema entry, or None if not present.
        """
        return self.__data_repository.data_config.schema.get(variable_name)

    def validate_iter_create_params(
        self,
        variable_name: str,
        variable_dtype: VariableType,
        auto_band: bool,
        loss_rate_type: LossRateTypes,
        use_scalars: bool,
        selected_segment_ids: list[RiskSegmentID] | None = None,
    ) -> list[str]:
        """Validate parameters before creating a new iteration.

        Args:
            variable_name: The variable to iterate on.
            variable_dtype: Whether the variable is numerical or categorical.
            auto_band: Whether automatic banding is requested.
            loss_rate_type: The loss rate type for auto banding.
            use_scalars: Whether scalar rates are requested.
            selected_segment_ids: Optional selected risk segment IDs.

        Returns:
            A list of error messages (empty if validation passes).
        """
        errors: list[str] = []

        if (
            selected_segment_ids is not None
            and not self.__options_repository.risk_segments.has_finite_upper_bound_segment(
                selected_segment_ids
            )
        ):
            errors.append(
                "At least 1 risk segment with a finite upper bound must be selected."
            )

        if not self.data_loaded:
            errors.append("Data sources are not loaded.")
            return errors

        variable_schema = self.__data_repository.data_config.schema.get(variable_name)

        if variable_schema is None:
            errors.append(
                f"Variable '{variable_name}' does not exist in the data schema."
            )
            return errors

        if (
            variable_dtype == VariableType.NUMERICAL
            and not variable_schema.is_numeric()
        ):
            errors.append(
                f"Variable '{variable_name}' is string/categorical in the data source and cannot be treated as a numerical variable."
            )

        is_categorical = (variable_dtype == VariableType.CATEGORICAL) or (
            not variable_schema.is_numeric()
        )

        if is_categorical:
            lf = self.__data_repository.get_lazyframe()
            unique_count = lf.select(variable_name).unique().count().collect().item()
            if unique_count > self.__options_repository.max_categorical_unique:
                errors.append(
                    f"Variable '{variable_name}' has {unique_count} unique values, "
                    f"which exceeds the maximum allowed for categorical variables "
                    f"({self.__options_repository.max_categorical_unique})."
                )

        if auto_band:
            if not self.metric_variables_selected(loss_rate_type):
                if loss_rate_type == LossRateTypes.DLR:
                    errors.append("Required metric variables for DLR are not selected.")
                elif loss_rate_type == LossRateTypes.ULR:
                    errors.append("Required metric variables for ULR are not selected.")

            if use_scalars and not self.scalar_selected(loss_rate_type):
                if loss_rate_type == LossRateTypes.DLR:
                    errors.append("Scalars for :red-badge[`$ Bad`] are not set.")

                if loss_rate_type == LossRateTypes.ULR:
                    errors.append("Scalars for :red-badge[`# Bad`] are not set.")

        return errors

    def add_single_var_iteration(
        self,
        name: str,
        variable_name: str,
        variable_dtype: VariableType,
        selected_segment_ids: list[RiskSegmentID],
        loss_rate_type: LossRateTypes,
        filter_ids: list[FilterID],
        auto_band: bool,
        use_scalar: bool,
        remove_outliers: bool,
        hv_imp_hr: bool | None = None,
    ):
        """Create a single-variable iteration and its metadata.

        Args:
            name: The iteration name.
            variable_name: The variable to iterate on.
            variable_dtype: Whether the variable is numerical or categorical.
            selected_segment_ids: The risk segment IDs to use.
            loss_rate_type: The loss rate type.
            filter_ids: The initial filter IDs.
            auto_band: Whether to use automatic banding.
            use_scalar: Whether to use scalar rates.
            remove_outliers: Whether to remove outliers.
            hv_imp_hr: Optional high-value-implies-high-risk flag.

        Returns:
            The created iteration.
        """
        iteration = self.__iterations_repository.add_single_var_iteration(
            name,
            variable_name,
            variable_dtype,
            selected_segment_ids,
            loss_rate_type,
            filter_ids,
            auto_band,
            use_scalar,
            remove_outliers,
            hv_imp_hr,
        )

        self.__metadata[iteration.uid] = IterationMetadata(
            scalars_enabled=use_scalar,
            loss_rate_type=loss_rate_type,
            initial_filter_ids=filter_ids,
            current_filter_ids=filter_ids,
            remove_outliers=remove_outliers,
            metric_ids=[m for m in self.__metric_repository.metrics if m.is_default],
        )

        return iteration

    def add_double_var_iteration(
        self,
        name: str,
        previous_iteration_id: IterationID,
        variable_name: str,
        variable_dtype: VariableType,
        auto_band: bool,
        use_scalar: bool,
        remove_outliers: bool,
        upgrade_limit: int | None = None,
        downgrade_limit: int | None = None,
        auto_rank_ordering: bool | None = None,
    ):
        """Create a double-variable iteration and its metadata.

        Args:
            name: The iteration name.
            previous_iteration_id: The parent iteration ID.
            variable_name: The variable to iterate on.
            variable_dtype: Whether the variable is numerical or categorical.
            auto_band: Whether to use automatic banding.
            use_scalar: Whether to use scalar rates.
            remove_outliers: Whether to remove outliers.
            upgrade_limit: Optional upgrade limit for auto banding.
            downgrade_limit: Optional downgrade limit for auto banding.
            auto_rank_ordering: Optional auto rank ordering flag.

        Returns:
            The created iteration.
        """
        prev_metadata = self.get_iteration_metadata(previous_iteration_id)
        loss_rate_type = prev_metadata.loss_rate_type
        filter_ids = prev_metadata.initial_filter_ids

        iteration = self.__iterations_repository.add_double_var_iteration(
            name,
            previous_iteration_id,
            variable_name,
            variable_dtype,
            loss_rate_type,
            filter_ids,
            auto_band,
            use_scalar,
            remove_outliers,
            upgrade_limit,
            downgrade_limit,
            auto_rank_ordering,
        )

        self.__metadata[iteration.uid] = IterationMetadata(
            scalars_enabled=use_scalar,
            loss_rate_type=loss_rate_type,
            initial_filter_ids=filter_ids,
            current_filter_ids=filter_ids,
            remove_outliers=remove_outliers,
            metric_ids=[m for m in self.__metric_repository.metrics if m.is_default],
        )

        return iteration

    def get_filters(self, filter_ids: list[FilterID] | None = None):
        """Get filters, optionally filtered to the given IDs.

        Args:
            filter_ids: Optional list of filter IDs to return.

        Returns:
            A mapping of FilterID to Filter.
        """
        return self.__filter_repository.get_filters(filter_ids)

    def metric_variables_selected(self, loss_rate_type: LossRateTypes) -> bool:
        """Check whether the metric variables for a loss rate type are selected.

        Args:
            loss_rate_type: The loss rate type (ULR or DLR).

        Returns:
            True if the required dev variables are configured.
        """
        if loss_rate_type == LossRateTypes.ULR:
            return self.__metric_repository.var_dev_unt_bad is not None
        return (
            self.__metric_repository.var_dev_dlr_bad is not None
            and self.__metric_repository.var_dev_avg_bal is not None
        )

    # @property
    # def max_categorical_unique(self) -> int:
    #     return self.__options_repository.max_categorical_unique

    def scalar_selected(self, loss_rate_type: LossRateTypes) -> bool:
        """Check whether both scalar rates are set for a loss rate type.

        Args:
            loss_rate_type: The loss rate type.

        Returns:
            True if current and lifetime rates are both configured.
        """
        scalar = self.__scalar_repository.get_scalar(loss_rate_type)
        return scalar.current_rate is not None and scalar.lifetime_rate is not None

    def is_rs_details_same(
        self, iteration_id: IterationID
    ) -> t.Literal["equal", "unequal", "updatable"]:
        """Compare an iteration's risk segment details to the global config.

        Args:
            iteration_id: The ID of the iteration.

        Returns:
            "equal", "unequal", or "updatable".
        """
        return self.__iterations_repository.is_rs_details_same(iteration_id)

    def update_rs_details(self, iteration_id: IterationID) -> bool:
        """Sync an iteration's risk segment details from the global config.

        Args:
            iteration_id: The ID of the iteration.

        Returns:
            True if details were updated, False if not updatable.
        """
        if self.__iterations_repository.is_rs_details_same(iteration_id) != "updatable":
            return False
        self.__iterations_repository.update_rs_details(iteration_id)
        return True

    def get_all_groups(self, iteration_id: IterationID) -> pd.DataFrame:
        """Get all groups for an iteration as a DataFrame.

        Args:
            iteration_id: The ID of the iteration.

        Returns:
            A DataFrame indexed by GroupID.
        """
        return self.__iterations_repository.get_all_groups(iteration_id)

    def select_groups(
        self, iteration_id: IterationID, selected_indices: list[GroupID]
    ) -> bool:
        """Set the active groups for a double-variable iteration.

        Args:
            iteration_id: The ID of the iteration.
            selected_indices: The GroupIDs to select.

        Returns:
            True if the selection changed, False otherwise.
        """
        current = self.__iterations_repository.get_all_groups(iteration_id)
        selected_col = RangeColumn.SELECTED.value
        current_selected: set[GroupID] = (
            set(current.index[current[selected_col]].tolist())
            if selected_col in current.columns
            else set()
        )
        new_selected = set(selected_indices)
        if current_selected == new_selected:
            return False
        self.__iterations_repository.select_groups(iteration_id, selected_indices)
        return True

    def add_new_group(self, iteration_id: IterationID) -> bool:
        """Add a new blank group to a double-variable iteration.

        Args:
            iteration_id: The ID of the iteration.

        Returns:
            True if a group was added, False otherwise.
        """
        before_count = len(self.__iterations_repository.get_all_groups(iteration_id))
        self.__iterations_repository.add_new_group(iteration_id)
        after_count = len(self.__iterations_repository.get_all_groups(iteration_id))
        return after_count > before_count

    def get_iteration_metric_table(
        self,
        iteration_id: IterationID,
        default: bool,
        show_controls: bool,
        filter_ids: list[FilterID],
        metric_ids: list[MetricID],
        scalars_enabled: bool,
        remove_outliers: bool,
        show_total_row: bool = False,
        theme: t.Literal["light", "dark"] = "dark",
    ) -> tuple[Styler, list[str], list[str]]:
        """Construct pandas Styler for iteration metric table display."""
        iteration = self.__iterations_repository.get_iteration(iteration_id)

        # 1. Label range
        rs_label_df = self.__iterations_repository.get_risk_segment_range(
            iteration_id, show_total_row
        )
        font_color_df, bg_color_df = self.__iterations_repository.get_color_range(
            iteration_id, show_total_row
        )

        # 2. Control range
        if show_controls and iteration.iter_type == IterationType.SINGLE:
            control_df = self.__iterations_repository.get_controls(
                iteration_id, default=default
            )
        else:
            control_df = None

        # 3. Metric range
        metric_df, errors, warnings = self.__iterations_repository.get_metric_range(
            iteration_id=iteration_id,
            default=default,
            filter_ids=filter_ids,
            metric_ids=metric_ids,
            scalars_enabled=scalars_enabled,
            remove_outliers=remove_outliers,
            show_total_row=show_total_row,
        )

        # Concatenate df
        final_df = rs_label_df

        if control_df is not None:
            final_df = final_df.join(control_df)

        final_df = final_df.join(metric_df)
        self.__editable_range_cache[(iteration_id, default)] = final_df.copy()
        # if control_df is None:
        #     final_df = pd.concat([rs_label_df, metric_df], axis=1)
        # else:
        #     final_df = pd.concat([rs_label_df, control_df, metric_df], axis=1)

        final_df_styled = final_df.style.apply(
            style_from_dfs,
            axis=None,
            subset=rs_label_df.columns,
            font_df=font_color_df,
            bg_df=bg_color_df,
        )

        final_df_styled = final_df_styled.apply(
            style_df_edge,
            axis=None,
            style_row=show_total_row,
            style_col=False,
            color_theme=theme,
        )

        return final_df_styled, errors, warnings

    def get_categorical_iteration_options(self, iteration_id: IterationID) -> list[str]:
        """Return available categorical unique options for an iteration variable."""
        iteration = self.__iterations_repository.get_iteration(iteration_id)

        if iteration.var_type == VariableType.CATEGORICAL:
            if not self.__data_repository.has_valid_sources:
                return []
            lf = self.__data_repository.get_lazyframe()
            if iteration.variable_name in self.__data_repository.data_config.schema:
                unique_vals = (
                    lf
                    .select(pl.col(iteration.variable_name).cast(pl.String))
                    .unique()
                    .drop_nulls()
                    .collect()
                    .get_column(iteration.variable_name)
                    .to_list()
                )
                return sorted([str(v) for v in unique_vals])

        return []

    def editable_range_edit_handler(
        self, iteration_id: IterationID, default: bool, edited_final_df: pd.DataFrame
    ) -> bool:
        """Handle edit events from st.data_editor and pass changed controls to repository."""
        self.logger.info(
            "Handling range edit event for iteration ID %s (default: %s)",
            iteration_id,
            default,
        )
        cached_editable_range = self.__editable_range_cache.get((iteration_id, default))
        if cached_editable_range is not None and edited_final_df.equals(
            cached_editable_range
        ):
            return False

        control_df_columns: list[str] = []

        if RangeColumn.LOWER_BOUND.value in edited_final_df.columns:
            control_df_columns.append(RangeColumn.LOWER_BOUND.value)

        if RangeColumn.UPPER_BOUND.value in edited_final_df.columns:
            control_df_columns.append(RangeColumn.UPPER_BOUND.value)

        if RangeColumn.CATEGORIES.value in edited_final_df.columns:
            control_df_columns.append(RangeColumn.CATEGORIES.value)

        if control_df_columns:
            control_df = edited_final_df[control_df_columns]
            self.logger.info(
                "Updating controls for iteration ID %s on the fly",
                iteration_id,
            )
            self.__iterations_repository.set_controls(iteration_id, control_df)

        return bool(control_df_columns)

    def _group_display_labels(self, iteration_id: IterationID) -> list[str]:
        """Build display labels for the custom groups of an iteration.

        Args:
            iteration_id: The ID of the iteration.

        Returns:
            A list of label strings for each custom group.
        """
        iteration = self.__iterations_repository.get_iteration(iteration_id)
        controls = self.__iterations_repository.get_controls(
            iteration_id, default=False
        )
        labels: list[str] = []

        if iteration.var_type == VariableType.NUMERICAL:
            for _, row in controls.iterrows():
                labels.append(
                    f"({float(row[RangeColumn.LOWER_BOUND.value])} - {float(row[RangeColumn.UPPER_BOUND.value])}]"
                )
        else:
            for _, row in controls.iterrows():
                categories = row[RangeColumn.CATEGORIES.value]
                if isinstance(categories, list):
                    labels.append(", ".join(str(category) for category in categories))  # type: ignore
                else:
                    labels.append("")

        return labels

    def get_editable_grid(
        self, iteration_id: IterationID, default: bool, editable: bool
    ) -> GridEditorViewComponents:
        """Build the editable risk segment grid with styling.

        Args:
            iteration_id: The ID of the double-variable iteration.
            default: Whether to use default or custom groups.
            editable: Whether the grid is in edit mode.

        Returns:
            A dict with the styled grid and column positions/options.
        """
        control_df = self.__iterations_repository.get_controls(iteration_id, default)
        risk_segment_grid = self.__iterations_repository.get_risk_segment_grid(
            iteration_id,
            default,
            RSDetCol.RISK_SEGMENT,
        )
        font_color_grid = self.__iterations_repository.get_risk_segment_grid(
            iteration_id,
            default,
            RSDetCol.FONT_COLOR,
        )
        bg_color_grid = self.__iterations_repository.get_risk_segment_grid(
            iteration_id,
            default,
            RSDetCol.BG_COLOR,
        )

        final_df = pd.concat([control_df, risk_segment_grid], axis=1)
        self.__editable_grid_cache[(iteration_id, default)] = final_df.copy()

        displayed_columns = final_df.columns.to_list()
        lower_bound_pos = (
            1 + displayed_columns.index(RangeColumn.LOWER_BOUND.value)
            if RangeColumn.LOWER_BOUND.value in displayed_columns
            else None
        )
        upper_bound_pos = (
            1 + displayed_columns.index(RangeColumn.UPPER_BOUND.value)
            if RangeColumn.UPPER_BOUND.value in displayed_columns
            else None
        )
        categories_pos = (
            1 + displayed_columns.index(RangeColumn.CATEGORIES.value)
            if RangeColumn.CATEGORIES.value in displayed_columns
            else None
        )
        risk_segment_grid_col_pos = [
            1 + displayed_columns.index(column_name)
            for column_name in risk_segment_grid.columns
        ]
        grid_options = risk_segment_grid.columns.to_list()

        show_prev_iter_details = (
            self.get_iteration_metadata(iteration_id).show_prev_iter_details
            and not editable
            and self.__iterations_repository.graph.iteration_depth(iteration_id) == 2
        )

        styler_subset = risk_segment_grid.columns
        if show_prev_iter_details:
            previous_iteration_id = self.__iterations_repository.graph.get_parent(
                iteration_id
            )
            assert previous_iteration_id is not None

            control_df_columns = pd.MultiIndex.from_arrays([
                [" "] * len(control_df.columns),
                control_df.columns.map(str).to_list(),
            ])
            risk_segment_grid_columns = pd.MultiIndex.from_arrays([
                risk_segment_grid.columns.to_list(),
                self._group_display_labels(previous_iteration_id),
            ])

            final_df.columns = control_df_columns.append(risk_segment_grid_columns)
            styler_subset = risk_segment_grid_columns

        final_df_styled = final_df.style.apply(
            style_from_dfs,
            axis=None,
            subset=styler_subset,
            font_df=font_color_grid,
            bg_df=bg_color_grid,
        )

        return {
            "styler": final_df_styled,
            "lower_bound_pos": lower_bound_pos,
            "upper_bound_pos": upper_bound_pos,
            "categories_pos": categories_pos,
            "risk_segment_grid_col_pos": risk_segment_grid_col_pos,
            "grid_options": grid_options,
            "show_prev_iter_details": show_prev_iter_details,
        }

    def editable_grid_edit_handler(
        self, iteration_id: IterationID, default: bool, edited_final_df: pd.DataFrame
    ) -> bool:
        """Handle edits to the risk segment grid and persist them.

        Args:
            iteration_id: The ID of the iteration.
            default: Whether editing the default grid.
            edited_final_df: The edited DataFrame from the data editor.

        Returns:
            True if changes were persisted, False otherwise.
        """
        self.logger.info(
            "Handling grid edit event for iteration ID %s (default: %s)",
            iteration_id,
            default,
        )
        cached_editable_grid = self.__editable_grid_cache.get((iteration_id, default))
        iteration = self.__iterations_repository.get_iteration(iteration_id)

        if iteration.var_type == VariableType.NUMERICAL:
            control_df_columns = pd.Index([
                RangeColumn.LOWER_BOUND.value,
                RangeColumn.UPPER_BOUND.value,
            ])
        else:
            control_df_columns = pd.Index([RangeColumn.CATEGORIES.value])

        risk_segment_grid_columns = pd.Index(
            list(
                self.__iterations_repository.get_risk_segment_details(
                    iteration_id
                ).segments.values()
            )
        ).map(lambda seg: seg.name)
        edited_final_df.columns = control_df_columns.append(risk_segment_grid_columns)

        if cached_editable_grid is not None and edited_final_df.equals(
            cached_editable_grid
        ):
            return False

        edited_control_df = edited_final_df[control_df_columns]
        edited_risk_segment_grid = edited_final_df[risk_segment_grid_columns]

        self.__iterations_repository.set_controls(iteration_id, edited_control_df)
        self.__iterations_repository.set_risk_segment_grid(
            iteration_id, edited_risk_segment_grid
        )
        return True

    def get_metric_grids(
        self,
        iteration_id: IterationID,
        default: bool,
        show_controls_idx: t.Literal["all", "alternate"] | list[int],
        show_total_row: bool = False,
        show_total_column: bool = False,
        theme: ColorTheme = "dark",
    ) -> tuple[list[GridMetricView], list[str], list[str]]:
        """Calculate and style metric grids for a double-variable iteration.

        Args:
            iteration_id: The ID of the iteration.
            default: Whether to use default or custom groups.
            show_controls_idx: Which grids show controls ("all", "alternate", or indices).
            show_total_row: Whether to include a total row.
            show_total_column: Whether to include a total column.
            theme: The color theme for total row/column styling.

        Returns:
            A tuple of styled metric grid views, list of errors, and list of warnings.
        """
        metadata = self.get_iteration_metadata(iteration_id)
        metric_summaries, errors, warnings = (
            self.__iterations_repository.get_metric_grids(
                iteration_id=iteration_id,
                default=default,
                filter_ids=metadata.current_filter_ids,
                metric_ids=metadata.metric_ids,
                scalars_enabled=metadata.scalars_enabled,
                remove_outliers=metadata.remove_outliers,
                show_total_row=show_total_row,
                show_total_column=show_total_column,
            )
        )
        font_color_grid = self.__iterations_repository.get_risk_segment_grid(
            iteration_id,
            default,
            RSDetCol.FONT_COLOR,
        )
        bg_color_grid = self.__iterations_repository.get_risk_segment_grid(
            iteration_id,
            default,
            RSDetCol.BG_COLOR,
        )

        if show_total_row:
            font_color_grid.loc[RowIndex.TOTAL, :] = Colors.F_TABLE_TOTAL_LIGHT.value
            bg_color_grid.loc[RowIndex.TOTAL, :] = Colors.B_TABLE_TOTAL_LIGHT.value

        if len(metric_summaries) == 0:
            return [], errors, warnings

        if show_controls_idx == "all":
            show_controls = [True] * len(metric_summaries)
        elif show_controls_idx == "alternate":
            show_controls = [i % 2 != 0 for i in range(len(metric_summaries))]
        else:
            show_controls = [
                i in show_controls_idx for i in range(len(metric_summaries))
            ]

        control_df = self.__iterations_repository.get_controls(iteration_id, default)
        if show_total_row:
            control_df = control_df.astype(str)
            control_df.at[RowIndex.TOTAL, control_df.columns[0]] = "Total"

        show_prev_iter_details = (
            self.get_iteration_metadata(iteration_id).show_prev_iter_details
            and self.__iterations_repository.graph.iteration_depth(iteration_id) == 2
        )
        if show_prev_iter_details:
            previous_iteration_id = self.__iterations_repository.graph.get_parent(
                iteration_id
            )
            assert previous_iteration_id is not None

            control_df_columns = pd.MultiIndex.from_arrays([
                [" "] * len(control_df.columns),
                control_df.columns.map(str).to_list(),
            ])
            metric_grid_columns = pd.MultiIndex.from_arrays([
                font_color_grid.columns.to_list(),
                self._group_display_labels(previous_iteration_id),
            ])
            if show_total_column:
                metric_grid_columns = metric_grid_columns.append(
                    pd.MultiIndex.from_arrays([[" "], ["Total"]])
                )
        else:
            control_df_columns = control_df.columns
            metric_grid_columns = font_color_grid.columns
            if show_total_column:
                metric_grid_columns = metric_grid_columns.append(pd.Index(["Total"]))

        combined_df_columns = control_df_columns.append(metric_grid_columns)
        styler_subset = font_color_grid.columns
        metric_df_views: list[GridMetricView] = []

        for metric_summary, show_control in zip(metric_summaries, show_controls):
            metric_grid = t.cast(pd.DataFrame, metric_summary["metric_grid"]).copy()
            if show_control:
                metric_df = pd.concat([control_df, metric_grid], axis=1)
                metric_df.columns = combined_df_columns
            else:
                metric_df = metric_grid
                metric_df.columns = metric_grid_columns

            metric_df_styled = metric_df.style.apply(
                style_from_dfs,
                axis=None,
                subset=styler_subset,
                font_df=font_color_grid,
                bg_df=bg_color_grid,
            )
            metric_df_styled = metric_df_styled.apply(
                style_df_edge,
                axis=None,
                style_row=show_total_row,
                style_col=show_total_column,
                color_theme=theme,
            )

            metric_df_views.append({
                "metric_styler": metric_df_styled,
                "metric_name": metric_summary["metric_name"],
                "data_source_names": metric_summary["data_source_names"],
            })

        return metric_df_views, errors, warnings

    def to_dict(self) -> IterationsViewModelJSON:
        """Serialize IterationsViewModel state to IterationsViewModelJSON Pydantic model."""

        return IterationsViewModelJSON(
            metadata=self.__metadata,
        )

    @classmethod
    def from_dict(
        cls,
        data: IterationsViewModelJSON,
        data_repository: DataRepository,
        iterations_repository: IterationsRepository,
        options_repository: OptionRepository,
        filter_repository: FilterRepository,
        metric_repository: MetricRepository,
        scalar_repository: ScalarRepository,
    ) -> "IterationsViewModel":
        """Reconstruct IterationsViewModel from IterationsViewModelJSON Pydantic model or dict."""
        vm = cls(
            data_repository=data_repository,
            iterations_repository=iterations_repository,
            options_repository=options_repository,
            filter_repository=filter_repository,
            metric_repository=metric_repository,
            scalar_repository=scalar_repository,
        )

        for iteration_id, metadata in data.metadata.items():
            vm.__metadata[iteration_id] = metadata

        return vm


__all__ = ["IterationsViewModel"]
