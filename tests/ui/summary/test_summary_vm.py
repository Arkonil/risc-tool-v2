"""Unit tests for SummaryViewModel."""

from pathlib import Path
from uuid import uuid4

import pandas as pd

from risc_tool.data.models.data_source import ReadConfig
from risc_tool.data.models.enums import Signature, SummaryPageTabName
from risc_tool.data.models.iteration import CategoricalSingleVarIteration
from risc_tool.data.models.types import IterationID, MetricID
from risc_tool.data.repositories.data import DataRepository
from risc_tool.data.repositories.filter import FilterRepository
from risc_tool.data.repositories.iterations import IterationsRepository
from risc_tool.data.repositories.metric import MetricRepository
from risc_tool.data.repositories.options import OptionRepository
from risc_tool.data.repositories.scalar import ScalarRepository
from risc_tool.ui.summary.summary_vm import SummaryViewModel


def _write_csv(path: Path, contents: str) -> None:
    """Write CSV content to a file for test setup."""
    path.write_text(contents, encoding="utf-8")


def _make_repositories(
    data_repository: DataRepository | None = None,
) -> tuple[DataRepository, FilterRepository, MetricRepository, IterationsRepository]:
    """Build repositories sharing a common DataRepository."""
    d = data_repository if data_repository is not None else DataRepository()
    f = FilterRepository(d)
    m = MetricRepository(d)
    o = OptionRepository()
    s = ScalarRepository()
    i = IterationsRepository(d, f, m, o, s)
    return d, f, m, i


def test_summary_vm_initialization():
    d = DataRepository()
    f = FilterRepository(d)
    m = MetricRepository(d)
    o = OptionRepository()
    s = ScalarRepository()
    i = IterationsRepository(d, f, m, o, s)

    vm = SummaryViewModel(d, f, m, i)

    assert vm.signature == Signature.SUMMARY_VIEW_MODEL
    assert vm.tab_names == [
        SummaryPageTabName.OVERVIEW,
        SummaryPageTabName.COMPARISON,
        SummaryPageTabName.PIVOT,
    ]
    assert vm.current_tab_name == SummaryPageTabName.OVERVIEW
    assert vm.no_iteration is True
    assert vm.sample_loaded is False


def test_summary_vm_metric_selection():
    d = DataRepository()
    f = FilterRepository(d)
    m = MetricRepository(d)
    o = OptionRepository()
    s = ScalarRepository()
    i = IterationsRepository(d, f, m, o, s)

    vm = SummaryViewModel(d, f, m, i)

    new_overview_metrics = [MetricID.DEV_VOLUME]
    vm.set_overview_metrics(new_overview_metrics)
    assert vm.ov_metric_ids == [MetricID.DEV_VOLUME]

    new_comparison_metrics = [MetricID.DEV_DLR_BAD_RATE]
    vm.set_comparison_metrics(new_comparison_metrics)
    assert vm.cv_metric_ids == [MetricID.DEV_DLR_BAD_RATE]


def test_summary_vm_comparison_view_management():
    d = DataRepository()
    f = FilterRepository(d)
    m = MetricRepository(d)
    o = OptionRepository()
    s = ScalarRepository()
    i = IterationsRepository(d, f, m, o, s)

    vm = SummaryViewModel(d, f, m, i)

    iter_1 = IterationID(1)
    iter_2 = IterationID(2)

    vm.add_iteration_view(iter_1, default=False)
    assert len(vm.cv_selected_iterations) == 1

    view_idx = next(iter(vm.cv_selected_iterations.keys()))
    assert vm.cv_selected_iterations[view_idx] == (iter_1, False)

    vm.edit_iteration_view(view_idx, iter_2, default=True)
    assert vm.cv_selected_iterations[view_idx] == (iter_2, True)

    vm.remove_iteration_view(view_idx)
    assert len(vm.cv_selected_iterations) == 0


def test_summary_vm_dependency_pruning(tmp_path):
    d = DataRepository()
    csv_path = tmp_path / "sample.csv"
    pd.DataFrame({"score": [10, 20]}).to_csv(csv_path, index=False)
    d.add_data_source("Dev Data", csv_path, ReadConfig())

    f = FilterRepository(d)
    m = MetricRepository(d)
    o = OptionRepository()
    s = ScalarRepository()
    i = IterationsRepository(d, f, m, o, s)

    iter_id = IterationID(1)
    i.iterations[iter_id] = CategoricalSingleVarIteration(
        uid=iter_id,
        name="Iter 1",
        variable_name="score",
    )

    vm = SummaryViewModel(d, f, m, i)
    vm.ov_selected_iteration_id = iter_id
    vm.add_iteration_view(iter_id, default=False)

    assert vm.no_iteration is False

    # Delete iteration from repository and notify
    del i.iterations[iter_id]
    i.notify_subscribers()

    # Verify pruned state
    assert vm.ov_selected_iteration_id is None
    assert len(vm.cv_selected_iterations) == 0


def test_summary_vm_pivot_metric_selection():
    d, f, m, i = _make_repositories()
    vm = SummaryViewModel(d, f, m, i)

    assert vm.pv_metric_ids == []

    vm.set_pivot_metrics([MetricID.DEV_VOLUME])
    assert vm.pv_metric_ids == [MetricID.DEV_VOLUME]


def test_summary_vm_pivot_variable_positions():
    d, f, m, i = _make_repositories()
    vm = SummaryViewModel(d, f, m, i)

    row_vars = ["score"]
    vm.set_pivot_variables("row", row_vars)
    assert vm.pv_row_vars == row_vars

    col_vars = ["age"]
    vm.set_pivot_variables("col", col_vars)
    assert vm.pv_col_vars == col_vars

    vm.set_pivot_variables("invalid", ["bad"])
    assert vm.pv_row_vars == row_vars
    assert vm.pv_col_vars == col_vars


def test_summary_vm_refresh_cache_without_data():
    d, f, m, i = _make_repositories()
    vm = SummaryViewModel(d, f, m, i)

    assert vm.pivot_variables == {}


def test_summary_vm_refresh_cache_includes_iteration_options():
    d, f, m, i = _make_repositories()
    iter_id = IterationID(1)
    i.iterations[iter_id] = CategoricalSingleVarIteration(
        uid=iter_id,
        name="Iter 1",
        variable_name="score",
    )

    vm = SummaryViewModel(d, f, m, i)

    assert (iter_id, True) in vm.pivot_variables
    assert (iter_id, False) in vm.pivot_variables


def test_summary_vm_refresh_cache_includes_low_cardinality_columns(tmp_path):
    csv_path = tmp_path / "sample.csv"
    rows = "\n".join(f"{'abc'[idx % 3]},{idx + 1}" for idx in range(20))
    _write_csv(csv_path, f"category,id\n{rows}\n")

    d = DataRepository()
    d.add_data_source("Dev Data", csv_path, ReadConfig())
    d, f, m, i = _make_repositories(data_repository=d)

    vm = SummaryViewModel(d, f, m, i)

    assert "category" in vm.pivot_variables
    assert "id" not in vm.pivot_variables


def test_summary_vm_data_loaded_flips_with_data(tmp_path):
    d, f, m, i = _make_repositories()
    vm = SummaryViewModel(d, f, m, i)

    assert vm.data_loaded is False
    assert vm.sample_loaded is False

    csv_path = tmp_path / "sample.csv"
    _write_csv(csv_path, "score\n10\n20\n")
    d.add_data_source("Dev Data", csv_path, ReadConfig())

    assert vm.data_loaded is True
    assert vm.sample_loaded is True


def test_summary_vm_get_metric_returns_metric(tmp_path):
    csv_path = tmp_path / "sample.csv"
    _write_csv(csv_path, "score\n10\n20\n")

    d = DataRepository()
    d.add_data_source("Dev Data", csv_path, ReadConfig())
    d, f, m, i = _make_repositories(data_repository=d)

    vm = SummaryViewModel(d, f, m, i)

    metric = vm.get_metric(MetricID.DEV_VOLUME)
    assert metric.uid == MetricID.DEV_VOLUME


def test_summary_vm_default_state():
    d, f, m, i = _make_repositories()
    vm = SummaryViewModel(d, f, m, i)

    assert vm.ov_scalars_enabled is True
    assert vm.ov_remove_outliers is True
    assert vm.cv_scalars_enabled is True
    assert vm.cv_remove_outliers is True
    assert vm.cv_view_mode == "list"
    assert vm.ov_selected_iteration_id is None
    assert vm.ov_selected_iteration_default is False
    assert vm.ov_filter_ids == []
    assert vm.cv_filter_ids == []
    assert vm.pv_filter_ids == []
    assert vm.pv_metric_ids == []
    assert vm.pv_row_vars == []
    assert vm.pv_col_vars == []
    assert vm.cv_selected_iterations == {}


def test_summary_vm_add_iteration_view_unique_ids():
    d, f, m, i = _make_repositories()
    vm = SummaryViewModel(d, f, m, i)

    iter_id = IterationID(1)
    vm.add_iteration_view(iter_id, default=False)
    vm.add_iteration_view(iter_id, default=False)

    assert len(vm.cv_selected_iterations) == 2
    assert len(set(vm.cv_selected_iterations.keys())) == 2
    assert all(
        value == (iter_id, False) for value in vm.cv_selected_iterations.values()
    )


def test_summary_vm_remove_iteration_view_missing_key():
    d, f, m, i = _make_repositories()
    vm = SummaryViewModel(d, f, m, i)

    iter_id = IterationID(1)
    vm.add_iteration_view(iter_id, default=False)
    existing_view_idx = next(iter(vm.cv_selected_iterations.keys()))

    vm.remove_iteration_view(uuid4())

    assert len(vm.cv_selected_iterations) == 1
    assert existing_view_idx in vm.cv_selected_iterations


def test_summary_vm_prunes_metric_ids(tmp_path):
    csv_path = tmp_path / "sample.csv"
    _write_csv(csv_path, "score\n10\n20\n")

    d = DataRepository()
    d.add_data_source("Dev Data", csv_path, ReadConfig())
    d, f, m, i = _make_repositories(data_repository=d)

    vm = SummaryViewModel(d, f, m, i)

    before_metric_ids = set(m.metrics.keys())
    m.duplicate_metric(MetricID.DEV_VOLUME)
    new_metric_ids = set(m.metrics.keys()) - before_metric_ids
    assert len(new_metric_ids) == 1
    new_metric_id = new_metric_ids.pop()

    vm.ov_metric_ids = [new_metric_id]
    vm.cv_metric_ids = [new_metric_id]
    vm.pv_metric_ids = [new_metric_id]

    m.remove_metric(new_metric_id)

    assert vm.ov_metric_ids == []
    assert vm.cv_metric_ids == []
    assert vm.pv_metric_ids == []


def test_summary_vm_prunes_filter_ids(tmp_path):
    csv_path = tmp_path / "sample.csv"
    _write_csv(csv_path, "score\n10\n20\n30\n")

    d = DataRepository()
    d.add_data_source("Dev Data", csv_path, ReadConfig())
    d, f, m, i = _make_repositories(data_repository=d)

    vm = SummaryViewModel(d, f, m, i)

    f.create_filter("Test Filter", "score > 5")
    assert len(f.filters) == 1
    filter_id = next(iter(f.filters.keys()))

    vm.ov_filter_ids = [filter_id]
    vm.cv_filter_ids = [filter_id]
    vm.pv_filter_ids = [filter_id]

    f.remove_filter(filter_id)

    assert vm.ov_filter_ids == []
    assert vm.cv_filter_ids == []
    assert vm.pv_filter_ids == []


def test_summary_vm_prunes_pivot_variables(tmp_path):
    csv_path = tmp_path / "sample.csv"
    _write_csv(csv_path, "score\n10\n20\n")

    d = DataRepository()
    d.add_data_source("Dev Data", csv_path, ReadConfig())
    d, f, m, i = _make_repositories(data_repository=d)

    iter_id = IterationID(1)
    i.iterations[iter_id] = CategoricalSingleVarIteration(
        uid=iter_id,
        name="Iter 1",
        variable_name="score",
    )

    vm = SummaryViewModel(d, f, m, i)
    vm.pv_row_vars = ["score", (iter_id, False)]

    del i.iterations[iter_id]
    i.notify_subscribers()

    assert vm.pv_row_vars == ["score"]


def test_summary_vm_get_pivot_tables(tmp_path):
    csv_path = tmp_path / "sample.csv"
    _write_csv(csv_path, "score,group\n10,A\n20,B\n30,A\n40,B\n")

    d = DataRepository()
    d.add_data_source("Dev Data", csv_path, ReadConfig())
    d, f, m, i = _make_repositories(data_repository=d)
    m.dev_data_source_ids = list(d.data_sources.keys())

    vm = SummaryViewModel(d, f, m, i)
    vm.set_pivot_metrics([MetricID.DEV_VOLUME])
    vm.set_pivot_variables("row", ["group"])

    tables = vm.get_pivot_tables()
    assert len(tables) == 1
    assert isinstance(tables[0], pd.DataFrame)
    assert not tables[0].empty

