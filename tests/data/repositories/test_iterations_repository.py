"""Unit tests for IterationsRepository using Polars LazyFrames and Mock dependencies."""

from unittest.mock import Mock

import pandas as pd
import pytest

from risc_tool.data.models.data_source import ReadConfig
from risc_tool.data.models.enums import LossRateTypes, RSDetCol, VariableType
from risc_tool.data.models.iteration import (
    CategoricalDoubleVarIteration,
    CategoricalSingleVarIteration,
    NumericalDoubleVarIteration,
)
from risc_tool.data.models.types import GroupID, IterationID, RiskSegmentID
from risc_tool.data.repositories.data import DataRepository
from risc_tool.data.repositories.filter import FilterRepository
from risc_tool.data.repositories.iterations import IterationsRepository
from risc_tool.data.repositories.metric import MetricRepository
from risc_tool.data.repositories.options import OptionRepository
from risc_tool.data.repositories.scalar import ScalarRepository


@pytest.fixture
def mock_session_repos():
    data_repo = DataRepository()
    filter_repo = FilterRepository(data_repo)
    metric_repo = MetricRepository(data_repo)
    option_repo = OptionRepository()
    scalar_repo = ScalarRepository()
    iter_repo = IterationsRepository(
        data_repo, filter_repo, metric_repo, option_repo, scalar_repo
    )
    return iter_repo, data_repo, filter_repo, metric_repo, option_repo, scalar_repo


def test_init_empty(mock_session_repos):
    iter_repo, *_ = mock_session_repos
    assert len(iter_repo.iterations) == 0
    assert len(iter_repo.graph.connections) == 0


def test_subscriber_notified(mock_session_repos):
    iter_repo, data_repo, *_ = mock_session_repos
    subscriber = Mock()
    iter_repo.subscribe(subscriber)

    # Trigger dependency change
    data_repo.notify_subscribers()
    assert subscriber.call_count >= 1


def test_non_auto_numeric_defaults_use_quantiles(tmp_path):
    data_repo = DataRepository()
    csv_path = tmp_path / "numeric.csv"
    pd.DataFrame({"score": [10, 20, 30, 40, 50, 60, 70, 80]}).to_csv(
        csv_path,
        index=False,
    )
    data_repo.add_data_source("Dev Data", csv_path, ReadConfig())

    filter_repo = FilterRepository(data_repo)
    metric_repo = MetricRepository(data_repo)
    option_repo = OptionRepository()
    scalar_repo = ScalarRepository()
    iter_repo = IterationsRepository(
        data_repo,
        filter_repo,
        metric_repo,
        option_repo,
        scalar_repo,
    )

    iteration = iter_repo.add_single_var_iteration(
        name="Score Quantile Defaults",
        variable_name="score",
        variable_dtype=VariableType.NUMERICAL,
        selected_segment_ids=[
            RiskSegmentID(0),
            RiskSegmentID(1),
            RiskSegmentID(2),
            RiskSegmentID(3),
        ],
        loss_rate_type=LossRateTypes.DLR,
        filter_ids=[],
        auto_band=False,
        use_scalar=False,
        remove_outliers=False,
    )

    groups = list(iteration.default_groups.values())
    assert len(groups) == 4
    assert groups[0].lower_bound == float("-inf")
    assert groups[0].upper_bound == pytest.approx(27.5)
    assert groups[1].lower_bound == pytest.approx(27.5)
    assert groups[1].upper_bound == pytest.approx(45.0)
    assert groups[2].lower_bound == pytest.approx(45.0)
    assert groups[2].upper_bound == pytest.approx(62.5)
    assert groups[3].lower_bound == pytest.approx(62.5)
    assert groups[3].upper_bound == float("inf")


def test_non_auto_categorical_defaults_split_unique_values_evenly(tmp_path):
    data_repo = DataRepository()
    csv_path = tmp_path / "categorical_even.csv"
    pd.DataFrame({"grade": ["e", "b", "a", "c", "d", "a", "c"]}).to_csv(
        csv_path,
        index=False,
    )
    data_repo.add_data_source("Dev Data", csv_path, ReadConfig())

    filter_repo = FilterRepository(data_repo)
    metric_repo = MetricRepository(data_repo)
    option_repo = OptionRepository()
    scalar_repo = ScalarRepository()
    iter_repo = IterationsRepository(
        data_repo,
        filter_repo,
        metric_repo,
        option_repo,
        scalar_repo,
    )

    iteration = iter_repo.add_single_var_iteration(
        name="Categorical Defaults",
        variable_name="grade",
        variable_dtype=VariableType.CATEGORICAL,
        selected_segment_ids=[RiskSegmentID(0), RiskSegmentID(1), RiskSegmentID(2)],
        loss_rate_type=LossRateTypes.DLR,
        filter_ids=[],
        auto_band=False,
        use_scalar=False,
        remove_outliers=False,
    )

    groups = list(iteration.default_groups.values())
    assert len(groups) == 3
    assert groups[0].categories == {"a", "b"}
    assert groups[1].categories == {"c", "d"}
    assert groups[2].categories == {"e"}


def test_non_auto_categorical_defaults_allow_empty_groups(tmp_path):
    data_repo = DataRepository()
    csv_path = tmp_path / "categorical_empty_groups.csv"
    pd.DataFrame({"bucket": ["x", "y", "x"]}).to_csv(csv_path, index=False)
    data_repo.add_data_source("Dev Data", csv_path, ReadConfig())

    filter_repo = FilterRepository(data_repo)
    metric_repo = MetricRepository(data_repo)
    option_repo = OptionRepository()
    scalar_repo = ScalarRepository()
    iter_repo = IterationsRepository(
        data_repo,
        filter_repo,
        metric_repo,
        option_repo,
        scalar_repo,
    )

    iteration = iter_repo.add_single_var_iteration(
        name="Categorical Empty Defaults",
        variable_name="bucket",
        variable_dtype=VariableType.CATEGORICAL,
        selected_segment_ids=[
            RiskSegmentID(0),
            RiskSegmentID(1),
            RiskSegmentID(2),
            RiskSegmentID(3),
        ],
        loss_rate_type=LossRateTypes.DLR,
        filter_ids=[],
        auto_band=False,
        use_scalar=False,
        remove_outliers=False,
    )

    groups = list(iteration.default_groups.values())
    assert len(groups) == 4
    assert groups[0].categories == {"x"}
    assert groups[1].categories == {"y"}
    assert groups[2].categories == set()
    assert groups[3].categories == set()


def test_rename_iteration_trims_name(mock_session_repos):
    iter_repo, *_ = mock_session_repos
    iter_id = IterationID(1)
    iter_repo.iterations[iter_id] = CategoricalSingleVarIteration(
        uid=iter_id,
        name="Old Name",
        variable_name="bucket",
    )

    iter_repo.rename_iteration(iter_id, "  New Name  ")

    assert iter_repo.iterations[iter_id].name == "New Name"


def test_rename_iteration_raises_for_missing_id(mock_session_repos):
    iter_repo, *_ = mock_session_repos

    with pytest.raises(ValueError, match="does not exist"):
        iter_repo.rename_iteration(IterationID(999), "Renamed")


def test_add_double_var_iteration_non_auto_initializes_defaults(tmp_path):
    data_repo = DataRepository()
    csv_path = tmp_path / "double_non_auto.csv"
    pd.DataFrame({
        "root_score": [10, 20, 30, 40, 50, 60, 70, 80],
        "child_band": [1, 1, 2, 2, 3, 3, 4, 4],
    }).to_csv(csv_path, index=False)
    data_repo.add_data_source("Dev Data", csv_path, ReadConfig())

    filter_repo = FilterRepository(data_repo)
    metric_repo = MetricRepository(data_repo)
    option_repo = OptionRepository()
    scalar_repo = ScalarRepository()
    iter_repo = IterationsRepository(
        data_repo,
        filter_repo,
        metric_repo,
        option_repo,
        scalar_repo,
    )

    root = iter_repo.add_single_var_iteration(
        name="Root",
        variable_name="root_score",
        variable_dtype=VariableType.NUMERICAL,
        selected_segment_ids=[RiskSegmentID(0), RiskSegmentID(1), RiskSegmentID(2)],
        loss_rate_type=LossRateTypes.DLR,
        filter_ids=[],
        auto_band=False,
        use_scalar=False,
        remove_outliers=False,
    )

    child = iter_repo.add_double_var_iteration(
        name="Child",
        previous_iteration_id=root.uid,
        variable_name="child_band",
        variable_dtype=VariableType.NUMERICAL,
        loss_rate_type=LossRateTypes.DLR,
        filter_ids=[],
        auto_band=False,
        use_scalar=False,
        remove_outliers=False,
    )

    assert isinstance(child, NumericalDoubleVarIteration)
    assert child.default_groups
    assert child.groups
    assert child.groups_mask
    assert all(child.groups_mask.values())
    assert child.default_risk_segment_grid
    assert child.risk_segment_grid

    parent_segments = list(root.risk_segment_details.segments.keys())
    for row in child.default_risk_segment_grid.values():
        assert list(row.keys()) == parent_segments
        for seg_id in parent_segments:
            assert row[seg_id] == seg_id


def test_add_double_var_iteration_auto_band_requires_limits(tmp_path):
    data_repo = DataRepository()
    csv_path = tmp_path / "double_requires_limits.csv"
    pd.DataFrame({
        "root_score": [10, 20, 30, 40],
        "child_score": [100, 200, 300, 400],
    }).to_csv(csv_path, index=False)
    data_repo.add_data_source("Dev Data", csv_path, ReadConfig())

    filter_repo = FilterRepository(data_repo)
    metric_repo = MetricRepository(data_repo)
    option_repo = OptionRepository()
    scalar_repo = ScalarRepository()
    iter_repo = IterationsRepository(
        data_repo,
        filter_repo,
        metric_repo,
        option_repo,
        scalar_repo,
    )

    root = iter_repo.add_single_var_iteration(
        name="Root",
        variable_name="root_score",
        variable_dtype=VariableType.NUMERICAL,
        selected_segment_ids=[RiskSegmentID(0), RiskSegmentID(1), RiskSegmentID(2)],
        loss_rate_type=LossRateTypes.DLR,
        filter_ids=[],
        auto_band=False,
        use_scalar=False,
        remove_outliers=False,
    )

    with pytest.raises(ValueError, match="must be set for auto banding"):
        iter_repo.add_double_var_iteration(
            name="Child",
            previous_iteration_id=root.uid,
            variable_name="child_score",
            variable_dtype=VariableType.NUMERICAL,
            loss_rate_type=LossRateTypes.DLR,
            filter_ids=[],
            auto_band=True,
            use_scalar=False,
            remove_outliers=False,
            upgrade_limit=None,
            downgrade_limit=None,
            auto_rank_ordering=False,
        )


def test_add_double_var_iteration_auto_band_respects_upgrade_downgrade_limits(tmp_path):
    data_repo = DataRepository()
    csv_path = tmp_path / "double_auto_limits.csv"
    pd.DataFrame({
        "root_score": [10, 20, 30, 40, 50, 60, 70, 80, 90, 100],
        "child_score": [3, 7, 11, 15, 19, 23, 27, 31, 35, 39],
        "dlr_bad": [1, 1, 2, 2, 3, 3, 4, 4, 5, 5],
        "avg_bal": [100, 100, 100, 100, 100, 100, 100, 100, 100, 100],
    }).to_csv(csv_path, index=False)
    data_repo.add_data_source("Dev Data", csv_path, ReadConfig())

    filter_repo = FilterRepository(data_repo)
    metric_repo = MetricRepository(data_repo)
    option_repo = OptionRepository()
    scalar_repo = ScalarRepository()
    iter_repo = IterationsRepository(
        data_repo,
        filter_repo,
        metric_repo,
        option_repo,
        scalar_repo,
    )

    data_source_ids = list(data_repo.data_sources.keys())
    metric_repo.dev_data_source_ids = data_source_ids
    metric_repo.var_dev_dlr_bad = "dlr_bad"
    metric_repo.var_dev_avg_bal = "avg_bal"

    root = iter_repo.add_single_var_iteration(
        name="Root",
        variable_name="root_score",
        variable_dtype=VariableType.NUMERICAL,
        selected_segment_ids=[RiskSegmentID(0), RiskSegmentID(1), RiskSegmentID(2)],
        loss_rate_type=LossRateTypes.DLR,
        filter_ids=[],
        auto_band=False,
        use_scalar=False,
        remove_outliers=False,
    )

    child = iter_repo.add_double_var_iteration(
        name="Child",
        previous_iteration_id=root.uid,
        variable_name="child_score",
        variable_dtype=VariableType.NUMERICAL,
        loss_rate_type=LossRateTypes.DLR,
        filter_ids=[],
        auto_band=True,
        use_scalar=False,
        remove_outliers=False,
        upgrade_limit=1,
        downgrade_limit=1,
        auto_rank_ordering=False,
    )

    assert isinstance(child, NumericalDoubleVarIteration)
    assert child.default_groups
    assert child.default_risk_segment_grid

    segment_order = list(root.risk_segment_details.segments.keys())
    seg_pos = {seg_id: idx for idx, seg_id in enumerate(segment_order)}

    for row in child.default_risk_segment_grid.values():
        for parent_seg, target_seg in row.items():
            delta = abs(seg_pos[target_seg] - seg_pos[parent_seg])
            assert delta <= 1


def test_add_double_var_iteration_auto_band_categorical_initializes_grid(tmp_path):
    data_repo = DataRepository()
    csv_path = tmp_path / "double_auto_categorical.csv"
    pd.DataFrame({
        "root_score": [10, 20, 30, 40, 50, 60, 70, 80],
        "child_bucket": ["A", "A", "B", "B", "C", "C", "D", "D"],
        "unt_bad": [0, 1, 0, 1, 2, 2, 3, 3],
    }).to_csv(csv_path, index=False)
    data_repo.add_data_source("Dev Data", csv_path, ReadConfig())

    filter_repo = FilterRepository(data_repo)
    metric_repo = MetricRepository(data_repo)
    option_repo = OptionRepository()
    scalar_repo = ScalarRepository()
    iter_repo = IterationsRepository(
        data_repo,
        filter_repo,
        metric_repo,
        option_repo,
        scalar_repo,
    )

    data_source_ids = list(data_repo.data_sources.keys())
    metric_repo.dev_data_source_ids = data_source_ids
    metric_repo.var_dev_unt_bad = "unt_bad"

    root = iter_repo.add_single_var_iteration(
        name="Root",
        variable_name="root_score",
        variable_dtype=VariableType.NUMERICAL,
        selected_segment_ids=[RiskSegmentID(0), RiskSegmentID(1), RiskSegmentID(2)],
        loss_rate_type=LossRateTypes.ULR,
        filter_ids=[],
        auto_band=False,
        use_scalar=False,
        remove_outliers=False,
    )

    child = iter_repo.add_double_var_iteration(
        name="ChildCat",
        previous_iteration_id=root.uid,
        variable_name="child_bucket",
        variable_dtype=VariableType.CATEGORICAL,
        loss_rate_type=LossRateTypes.ULR,
        filter_ids=[],
        auto_band=True,
        use_scalar=False,
        remove_outliers=False,
        upgrade_limit=1,
        downgrade_limit=1,
        auto_rank_ordering=True,
    )

    assert isinstance(child, CategoricalDoubleVarIteration)
    assert child.default_groups
    assert child.default_risk_segment_grid
    assert all(child.groups_mask.values())


def test_double_var_grid_helpers_and_group_selection(tmp_path):
    data_repo = DataRepository()
    csv_path = tmp_path / "double_grid_helpers.csv"
    pd.DataFrame({
        "root_score": [10, 20, 30, 40, 50, 60, 70, 80],
        "child_band": [1, 1, 2, 2, 3, 3, 4, 4],
    }).to_csv(csv_path, index=False)
    data_repo.add_data_source("Dev Data", csv_path, ReadConfig())

    filter_repo = FilterRepository(data_repo)
    metric_repo = MetricRepository(data_repo)
    option_repo = OptionRepository()
    scalar_repo = ScalarRepository()
    iter_repo = IterationsRepository(
        data_repo,
        filter_repo,
        metric_repo,
        option_repo,
        scalar_repo,
    )

    root = iter_repo.add_single_var_iteration(
        name="Root",
        variable_name="root_score",
        variable_dtype=VariableType.NUMERICAL,
        selected_segment_ids=[RiskSegmentID(0), RiskSegmentID(1), RiskSegmentID(2)],
        loss_rate_type=LossRateTypes.DLR,
        filter_ids=[],
        auto_band=False,
        use_scalar=False,
        remove_outliers=False,
    )
    child = iter_repo.add_double_var_iteration(
        name="Child",
        previous_iteration_id=root.uid,
        variable_name="child_band",
        variable_dtype=VariableType.NUMERICAL,
        loss_rate_type=LossRateTypes.DLR,
        filter_ids=[],
        auto_band=False,
        use_scalar=False,
        remove_outliers=False,
    )

    grid_df = iter_repo.get_risk_segment_grid(
        child.uid,
        default=False,
        details_column=RSDetCol.RISK_SEGMENT,
    )
    expected_columns = [
        segment.name for segment in root.risk_segment_details.segments.values()
    ]
    assert list(grid_df.columns) == expected_columns

    groups_df = iter_repo.get_all_groups(child.uid)
    assert RSDetCol.SELECTED.value in groups_df.columns

    selected_group_ids = [GroupID(0), GroupID(1)]
    iter_repo.select_groups(child.uid, selected_group_ids)
    filtered_controls = iter_repo.get_controls(child.uid, default=False)
    assert filtered_controls.index.to_list() == selected_group_ids

    before_count = len(iter_repo.get_all_groups(child.uid))
    iter_repo.add_new_group(child.uid)
    after_groups = iter_repo.get_all_groups(child.uid)
    assert len(after_groups) == before_count + 1
    assert after_groups.iloc[-1][RSDetCol.SELECTED.value]


def test_add_single_var_iteration_finite_upper_bound_validation(tmp_path):
    data_repo = DataRepository()
    csv_path = tmp_path / "data.csv"
    pd.DataFrame({"score": [10, 20, 30]}).to_csv(csv_path, index=False)
    data_repo.add_data_source("Dev Data", csv_path, ReadConfig())

    filter_repo = FilterRepository(data_repo)
    metric_repo = MetricRepository(data_repo)
    option_repo = OptionRepository()
    scalar_repo = ScalarRepository()
    iter_repo = IterationsRepository(
        data_repo,
        filter_repo,
        metric_repo,
        option_repo,
        scalar_repo,
    )

    # Selecting only segments with infinite upper rate (5A=8, 5B=9) must raise ValueError
    with pytest.raises(
        ValueError, match="at least 1 risk segment with a finite upper bound must be selected"
    ):
        iter_repo.add_single_var_iteration(
            name="Invalid",
            variable_name="score",
            variable_dtype=VariableType.NUMERICAL,
            selected_segment_ids=[RiskSegmentID(8), RiskSegmentID(9)],
            loss_rate_type=LossRateTypes.DLR,
            filter_ids=[],
            auto_band=False,
            use_scalar=False,
            remove_outliers=False,
        )

    # Selecting empty segment IDs must also raise ValueError
    with pytest.raises(
        ValueError, match="at least 1 risk segment with a finite upper bound must be selected"
    ):
        iter_repo.add_single_var_iteration(
            name="EmptySegments",
            variable_name="score",
            variable_dtype=VariableType.NUMERICAL,
            selected_segment_ids=[],
            loss_rate_type=LossRateTypes.DLR,
            filter_ids=[],
            auto_band=False,
            use_scalar=False,
            remove_outliers=False,
        )

