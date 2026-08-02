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
    data_sources: dict[DataSourceID, DataSource]


# Filter Repository
class FilterJSON(BaseJSON):
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
    filters: dict[FilterID, FilterJSON]


# Metric Repository
class MetricJSON(BaseJSON):
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
    scalars: dict[LossRateTypes, LossRateScalar]


# Option Repository
class OptionsRepositoryJSON(BaseJSON):
    risk_segments: RiskSegmentConfig
    options_config: OptionsConfig


# Iterations Repository
class IterationJSON[TGroup: "GroupBase"](BaseJSON):
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
    iterations: list[IterationJSONItem]
    graph: IterationGraph


# View Models
class IterationsViewModelJSON(BaseJSON):
    metadata: dict[IterationID, IterationMetadata]


class SummaryViewModelJSON(BaseJSON):
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
    iv_data_sources: list[DataSourceID]
    iv_current_target: str | None
    iv_current_variables: list[str]
    iv_current_filter_ids: list[FilterID]
    iv_remove_outliers: bool


# Unified Session Schema
class SessionJSON(BaseJSON):
    data_repository: DataRepositoryJSON
    filter_repository: FilterRepositoryJSON
    metric_repository: MetricRepositoryJSON
    scalar_repository: ScalarRepositoryJSON
    options_repository: OptionsRepositoryJSON
    iterations_repository: IterationRepositoryJSON
    iterations_view_model: IterationsViewModelJSON
    summary_view_model: SummaryViewModelJSON
    data_explorer_view_model: DataExplorerViewModelJSON
