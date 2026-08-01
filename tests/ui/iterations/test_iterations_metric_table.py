"""Unit tests for get_iteration_metric_table in IterationsViewModel and IterationsRepository."""

from typing import cast

import pandas as pd
import pytest
from pandas.io.formats.style import Styler

from risc_tool.data.models.data_source import ReadConfig
from risc_tool.data.models.enums import LossRateTypes, VariableType
from risc_tool.data.models.types import MetricID, RiskSegmentID
from risc_tool.data.repositories.data import DataRepository
from risc_tool.data.repositories.filter import FilterRepository
from risc_tool.data.repositories.iterations import IterationsRepository
from risc_tool.data.repositories.metric import MetricRepository
from risc_tool.data.repositories.options import OptionRepository
from risc_tool.data.repositories.scalar import ScalarRepository
from risc_tool.ui.iterations.iterations_vm import IterationsViewModel


@pytest.fixture
def session_env(tmp_path):
    df = pd.DataFrame({
        "score": [650, 700, 720, 800, 600, 750],
        "bad": [1, 0, 0, 0, 1, 0],
        "bal": [100.0, 200.0, 150.0, 300.0, 50.0, 250.0],
    })
    csv_path = tmp_path / "test_data.csv"
    df.to_csv(csv_path, index=False)

    data_repo = DataRepository()
    ds1 = data_repo.add_data_source("Dev Data", csv_path, ReadConfig())

    filter_repo = FilterRepository(data_repo)
    metric_repo = MetricRepository(data_repo)
    option_repo = OptionRepository()
    scalar_repo = ScalarRepository()
    iter_repo = IterationsRepository(
        data_repo, filter_repo, metric_repo, option_repo, scalar_repo
    )

    metric_repo._dev_data_source_ids = [ds1.uid]
    metric_repo._var_dev_dlr_bad = "bad"
    metric_repo._var_dev_unt_bad = "bad"
    metric_repo._var_dev_avg_bal = "bal"
    metric_repo._current_rate_mob = 12

    vm = IterationsViewModel(
        data_repository=data_repo,
        iterations_repository=iter_repo,
        options_repository=option_repo,
        filter_repository=filter_repo,
        metric_repository=metric_repo,
        scalar_repository=scalar_repo,
    )

    return vm, iter_repo, metric_repo


def test_get_iteration_metric_table_single_var(session_env):
    vm, iter_repo, metric_repo = session_env

    iter_obj = iter_repo.add_single_var_iteration(
        name="Score Iteration",
        variable_name="score",
        variable_dtype=VariableType.NUMERICAL,
        selected_segment_ids=[RiskSegmentID(0), RiskSegmentID(1)],
        loss_rate_type=LossRateTypes.DLR,
        filter_ids=[],
        auto_band=False,
        use_scalar=False,
        remove_outliers=False,
    )

    metric_id = MetricID.DEV_VOLUME

    styler, errors, warnings = vm.get_iteration_metric_table(
        iteration_id=iter_obj.uid,
        default=True,
        show_controls=True,
        filter_ids=[],
        metric_ids=[metric_id],
        scalars_enabled=False,
        remove_outliers=False,
        show_total_row=True,
        theme="dark",
    )

    assert isinstance(styler, Styler)
    assert isinstance(errors, list)
    assert isinstance(warnings, list)
    assert not errors

    raw_df = cast(pd.DataFrame, getattr(styler, "data"))
    assert "Risk Segment" in raw_df.columns
    assert "Lower Bound" in raw_df.columns
    assert "Upper Bound" in raw_df.columns


def test_get_categorical_iteration_options(session_env):
    vm, iter_repo, _ = session_env

    iter_obj = iter_repo.add_single_var_iteration(
        name="Score Iteration",
        variable_name="score",
        variable_dtype=VariableType.NUMERICAL,
        selected_segment_ids=[RiskSegmentID(0)],
        loss_rate_type=LossRateTypes.DLR,
        filter_ids=[],
        auto_band=False,
        use_scalar=False,
        remove_outliers=False,
    )

    opts = vm.get_categorical_iteration_options(iter_obj.uid)
    assert opts == []


def test_get_metric_grids_double_var(session_env):
    vm, _, _ = session_env

    root = vm.add_single_var_iteration(
        name="Root",
        variable_name="score",
        variable_dtype=VariableType.NUMERICAL,
        selected_segment_ids=[RiskSegmentID(0), RiskSegmentID(1)],
        loss_rate_type=LossRateTypes.DLR,
        filter_ids=[],
        auto_band=False,
        use_scalar=False,
        remove_outliers=False,
    )
    child = vm.add_double_var_iteration(
        name="Child",
        previous_iteration_id=root.uid,
        variable_name="bal",
        variable_dtype=VariableType.NUMERICAL,
        auto_band=False,
        use_scalar=False,
        remove_outliers=False,
    )
    vm.set_metadata(child.uid, metric_ids=[MetricID.DEV_VOLUME])

    metric_views, errors, warnings = vm.get_metric_grids(
        iteration_id=child.uid,
        default=True,
        show_controls_idx="all",
        show_total_row=True,
        show_total_column=True,
        theme="dark",
    )

    assert isinstance(errors, list)
    assert isinstance(warnings, list)
    assert len(metric_views) == 1

    raw_df = cast(pd.DataFrame, getattr(metric_views[0]["metric_styler"], "data"))
    assert "Total" in raw_df.columns.get_level_values(-1).tolist()
