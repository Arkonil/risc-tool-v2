"""JSON Pydantic schemas for session serialization and deserialization."""

import typing as t
from collections import OrderedDict
from uuid import UUID

from pydantic import BaseModel, ConfigDict, model_validator

from risc_tool.data.models.config import (
    LossRateScalar,
    OptionsConfig,
    RiskSegmentConfig,
)
from risc_tool.data.models.data_source import DataSource
from risc_tool.data.models.enums import (
    ComparisonOperation,
    IterationType,
    LossRateTypes,
    PercentileOptions,
    SummaryPageTabName,
    VariableType,
)
from risc_tool.data.models.iteration_graph import IterationGraph
from risc_tool.data.models.iteration_group import (
    CategoricalGroup,
    GroupBase,
    NumericalGroup,
)
from risc_tool.data.models.iteration_metadata import IterationMetadata
from risc_tool.data.models.types import (
    DataSourceID,
    FilterID,
    GroupID,
    IterationID,
    MetricID,
    RiskSegmentID,
)


class BaseJSON(BaseModel):
    """Base Pydantic model configuration for JSON serialization."""

    model_config = ConfigDict(validate_assignment=True, ser_json_inf_nan="strings")


# Data Repository
class DataRepositoryJSON(BaseJSON):
    """JSON schema for the DataRepository state.

    Attributes:
        data_sources: Mapping of DataSourceID to DataSource models.
    """

    data_sources: dict[DataSourceID, DataSource]


# Filter Repository
class FilterJSON(BaseJSON):
    """JSON schema for a single filter or outlier rule.

    Attributes:
        uid: Unique identifier for the filter.
        name: Human-readable filter name.
        query: Raw filter expression string.
        used_columns: Column names referenced by the query.
        variable_name: Column name for outlier rules (None for normal filters).
        comparison_op: Comparison operator for outlier rules (None otherwise).
        comparison_base: Percentile option or threshold for outlier rules (None otherwise).
        is_outlier: Whether this filter is an outlier rule.
    """

    uid: FilterID
    name: str
    query: str
    used_columns: list[str]
    variable_name: str | None = None
    comparison_op: ComparisonOperation | None = None
    comparison_base: PercentileOptions | float | None = None
    is_outlier: bool = False

    @model_validator(mode="after")
    def validate_outlier_fields(self) -> "FilterJSON":
        """Require outlier comparison fields when this filter is marked as outlier."""
        if self.is_outlier and (
            self.variable_name is None
            or self.comparison_op is None
            or self.comparison_base is None
        ):
            raise ValueError(
                "Outlier filters require variable_name, comparison_op, and comparison_base"
            )
        return self


class FilterRepositoryJSON(BaseJSON):
    """JSON schema for the FilterRepository state.

    Attributes:
        filters: Mapping of FilterID to FilterJSON models.
    """

    filters: dict[FilterID, FilterJSON]


# Metric Repository
class MetricJSON(BaseJSON):
    """JSON schema for a single metric.

    Attributes:
        uid: Unique identifier for the metric.
        name: Human-readable metric name.
        query: Raw metric expression string.
        data_source_ids: Data sources used to evaluate the metric.
        used_columns: Column names referenced by the query.
        is_cumulative: Whether the metric is cumulative over time.
        use_thousand_sep: Whether to display numbers with thousands separators.
        is_percentage: Whether the metric value is formatted as a percentage.
        decimal_places: Number of decimal places used when formatting.
        processed_query: Query with placeholders resolved to actual expressions.
        placeholder_map: Mapping from placeholder names to original expressions.
    """

    uid: MetricID
    name: str
    query: str
    data_source_ids: list[DataSourceID]
    used_columns: list[str]
    is_cumulative: bool
    use_thousand_sep: bool
    is_percentage: bool
    decimal_places: int
    processed_query: str
    placeholder_map: dict[str, str]


class MetricRepositoryJSON(BaseJSON):
    """JSON schema for the MetricRepository state.

    Attributes:
        metrics: Mapping of MetricID to MetricJSON models.
        var_dev_unt_bad: Development unit bad rate variable name.
        var_dev_dlr_bad: Development dollar bad rate variable name.
        var_dev_avg_bal: Development average balance variable name.
        var_tst_unt_bad: Test unit bad rate variable name.
        var_tst_dlr_bad: Test dollar bad rate variable name.
        var_tst_avg_bal: Test average balance variable name.
        current_rate_mob: Current rate month-on-book value.
        lifetime_rate_mob: Lifetime rate month-on-book value.
        dev_data_source_ids: Development data source IDs.
        tst_data_source_ids: Test data source IDs.
    """

    metrics: dict[MetricID, MetricJSON]
    var_dev_unt_bad: str | None
    var_dev_dlr_bad: str | None
    var_dev_avg_bal: str | None
    var_tst_unt_bad: str | None
    var_tst_dlr_bad: str | None
    var_tst_avg_bal: str | None
    current_rate_mob: int
    lifetime_rate_mob: int
    dev_data_source_ids: list[DataSourceID]
    tst_data_source_ids: list[DataSourceID]


# Scalar Repository
class ScalarRepositoryJSON(BaseJSON):
    """JSON schema for the ScalarRepository state.

    Attributes:
        scalars: Mapping of LossRateTypes to LossRateScalar models.
    """

    scalars: dict[LossRateTypes, LossRateScalar]


# Option Repository
class OptionsRepositoryJSON(BaseJSON):
    """JSON schema for the OptionRepository state.

    Attributes:
        risk_segments: Risk segment configuration model.
        options_config: Global options configuration model.
    """

    risk_segments: RiskSegmentConfig
    options_config: OptionsConfig


# Iterations Repository
class IterationJSON[TGroup: "GroupBase"](BaseJSON):
    """JSON schema for a single iteration.

    Attributes:
        var_type: Variable type (numerical or categorical).
        iter_type: Iteration type (single or double variable).
        uid: Unique identifier for the iteration.
        name: Human-readable iteration name.
        variable_name: Variable used for the iteration.
        groups: Mapping of GroupID to group models.
        default_groups: Mapping of GroupID to default group models.
        risk_segment_details: Risk segment details for single-variable iterations.
        groups_mask: Group selection mask for double-variable iterations.
        risk_segment_grid: Grid mapping groups and risk segments for double-variable iterations.
        default_risk_segment_grid: Default grid for double-variable iterations.
    """

    var_type: VariableType
    iter_type: IterationType
    uid: IterationID
    name: str
    variable_name: str
    groups: OrderedDict[GroupID, TGroup]
    default_groups: OrderedDict[GroupID, TGroup]

    # Single Var
    risk_segment_details: RiskSegmentConfig | None = None

    # Double Var
    groups_mask: dict[GroupID, bool] | None = None
    risk_segment_grid: dict[GroupID, dict[RiskSegmentID, RiskSegmentID]] | None = None
    default_risk_segment_grid: (
        dict[GroupID, dict[RiskSegmentID, RiskSegmentID]] | None
    ) = None

    @model_validator(mode="after")
    def validate_outlier_fields(self) -> "IterationJSON[TGroup]":
        """Require outlier comparison fields when this filter is marked as outlier."""
        if self.iter_type == IterationType.SINGLE and self.risk_segment_details is None:
            raise ValueError(
                "Single variable iterations require risk_segment_details to be provided"
            )

        if self.iter_type == IterationType.DOUBLE and (
            self.groups_mask is None
            or self.risk_segment_grid is None
            or self.default_risk_segment_grid is None
        ):
            raise ValueError(
                "Double variable iterations require groups_mask, risk_segment_grid, and default_risk_segment_grid to be provided"
            )

        return self


IterationJSONItem = IterationJSON[CategoricalGroup] | IterationJSON[NumericalGroup]


class IterationRepositoryJSON(BaseJSON):
    """JSON schema for the IterationsRepository state.

    Attributes:
        iterations: List of iteration JSON models.
        graph: The iteration dependency graph.
    """

    iterations: list[IterationJSONItem]
    graph: IterationGraph


# View Models
class IterationsViewModelJSON(BaseJSON):
    """JSON schema for the IterationsViewModel state.

    Attributes:
        metadata: Mapping of IterationID to IterationMetadata models.
    """

    metadata: dict[IterationID, IterationMetadata]


class SummaryViewModelJSON(BaseJSON):
    """JSON schema for the SummaryViewModel state.

    Attributes:
        current_tab_name: Currently active summary tab.
        ov_metric_ids: Overview tab selected metric IDs.
        ov_filter_ids: Overview tab selected filter IDs.
        ov_scalars_enabled: Whether scalars are applied on the overview tab.
        ov_remove_outliers: Whether outliers are removed on the overview tab.
        ov_selected_iteration_id: Iteration selected on the overview tab.
        ov_selected_iteration_default: Whether the overview iteration uses default groups.
        cv_metric_ids: Comparison tab selected metric IDs.
        cv_filter_ids: Comparison tab selected filter IDs.
        cv_scalars_enabled: Whether scalars are applied on the comparison tab.
        cv_remove_outliers: Whether outliers are removed on the comparison tab.
        cv_selected_iterations: Ordered mapping of UUID to (iteration ID, default flag).
        cv_view_mode: Comparison tab view mode ("grid" or "list").
        pv_metric_ids: Pivot tab selected metric IDs.
        pv_filter_ids: Pivot tab selected filter IDs.
        pv_remove_outliers: Whether outliers are removed on the pivot tab.
        pv_row_vars: Pivot row variables.
        pv_col_vars: Pivot column variables.
    """

    current_tab_name: SummaryPageTabName = SummaryPageTabName.OVERVIEW

    # Overview
    ov_metric_ids: list[MetricID]
    ov_filter_ids: list[FilterID]
    ov_scalars_enabled: bool
    ov_remove_outliers: bool
    ov_selected_iteration_id: IterationID | None
    ov_selected_iteration_default: bool

    # Comparison Tab
    cv_metric_ids: list[MetricID]
    cv_filter_ids: list[FilterID]
    cv_scalars_enabled: bool
    cv_remove_outliers: bool
    cv_selected_iterations: OrderedDict[UUID, tuple[IterationID, bool]]
    cv_view_mode: t.Literal["grid", "list"]

    # Pivot Tab
    pv_metric_ids: list[MetricID]
    pv_filter_ids: list[FilterID]
    pv_remove_outliers: bool
    pv_row_vars: list[str | tuple[IterationID, bool]]
    pv_col_vars: list[str | tuple[IterationID, bool]]


class DataExplorerViewModelJSON(BaseJSON):
    """JSON schema for the DataExplorerViewModel state.

    Attributes:
        iv_data_sources: Data sources used for IV analysis.
        iv_current_target: Current target variable, if selected.
        iv_current_variables: Variables selected for IV analysis.
        iv_current_filter_ids: Filter IDs applied to the analysis.
        iv_remove_outliers: Whether outlier rules are excluded.
    """

    iv_data_sources: list[DataSourceID]
    iv_current_target: str | None
    iv_current_variables: list[str]
    iv_current_filter_ids: list[FilterID]
    iv_remove_outliers: bool


# Unified Session Schema
class SessionJSON(BaseJSON):
    """Top-level JSON schema for a full session dump.

    Attributes:
        data_repository: Data repository state.
        filter_repository: Filter repository state.
        metric_repository: Metric repository state.
        scalar_repository: Scalar repository state.
        options_repository: Options repository state.
        iterations_repository: Iterations repository state.
        iterations_view_model: Iterations view model state.
        summary_view_model: Summary view model state.
        data_explorer_view_model: Data explorer view model state.
    """

    data_repository: DataRepositoryJSON
    filter_repository: FilterRepositoryJSON
    metric_repository: MetricRepositoryJSON
    scalar_repository: ScalarRepositoryJSON
    options_repository: OptionsRepositoryJSON
    iterations_repository: IterationRepositoryJSON
    iterations_view_model: IterationsViewModelJSON
    summary_view_model: SummaryViewModelJSON
    data_explorer_view_model: DataExplorerViewModelJSON
