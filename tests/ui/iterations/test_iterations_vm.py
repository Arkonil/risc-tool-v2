"""Unit tests for IterationsViewModel."""

import pandas as pd

from risc_tool.data.models.data_source import ReadConfig
from risc_tool.data.models.enums import LossRateTypes, VariableType
from risc_tool.data.models.iteration import CategoricalSingleVarIteration
from risc_tool.data.models.types import GroupID, IterationID, MetricID, RiskSegmentID
from risc_tool.data.repositories.data import DataRepository
from risc_tool.data.repositories.filter import FilterRepository
from risc_tool.data.repositories.iterations import IterationsRepository
from risc_tool.data.repositories.metric import MetricRepository
from risc_tool.data.repositories.options import OptionRepository
from risc_tool.data.repositories.scalar import ScalarRepository
from risc_tool.ui.iterations.iterations_vm import IterationsViewModel


def test_current_status_default():
    d = DataRepository()
    f = FilterRepository(d)
    m = MetricRepository(d)
    o = OptionRepository()
    s = ScalarRepository()
    i = IterationsRepository(d, f, m, o, s)

    vm = IterationsViewModel(d, i, o, f, m, s)
    status, iter_id = vm.current_status
    assert status == "graph"
    assert iter_id is None


def test_navigation_state_management():
    d = DataRepository()
    f = FilterRepository(d)
    m = MetricRepository(d)
    o = OptionRepository()
    s = ScalarRepository()
    i = IterationsRepository(d, f, m, o, s)

    vm = IterationsViewModel(d, i, o, f, m, s)
    vm.set_current_status("create", iteration_create_parent_id=None)
    status, _ = vm.current_status
    assert status == "create"


def test_rename_iteration_keeps_graph_selection(tmp_path):
    d = DataRepository()
    csv_path = tmp_path / "sample.csv"
    pd.DataFrame({"bucket": ["a", "b", "a"]}).to_csv(csv_path, index=False)
    d.add_data_source("Dev Data", csv_path, ReadConfig())

    f = FilterRepository(d)
    m = MetricRepository(d)
    o = OptionRepository()
    s = ScalarRepository()
    i = IterationsRepository(d, f, m, o, s)

    iter_id = IterationID(1)
    i.iterations[iter_id] = CategoricalSingleVarIteration(
        uid=iter_id,
        name="Old Name",
        variable_name="bucket",
    )

    vm = IterationsViewModel(d, i, o, f, m, s)
    vm.set_current_status("graph", selected_iteration_id=iter_id)

    vm.rename_iteration(iter_id, "  New Name  ")

    assert vm.get_iteration_name(iter_id) == "New Name"
    status, selected_id = vm.current_status
    assert status == "graph"
    assert selected_id == iter_id


def test_double_var_group_helpers_return_change_status(tmp_path):
    d = DataRepository()
    csv_path = tmp_path / "sample.csv"
    pd.DataFrame({"score": [10, 20, 30, 40], "band": [1, 2, 3, 4]}).to_csv(
        csv_path,
        index=False,
    )
    d.add_data_source("Dev Data", csv_path, ReadConfig())

    f = FilterRepository(d)
    m = MetricRepository(d)
    o = OptionRepository()
    s = ScalarRepository()
    i = IterationsRepository(d, f, m, o, s)
    vm = IterationsViewModel(d, i, o, f, m, s)

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
        variable_name="band",
        variable_dtype=VariableType.NUMERICAL,
        auto_band=False,
        use_scalar=False,
        remove_outliers=False,
    )
    vm.set_metadata(child.uid, metric_ids=[MetricID.DEV_VOLUME])

    assert vm.select_groups(child.uid, [GroupID(0), GroupID(1)])
    assert not vm.select_groups(child.uid, [GroupID(0), GroupID(1)])
    assert vm.add_new_group(child.uid)

    editable_grid = vm.get_editable_grid(child.uid, default=False, editable=True)
    assert "styler" in editable_grid
