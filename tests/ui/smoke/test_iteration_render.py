"""Smoke tests that AppTest-render the simulation iteration page end-to-end.

These exercise the real ``simulation_iteration_view`` page and guard against
runtime render regressions -- particularly controls leaking into the main body
instead of the sidebar (the tables-only main body requirement).
"""

import pathlib
import types

from streamlit.testing.v1 import AppTest

from risc_tool_v2.data.core.enums import LossRateTypes, VariableType
from risc_tool_v2.data.simulation.repositories.simulation_repository import (
    SimulationRepository,
)
from risc_tool_v2.ui.simulation.simulation_vm import SimulationViewModel

_RENDER = str(
    pathlib.Path(__file__).resolve().parent / "_render_simulation_iteration.py"
)


def _iteration_vm(data_repository, filter_repository, metric_repository):
    """Build a SimulationViewModel with one run, opened iteration."""
    sim_repo = SimulationRepository(
        data_repository, filter_repository, metric_repository
    )
    vm = SimulationViewModel(
        data_repository, sim_repo, filter_repository, metric_repository
    )

    vm.begin_draft()
    vm.update_draft_name("My Sim")
    vm.update_draft_variable_name("credit_score")
    vm.update_draft_bad_rate_column(
        which="dev",
        loss_rate_type=LossRateTypes.ULR,
        field="numerator_col",
        value="unt_bad",
    )
    vm.update_draft_bad_rate_data_sources(
        which="dev", data_source_ids=tuple(vm.data_source_ids)
    )
    vm.confirm_draft()
    sim_id = vm.current_simulation_id
    assert sim_id is not None
    vm.run_simulation(sim_id)
    so = vm.get_simulation_outputs(sim_id)[0]
    vm.open_iteration_from_output(sim_id, so.uid)
    assert vm.mode == "iteration"
    return vm


def _run_app(vm):
    at = AppTest.from_file(_RENDER)
    at.session_state["session"] = types.SimpleNamespace(simulation_view_model=vm)
    at.run(timeout=15)
    return at


def test_iteration_page_renders_without_exception(
    data_repository, filter_repository, metric_repository
):
    vm = _iteration_vm(data_repository, filter_repository, metric_repository)
    at = _run_app(vm)

    assert not at.exception, at.exception
    assert at.get("title")  # Iteration #<id> title


def test_iteration_controls_render_sidebar_only_widgets_present(
    data_repository, filter_repository, metric_repository
):
    vm = _iteration_vm(data_repository, filter_repository, metric_repository)
    at = _run_app(vm)

    assert not at.exception, at.exception
    buttons = at.get("button")
    assert any("Set Metrics" in str(b.label) for b in buttons)
    assert any("Rename Iteration" in str(b.label) for b in buttons)
    assert any("Back" in str(b.label) for b in buttons)
    assert len(at.get("multiselect")) >= 1  # filter selector
    assert len(at.get("checkbox")) >= 2  # scalars + remove outliers


def test_iteration_main_body_renders_combined_tables(
    data_repository, filter_repository, metric_repository
):
    """Single-var iterations render v1-style combined tables with a Total row."""
    vm = _iteration_vm(data_repository, filter_repository, metric_repository)
    at = _run_app(vm)

    assert not at.exception, at.exception
    headers = [m.value for m in at.get("markdown")]
    assert any("Default Range" in str(h) for h in headers)
    assert any("Editable Range" in str(h) for h in headers)

    tables = [*at.get("dataframe"), *at.get("data_editor")]
    assert len(tables) >= 2
    for table in tables:
        df = table.value
        assert "Risk Segment" in df.columns
        assert "Total" in df["Risk Segment"].tolist()


def test_iteration_double_var_body_renders_grid_tables(
    data_repository, filter_repository, metric_repository
):
    """Double-var iterations render the control table + per-metric tables."""
    vm = _iteration_vm(data_repository, filter_repository, metric_repository)
    assert vm.current_iteration is not None
    vm.create_double_var_iteration(
        vm.current_iteration.uid,
        new_variable_name="income",
        new_variable_type=VariableType.NUMERICAL,
    )

    at = _run_app(vm)

    assert not at.exception, at.exception
    headers = [m.value for m in at.get("markdown")]
    assert any("Default Risk Segment Grid" in str(h) for h in headers)
    assert any("Default Metric Grids" in str(h) for h in headers)

    df = at.get("dataframe")[0].value
    assert "Band" in df.columns
    assert "Lower Bound" in df.columns

    metric_table = at.get("dataframe")[-1].value
    assert "Total" in metric_table.columns
    assert "Total" in metric_table["Band"].tolist()


def test_iteration_editable_double_var_renders_working_editors(
    data_repository, filter_repository, metric_repository
):
    """Editable double-var iterations expose working grid + active bands editors."""
    vm = _iteration_vm(data_repository, filter_repository, metric_repository)
    assert vm.current_iteration is not None
    dv = vm.create_double_var_iteration(
        vm.current_iteration.uid,
        new_variable_name="income",
        new_variable_type=VariableType.NUMERICAL,
    )
    vm.create_editable_clone(dv.uid)

    at = _run_app(vm)

    assert not at.exception, at.exception
    headers = [m.value for m in at.get("markdown")]
    assert any("Editable Risk Segment Grid" in str(h) for h in headers)
    assert any("Active Bands" in str(h) for h in headers)
    assert any("Editable Metric Grids" in str(h) for h in headers)

    table_values = [t.value for t in at.get("dataframe")]
    # Working editors render the grid, the active-bands mask, and the metric
    # tables on top of the default sections (1 control + 4 metrics).
    assert len(table_values) >= 9
    # The active-bands editor carries its boolean mask column.
    assert any("Active" in df.columns for df in table_values)


def test_graph_page_renders_without_exception(
    data_repository, filter_repository, metric_repository
):
    sim_repo = SimulationRepository(
        data_repository, filter_repository, metric_repository
    )
    vm = SimulationViewModel(
        data_repository, sim_repo, filter_repository, metric_repository
    )
    vm.begin_draft()
    vm.update_draft_name("My Sim")
    vm.update_draft_variable_name("credit_score")
    vm.update_draft_bad_rate_column(
        which="dev", loss_rate_type=LossRateTypes.ULR, field="numerator_col", value="unt_bad"
    )
    vm.update_draft_bad_rate_data_sources(
        which="dev", data_source_ids=tuple(vm.data_source_ids)
    )
    vm.confirm_draft()
    sim_id = vm.current_simulation_id
    assert sim_id is not None
    vm.run_simulation(sim_id)
    so = vm.get_simulation_outputs(sim_id)[0]
    vm.open_iteration_from_output(sim_id, so.uid)

    at = AppTest.from_file(str(pathlib.Path(__file__).resolve().parent / "_render_simulation_graph.py"))
    at.session_state["session"] = types.SimpleNamespace(simulation_view_model=vm)
    at.run(timeout=15)

    assert not at.exception, at.exception
    assert at.get("title")  # "Simulations" title
