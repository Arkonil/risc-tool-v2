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
from risc_tool.data.models.types import (
    ChangeIDs,
    ColorTheme,
    FilterID,
    GridEditorViewComponents,
    GridMetricView,
    GroupID,
    IterationID,
    IterationView,
    MetricID,
    RiskSegmentID,
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
        v_type, i_id = self.current_status

        if v_type != "view" or i_id is None:
            return None

        return self.__iterations_repository.iterations.get(i_id)

    @property
    def current_iteration_type(self) -> IterationType | None:
        current_iteration = self.current_iteration

        if current_iteration is None:
            return None

        return current_iteration.iter_type

    @property
    def current_iteration_create_mode(self) -> IterationType:
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
        if iteration_id not in self.__metadata:
            raise ValueError(f"Iteration {iteration_id} does not exist.")

        return self.__metadata[iteration_id]

    def set_metadata(self, iteration_id: IterationID, **kwargs: t.Any) -> None:
        meta = self.get_iteration_metadata(iteration_id)
        if "filter_ids" in kwargs:
            kwargs["current_filter_ids"] = kwargs.pop("filter_ids")
        meta.update(**kwargs)

    @property
    def data_loaded(self) -> bool:
        return self.__data_repository.has_valid_sources

    @property
    def common_columns(self) -> list[str]:
        return [c[0] for c in self.__data_repository.common_columns()]

    @property
    def iterations(self) -> dict[IterationID, Iteration]:
        return self.__iterations_repository.iterations

    @property
    def iteration_graph(self) -> IterationGraph:
        return self.__iterations_repository.graph

    def can_have_child(self, iteration_id: IterationID) -> bool:
        return iteration_id in self.iterations

    def delete_iteration(self, iteration_id: IterationID) -> None:
        self.__iterations_repository.delete_iteration(iteration_id)
        self.set_current_status("graph")

    def rename_iteration(self, iteration_id: IterationID, name: str) -> None:
        self.__iterations_repository.rename_iteration(iteration_id, name)
        self.set_current_status("graph", selected_iteration_id=iteration_id)

    def get_iteration_name(self, iteration_id: IterationID) -> str:
        return self.__iterations_repository.get_iteration(iteration_id).name

    def get_iteration(self, iteration_id: IterationID) -> Iteration:
        return self.__iterations_repository.get_iteration(iteration_id)

    def global_risk_segment_details(self):
        return self.__options_repository.risk_segments.to_pandas_styler(
            apply_colors_to_name_col=True,
            format_numbers=True,
            all_selected=True,
        )

    def get_risk_segment_details(self, iteration_id: IterationID):
        return self.__iterations_repository.get_risk_segment_details(
            iteration_id
        ).to_pandas_styler(
            apply_colors_to_name_col=True,
            format_numbers=True,
            all_selected=True,
        )

    def get_variable_schema(self, variable_name: str):
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
        errors: list[str] = []

        if selected_segment_ids is not None:
            if not self.__options_repository.risk_segments.has_finite_upper_bound_segment(
                selected_segment_ids
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

            if use_scalars:
                if not self.scalar_selected(loss_rate_type):
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
        return self.__filter_repository.get_filters(filter_ids)

    def metric_variables_selected(self, loss_rate_type: LossRateTypes) -> bool:
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
        scalar = self.__scalar_repository.get_scalar(loss_rate_type)
        return scalar.current_rate is not None and scalar.lifetime_rate is not None

    def is_rs_details_same(
        self, iteration_id: IterationID
    ) -> t.Literal["equal", "unequal", "updatable"]:
        return self.__iterations_repository.is_rs_details_same(iteration_id)

    def update_rs_details(self, iteration_id: IterationID) -> bool:
        if self.__iterations_repository.is_rs_details_same(iteration_id) != "updatable":
            return False
        self.__iterations_repository.update_rs_details(iteration_id)
        return True

    def get_all_groups(self, iteration_id: IterationID) -> pd.DataFrame:
        return self.__iterations_repository.get_all_groups(iteration_id)

    def select_groups(
        self, iteration_id: IterationID, selected_indices: list[GroupID]
    ) -> bool:
        current = self.__iterations_repository.get_all_groups(iteration_id)
        selected_col = RangeColumn.SELECTED.value
        current_selected = (
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
                    lf.select(pl.col(iteration.variable_name).cast(pl.String))
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

        control_df_columns = []

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
                    labels.append(", ".join(str(category) for category in categories))
                else:
                    labels.append("")

        return labels

    def get_editable_grid(
        self, iteration_id: IterationID, default: bool, editable: bool
    ) -> GridEditorViewComponents:
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

            control_df_columns = pd.MultiIndex.from_arrays(
                [
                    [" "] * len(control_df.columns),
                    control_df.columns.map(str).to_list(),
                ]
            )
            risk_segment_grid_columns = pd.MultiIndex.from_arrays(
                [
                    risk_segment_grid.columns.to_list(),
                    self._group_display_labels(previous_iteration_id),
                ]
            )

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
        self.logger.info(
            "Handling grid edit event for iteration ID %s (default: %s)",
            iteration_id,
            default,
        )
        cached_editable_grid = self.__editable_grid_cache.get((iteration_id, default))
        iteration = self.__iterations_repository.get_iteration(iteration_id)

        if iteration.var_type == VariableType.NUMERICAL:
            control_df_columns = pd.Index(
                [
                    RangeColumn.LOWER_BOUND.value,
                    RangeColumn.UPPER_BOUND.value,
                ]
            )
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

            control_df_columns = pd.MultiIndex.from_arrays(
                [
                    [" "] * len(control_df.columns),
                    control_df.columns.map(str).to_list(),
                ]
            )
            metric_grid_columns = pd.MultiIndex.from_arrays(
                [
                    font_color_grid.columns.to_list(),
                    self._group_display_labels(previous_iteration_id),
                ]
            )
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

            metric_df_views.append(
                {
                    "metric_styler": metric_df_styled,
                    "metric_name": metric_summary["metric_name"],
                    "data_source_names": metric_summary["data_source_names"],
                }
            )

        return metric_df_views, errors, warnings


__all__ = ["IterationsViewModel"]
