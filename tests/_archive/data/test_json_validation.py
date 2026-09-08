"""Tests for the validate_json classmethods on repositories and view models."""

from collections import OrderedDict

from risc_tool.data.models.config import RiskSegmentConfig
from risc_tool.data.models.enums import (
    ComparisonOperation,
    IterationType,
    PercentileOptions,
    VariableType,
)
from risc_tool.data.models.iteration_graph import IterationGraph
from risc_tool.data.models.iteration_group import NumericalGroup
from risc_tool.data.models.json_models import (
    DataExplorerViewModelJSON,
    FilterJSON,
    FilterRepositoryJSON,
    IterationJSON,
    IterationRepositoryJSON,
    MetricJSON,
    MetricRepositoryJSON,
    SummaryViewModelJSON,
)
from risc_tool.data.models.uid import (
    FilterID,
    GroupID,
    IterationID,
    MetricID,
)
from risc_tool.data.repositories.data import DataRepository
from risc_tool.data.repositories.filter import FilterRepository
from risc_tool.data.repositories.iterations import IterationsRepository
from risc_tool.data.repositories.metric import MetricRepository
from risc_tool.ui.data_explorer.data_explorer_vm import DataExplorerViewModel
from risc_tool.ui.summary.summary_vm import SummaryViewModel


def test_data_repository_has_no_validate_json():
    assert not hasattr(DataRepository, "validate_json")


def test_filter_repository_validate_json_all_present(data_repository):
    data = FilterRepositoryJSON(
        filters={
            FilterID(0): FilterJSON(
                uid=FilterID(0),
                name="Score Filter",
                query="`credit_score` > 500",
                used_columns=["credit_score"],
            ),
            FilterID(1): FilterJSON(
                uid=FilterID(1),
                name="Income Outlier",
                query="`income` > 100000",
                used_columns=["income"],
                variable_name="income",
                comparison_op=ComparisonOperation.GT,
                comparison_base=PercentileOptions.PERC_50,
                is_outlier=True,
            ),
        }
    )

    assert FilterRepository.validate_json(data_repository, data) == {}


def test_filter_repository_validate_json_missing(data_repository):
    bad_filter = FilterJSON(
        uid=FilterID(0),
        name="Score Filter",
        query="`nonexistent_var` > 500",
        used_columns=["nonexistent_var"],
    )
    outlier = FilterJSON(
        uid=FilterID(1),
        name="Bad Outlier",
        query="`income` > 100000",
        used_columns=["income"],
        variable_name="also_missing",
        comparison_op=ComparisonOperation.GT,
        comparison_base=PercentileOptions.PERC_50,
        is_outlier=True,
    )
    data = FilterRepositoryJSON(filters={FilterID(0): bad_filter, FilterID(1): outlier})

    result = FilterRepository.validate_json(data_repository, data)

    assert result == {FilterID(0): bad_filter}


def _metric_json(
    uid: int, used_columns: list[str], data_source_ids, name: str = "metric"
) -> MetricJSON:
    return MetricJSON(
        uid=MetricID(uid),
        name=name,
        query="`credit_score`.sum()",
        data_source_ids=data_source_ids,
        used_columns=used_columns,
        is_cumulative=False,
        use_thousand_sep=True,
        is_percentage=False,
        decimal_places=2,
        processed_query="`credit_score`.sum()",
        placeholder_map={},
    )


def test_metric_repository_validate_json_all_present(data_repository):
    ds_ids = list(data_repository.data_sources.keys())
    data = MetricRepositoryJSON(
        metrics={
            MetricID(0): _metric_json(0, ["credit_score", "income"], ds_ids),
            MetricID(1): _metric_json(1, ["age"], ds_ids),
        },
    )

    invalid_metrics = MetricRepository.validate_json(data_repository, data)

    assert invalid_metrics == {}


def test_metric_repository_validate_json_missing(data_repository):
    ds_ids = list(data_repository.data_sources.keys())
    bad_metric = _metric_json(0, ["credit_score", "missing_metric_col"], ds_ids)
    data = MetricRepositoryJSON(metrics={MetricID(0): bad_metric})

    invalid_metrics = MetricRepository.validate_json(data_repository, data)

    assert invalid_metrics == {MetricID(0): bad_metric}


def _iteration_json(uid: int, variable_name: str):
    group = NumericalGroup(lower_bound=0.0, upper_bound=1.0)
    return IterationJSON[NumericalGroup](
        var_type=VariableType.NUMERICAL,
        iter_type=IterationType.SINGLE,
        uid=IterationID(uid),
        name="Iteration",
        variable_name=variable_name,
        groups=OrderedDict({GroupID(0): group}),
        default_groups=OrderedDict({GroupID(0): group}),
        risk_segment_details=RiskSegmentConfig(),
    )


def test_iterations_repository_validate_json_all_present(data_repository):
    data = IterationRepositoryJSON(
        iterations=[_iteration_json(0, "credit_score"), _iteration_json(1, "income")],
        graph=IterationGraph(),
    )

    assert IterationsRepository.validate_json(data_repository, data) == {}


def test_iterations_repository_validate_json_missing(data_repository):
    bad_iteration = _iteration_json(0, "nonexistent_iter_var")
    data = IterationRepositoryJSON(
        iterations=[bad_iteration],
        graph=IterationGraph(),
    )

    result = IterationsRepository.validate_json(data_repository, data)

    assert result == {IterationID(0): bad_iteration}


def _summary_json(pv_row_vars, pv_col_vars) -> SummaryViewModelJSON:
    return SummaryViewModelJSON(
        ov_metric_ids=[],
        ov_filter_ids=[],
        ov_scalars_enabled=False,
        ov_remove_outliers=False,
        ov_selected_iteration_id=None,
        ov_selected_iteration_default=False,
        cv_metric_ids=[],
        cv_filter_ids=[],
        cv_scalars_enabled=False,
        cv_remove_outliers=False,
        cv_selected_iterations=OrderedDict(),
        cv_view_mode="list",
        pv_metric_ids=[],
        pv_filter_ids=[],
        pv_remove_outliers=False,
        pv_row_vars=pv_row_vars,
        pv_col_vars=pv_col_vars,
    )


def test_summary_view_model_validate_json_all_present(data_repository):
    data = _summary_json(
        pv_row_vars=["credit_score"],
        pv_col_vars=["income", (IterationID(0), True)],
    )

    assert SummaryViewModel.validate_json(data_repository, data) == []


def test_summary_view_model_validate_json_missing(data_repository):
    data = _summary_json(
        pv_row_vars=["credit_score", "missing_pv_var"],
        pv_col_vars=["also_missing", (IterationID(0), True)],
    )

    assert SummaryViewModel.validate_json(data_repository, data) == [
        "also_missing",
        "missing_pv_var",
    ]


def test_data_explorer_view_model_validate_json_all_present(data_repository):
    data = DataExplorerViewModelJSON(
        iv_data_sources=[],
        iv_current_target="credit_score",
        iv_current_variables=["income", "age"],
        iv_current_filter_ids=[],
        iv_remove_outliers=False,
    )

    assert DataExplorerViewModel.validate_json(data_repository, data) == []


def test_data_explorer_view_model_validate_json_missing(data_repository):
    data = DataExplorerViewModelJSON(
        iv_data_sources=[],
        iv_current_target="missing_target",
        iv_current_variables=["income", "missing_var"],
        iv_current_filter_ids=[],
        iv_remove_outliers=False,
    )

    assert DataExplorerViewModel.validate_json(data_repository, data) == [
        "missing_target",
        "missing_var",
    ]
