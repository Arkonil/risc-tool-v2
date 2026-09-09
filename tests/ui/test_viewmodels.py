import pytest

from risc_tool_v2.data.core.enums import IterationType, LossRateTypes, VariableType
from risc_tool_v2.data.core.uid import (
    IterationID,
    MetricID,
    RiskSegmentID,
    SimulationID,
)
from risc_tool_v2.data.data_source.models.data_source import ReadConfig
from risc_tool_v2.data.simulation.models.simulation import SimulationStatus
from risc_tool_v2.data.simulation.repositories.simulation_repository import (
    SimulationRepository,
)
from risc_tool_v2.ui.data_source.data_explorer.data_explorer_vm import (
    DataExplorerViewModel,
)
from risc_tool_v2.ui.data_source.data_importer.data_importer_vm import (
    DataImporterViewModel,
)
from risc_tool_v2.ui.filter.filter_editor.filter_vm import FilterViewModel
from risc_tool_v2.ui.metric.metric_editor.metric_vm import MetricViewModel
from risc_tool_v2.ui.simulation.simulation_vm import SimulationViewModel


def test_data_importer_vm(data_repository, sample_csv):
    vm = DataImporterViewModel(data_repository)
    assert not vm.is_empty

    first_ds_id = next(iter(data_repository.data_sources.keys()))
    vm.update_data_source(
        data_source_id=first_ds_id,
        filepath=sample_csv,
        label="Updated Dev",
        read_config=ReadConfig(),
    )


def test_data_explorer_vm(data_repository, filter_repository):
    vm = DataExplorerViewModel(data_repository, filter_repository)
    assert vm.data_loaded

    # Test IV DataFrame computation
    ds_ids = list(data_repository.data_sources.keys())
    vm.iv_data_sources = ds_ids
    df = vm.get_iv_df(
        target_variable="unt_bad", input_variables=["credit_score", "income"]
    )
    assert df is not None
    assert df.height == 2


def test_filter_vm_crud(data_repository, filter_repository):
    vm = FilterViewModel(data_repository, filter_repository)
    vm.set_mode("edit")
    vm.set_filter_property(name="High Income", query="income > 60000")
    vm.validate_filter("High Income", "income > 60000", "test_id")
    assert vm.is_verified
    vm.save_filter()

    assert len(filter_repository.filters) == 1


def test_metric_vm_crud(data_repository, metric_repository):
    vm = MetricViewModel(data_repository, metric_repository)
    vm.set_mode("edit")
    ds_ids = list(data_repository.data_sources.keys())
    vm.selected_data_source_ids = ds_ids
    vm.set_metric_property(name="Mean Score", query="credit_score.mean()")
    vm.validate_metric("Mean Score", "credit_score.mean()", "test_id")
    assert vm.is_verified
    vm.save_metric()

    assert len(metric_repository.metrics) == 1


def test_simulation_vm_selected_common_columns(
    data_repository, filter_repository, metric_repository
):
    sim_repo = SimulationRepository(
        data_repository, filter_repository, metric_repository
    )
    vm = SimulationViewModel(
        data_repository, sim_repo, filter_repository, metric_repository
    )
    ds_ids = list(data_repository.data_sources.keys())

    assert vm.selected_common_columns(ds_ids) == [
        c[0] for c in data_repository.common_columns(ds_ids)
    ]
    assert vm.selected_common_columns([]) == []


def _simulation_vm(data_repository, filter_repository, metric_repository):
    sim_repo = SimulationRepository(
        data_repository, filter_repository, metric_repository
    )
    vm = SimulationViewModel(
        data_repository, sim_repo, filter_repository, metric_repository
    )
    return vm, sim_repo


def _create_simulation(vm, repo) -> SimulationID:
    vm.begin_draft()
    vm.update_draft_name("My Sim")
    vm.confirm_draft()
    sim_id = vm.current_simulation_id
    assert sim_id is not None
    return sim_id


def test_simulation_vm_begin_edit_draft_loads_scg(
    data_repository, filter_repository, metric_repository
):
    vm, sim_repo = _simulation_vm(data_repository, filter_repository, metric_repository)
    sim_id = _create_simulation(vm, sim_repo)
    original_scg = sim_repo.scgs[
        sim_repo.simulations[sim_id].simulation_config_generator_id
    ]

    vm.begin_edit_draft(sim_id)

    assert vm.is_editing
    assert vm.editing_simulation_id == sim_id
    assert vm.mode == "create"
    assert vm.draft_scg == original_scg


def test_simulation_vm_confirm_draft_edit_repoints_scg(
    data_repository, filter_repository, metric_repository
):
    vm, sim_repo = _simulation_vm(data_repository, filter_repository, metric_repository)
    sim_id = _create_simulation(vm, sim_repo)
    original_scg_uid = sim_repo.simulations[sim_id].simulation_config_generator_id

    vm.begin_edit_draft(sim_id)
    vm.update_draft_variable_name("edited_var")
    vm.confirm_draft()

    updated = sim_repo.simulations[sim_id]
    edited_uid = updated.simulation_config_generator_id
    assert edited_uid != original_scg_uid
    assert sim_repo.scgs[edited_uid].variable_name == "edited_var"
    assert updated.uid == sim_id
    assert updated.status == SimulationStatus.PENDING
    assert not vm.is_editing
    assert vm.mode == "view"
    assert vm.current_simulation_id == sim_id

    # Old SCG retained in the cache.
    assert original_scg_uid in sim_repo.scgs


def test_simulation_vm_confirm_draft_create_simulation(
    data_repository, filter_repository, metric_repository
):
    vm, sim_repo = _simulation_vm(data_repository, filter_repository, metric_repository)
    sim_id = _create_simulation(vm, sim_repo)

    assert len(sim_repo.simulations) == 1
    sim = sim_repo.simulations[sim_id]
    assert sim.simulation_config_generator_id in sim_repo.scgs
    assert not vm.is_editing
    assert vm.mode == "graph"


def test_simulation_vm_cancel_edit_draft(
    data_repository, filter_repository, metric_repository
):
    vm, sim_repo = _simulation_vm(data_repository, filter_repository, metric_repository)
    sim_id = _create_simulation(vm, sim_repo)
    original_scg_uid = sim_repo.simulations[sim_id].simulation_config_generator_id

    vm.begin_edit_draft(sim_id)
    assert vm.is_editing
    vm.cancel_edit_draft()

    assert not vm.is_editing
    assert vm.editing_simulation_id is None
    assert vm.mode == "graph"
    # The simulation is untouched.
    assert sim_repo.simulations[sim_id].simulation_config_generator_id == (
        original_scg_uid
    )


def test_simulation_vm_view_mode_resolves_simulation_and_outputs(
    data_repository, filter_repository, metric_repository
):
    vm, _sim_repo = _simulation_vm(
        data_repository, filter_repository, metric_repository
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

    vm.set_mode("view", sim_id)

    assert vm.mode == "view"
    assert vm.current_simulation_id == sim_id
    assert vm.current_simulation is not None
    assert vm.current_simulation.uid == sim_id
    assert not vm.is_editing

    assert vm.get_simulation_outputs(sim_id) == ()
    vm.run_simulation(sim_id)
    outputs = vm.get_simulation_outputs(sim_id)
    assert len(outputs) == 1
    assert all(
        isinstance(group_id, RiskSegmentID) for so in outputs for group_id in so.groups
    )


def test_simulation_vm_view_mode_falls_back_when_simulation_removed(
    data_repository, filter_repository, metric_repository
):
    vm, sim_repo = _simulation_vm(data_repository, filter_repository, metric_repository)
    sim_id = _create_simulation(vm, sim_repo)

    vm.set_mode("view", sim_id)
    vm.remove_simulation(sim_id)

    assert vm.mode == "graph"
    assert vm.current_simulation_id is None
    assert vm.current_simulation is None


def _create_output_simulation(vm, sim_repo):
    """Create and run a simulation, returning (sim_id, output)."""
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
    outputs = vm.get_simulation_outputs(sim_id)
    assert len(outputs) == 1
    return sim_id, outputs[0]


def test_simulation_vm_open_iteration_seeds_metadata_from_sim(
    data_repository, filter_repository, metric_repository
):
    filter_repository.create_filter("High Score", "credit_score > 600")
    sim_filter_id = next(iter(filter_repository.filters))

    vm, _sim_repo2 = _simulation_vm(
        data_repository, filter_repository, metric_repository
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
    vm.update_draft_filter_ids((sim_filter_id,))
    vm.update_draft_use_scalars(False)
    vm.confirm_draft()
    sim_id = vm.current_simulation_id
    assert sim_id is not None
    vm.run_simulation(sim_id)
    so = vm.get_simulation_outputs(sim_id)[0]

    iteration = vm.open_iteration_from_output(sim_id, so.uid)

    assert vm.mode == "iteration"
    assert vm.current_iteration_id == iteration.uid
    assert vm.current_iteration is not None
    # Opening for an output that already has an iteration is idempotent.
    assert vm.open_iteration_from_output(sim_id, so.uid).uid == iteration.uid

    metadata = vm.iteration_metadata(iteration.uid)
    assert metadata.filter_ids == (sim_filter_id,)
    assert metadata.remove_outliers is True
    assert metadata.scalars_enabled is False
    # A new iteration is seeded with all four built-in bad rates selected.
    assert metadata.metric_ids == (
        MetricID.DEV_UNT_BAD_RATE,
        MetricID.DEV_DLR_BAD_RATE,
        MetricID.TST_UNT_BAD_RATE,
        MetricID.TST_DLR_BAD_RATE,
    )


def test_simulation_vm_update_iteration_metadata_prunes_invalid_ids(
    data_repository, filter_repository, metric_repository
):
    vm, sim_repo = _simulation_vm(data_repository, filter_repository, metric_repository)
    sim_id, so = _create_output_simulation(vm, sim_repo)
    iteration = vm.open_iteration_from_output(sim_id, so.uid)

    from risc_tool_v2.data.core.uid import FilterID

    vm.update_iteration_metadata(
        iteration.uid,
        metric_ids=(MetricID(int=1), MetricID(int=2)),
        filter_ids=(FilterID(int=3),),
    )
    metadata = vm.iteration_metadata(iteration.uid)
    # Invalid (non-built-in, non-existent) metric ids are dropped entirely.
    assert metadata.metric_ids == ()
    assert metadata.filter_ids == ()


def test_simulation_vm_update_iteration_metadata_keeps_builtin_sentinels(
    data_repository, filter_repository, metric_repository
):
    """Built-in bad rate id sentinels survive an explicit metadata metric update."""
    vm, sim_repo = _simulation_vm(data_repository, filter_repository, metric_repository)
    sim_id, so = _create_output_simulation(vm, sim_repo)
    iteration = vm.open_iteration_from_output(sim_id, so.uid)

    # Explicitly selecting built-ins plus a bogus id keeps the built-ins.
    vm.update_iteration_metadata(
        iteration.uid,
        metric_ids=(
            MetricID.DEV_UNT_BAD_RATE,
            MetricID(int=999),
            MetricID.TST_DLR_BAD_RATE,
        ),
    )
    metadata = vm.iteration_metadata(iteration.uid)
    assert metadata.metric_ids == (
        MetricID.DEV_UNT_BAD_RATE,
        MetricID.TST_DLR_BAD_RATE,
    )


def test_simulation_vm_remove_iteration_falls_back_to_graph(
    data_repository, filter_repository, metric_repository
):
    vm, sim_repo = _simulation_vm(data_repository, filter_repository, metric_repository)
    sim_id, so = _create_output_simulation(vm, sim_repo)
    iteration = vm.open_iteration_from_output(sim_id, so.uid)
    assert vm.mode == "iteration"

    vm.remove_iteration(iteration.uid)

    assert vm.mode == "graph"
    assert vm.current_iteration is None
    assert vm.current_iteration_id is None
    with pytest.raises(KeyError):
        vm.iteration_metadata(iteration.uid)
    assert sim_repo.simulations[sim_id].uid == sim_id


def test_simulation_vm_dependency_update_prunes_removed_iteration(
    data_repository, filter_repository, metric_repository
):
    vm, sim_repo = _simulation_vm(data_repository, filter_repository, metric_repository)
    sim_id, so = _create_output_simulation(vm, sim_repo)
    iteration = vm.open_iteration_from_output(sim_id, so.uid)

    vm.remove_simulation(sim_id)

    # Cascade delete surfaced through the dependency update fallback.
    assert vm.mode == "graph"
    assert vm.current_iteration is None
    assert vm.current_iteration_id is None
    assert iteration.uid not in sim_repo.iterations


def test_simulation_vm_create_editable_clone_opens_clone(
    data_repository, filter_repository, metric_repository
):
    vm, sim_repo = _simulation_vm(data_repository, filter_repository, metric_repository)
    sim_id, so = _create_output_simulation(vm, sim_repo)
    root = vm.open_iteration_from_output(sim_id, so.uid)

    clone = vm.create_editable_clone(root.uid)

    assert clone.is_editable is True
    assert clone.iter_type == IterationType.SINGLE
    assert clone.family_root_id == root.uid
    assert clone.default_groups == root.groups
    assert vm.mode == "iteration"
    assert vm.current_iteration_id == clone.uid
    assert clone.uid in sim_repo.iteration_graph.children(root.uid)

    # Clone of an editable branches from the family root, not the clone.
    clone2 = vm.create_editable_clone(clone.uid)
    assert clone2.family_root_id == root.uid
    assert clone2.source_iteration_id == clone.uid
    assert clone2.uid in sim_repo.iteration_graph.children(root.uid)


def test_simulation_vm_create_double_var_iteration_numeric(
    data_repository, filter_repository, metric_repository
):
    vm, _sim_repo = _simulation_vm(
        data_repository, filter_repository, metric_repository
    )
    sim_id, so = _create_output_simulation(vm, _sim_repo)
    root = vm.open_iteration_from_output(sim_id, so.uid)

    double_var = vm.create_double_var_iteration(
        root.uid, new_variable_name="income", new_variable_type=VariableType.NUMERICAL
    )

    assert double_var.is_double_var
    assert double_var.is_editable is False
    assert vm.mode == "iteration"
    assert vm.current_iteration_id == double_var.uid

    grid = vm.get_iteration_grid(double_var.uid)
    assert grid.parent_segments
    assert all(
        (row_gid, parent_gid) in grid.values
        for row_gid in grid.row_groups
        for parent_gid in grid.parent_segments
    )

    # The single-variable view is not double-variable capable.
    with pytest.raises(ValueError):
        vm.get_iteration_grid(root.uid)


def test_simulation_vm_metric_options_includes_builtins_and_user_metrics(
    data_repository, filter_repository, metric_repository
):
    metric_repository.create_metric(
        name="Avg Credit",
        query="`credit_score`.mean()",
        is_cumulative=False,
        use_thousand_sep=True,
        is_percentage=False,
        decimal_places=2,
        data_source_ids=list(data_repository.data_sources.keys()),
    )
    vm, _sim_repo = _simulation_vm(
        data_repository, filter_repository, metric_repository
    )
    sim_id, so = _create_output_simulation(vm, _sim_repo)
    iteration = vm.open_iteration_from_output(sim_id, so.uid)

    options = vm.metric_options(iteration.uid)

    # The four built-in bad rates come first, then the user metric.
    keys = list(options.keys())
    assert keys[:4] == [
        MetricID.DEV_UNT_BAD_RATE,
        MetricID.DEV_DLR_BAD_RATE,
        MetricID.TST_UNT_BAD_RATE,
        MetricID.TST_DLR_BAD_RATE,
    ]
    names = [m.name for m in options.values()]
    assert "Dev # Bad Rate" in names
    assert any(name == "Avg Credit" for name in names)


def test_simulation_vm_iteration_create_mode_lifecycle(
    data_repository, filter_repository, metric_repository
):
    vm, _sim_repo = _simulation_vm(
        data_repository, filter_repository, metric_repository
    )
    sim_id, so = _create_output_simulation(vm, _sim_repo)
    root = vm.open_iteration_from_output(sim_id, so.uid)

    vm.begin_iteration_create(root.uid)

    assert vm.mode == "iteration_create"
    assert vm.iteration_create_base_id == root.uid
    assert vm.iteration_create_base is not None

    vm.cancel_iteration_create()
    assert vm.mode == "graph"
    assert vm.iteration_create_base_id is None


def test_simulation_vm_iteration_create_missing_base(
    data_repository, filter_repository, metric_repository
):
    vm, _sim_repo = _simulation_vm(
        data_repository, filter_repository, metric_repository
    )

    with pytest.raises(ValueError):
        vm.begin_iteration_create(IterationID(int=99))


def test_simulation_vm_create_double_var_rejects_missing_variable(
    data_repository, filter_repository, metric_repository
):
    vm, _sim_repo = _simulation_vm(
        data_repository, filter_repository, metric_repository
    )
    sim_id, so = _create_output_simulation(vm, _sim_repo)
    root = vm.open_iteration_from_output(sim_id, so.uid)

    with pytest.raises(ValueError):
        vm.create_double_var_iteration(
            root.uid,
            new_variable_name="does_not_exist",
            new_variable_type=VariableType.NUMERICAL,
        )
    # The failed creation must not disturb the view state.
    assert vm.mode == "iteration"
    assert vm.current_iteration_id == root.uid


def test_simulation_vm_double_var_candidate_columns(
    data_repository, filter_repository, metric_repository
):
    vm, _sim_repo = _simulation_vm(
        data_repository, filter_repository, metric_repository
    )
    sim_id, so = _create_output_simulation(vm, _sim_repo)
    root = vm.open_iteration_from_output(sim_id, so.uid)

    candidates = vm.double_var_candidate_columns(root.uid)
    names = [name for name, _ in candidates]
    assert "credit_score" not in names  # the iteration's own variable
    assert "income" in names
    assert any(name == "income" and var_type == VariableType.NUMERICAL for name, var_type in candidates)
    assert any(name == "status" and var_type == VariableType.CATEGORICAL for name, var_type in candidates)


def test_simulation_vm_iteration_chain_and_graph(
    data_repository, filter_repository, metric_repository
):
    vm, _sim_repo = _simulation_vm(
        data_repository, filter_repository, metric_repository
    )
    sim_id, so = _create_output_simulation(vm, _sim_repo)
    root = vm.open_iteration_from_output(sim_id, so.uid)
    clone = vm.create_editable_clone(root.uid)
    double_var = vm.create_double_var_iteration(
        root.uid, new_variable_name="income", new_variable_type=VariableType.NUMERICAL
    )

    assert vm.iteration_chain(root.uid) == (root,)
    chain = vm.iteration_chain(clone.uid)
    assert [it.uid for it in chain] == [root.uid, clone.uid]
    assert vm.iteration_graph.get_parent(clone.uid) == root.uid
    assert vm.iteration_graph.get_parent(double_var.uid) == root.uid
    assert vm.iteration_graph.is_root(double_var.uid) is False


def test_simulation_vm_rename_iteration(
    data_repository, filter_repository, metric_repository
):
    vm, _sim_repo = _simulation_vm(
        data_repository, filter_repository, metric_repository
    )
    sim_id, so = _create_output_simulation(vm, _sim_repo)
    root = vm.open_iteration_from_output(sim_id, so.uid)

    updated = vm.rename_iteration(root.uid, "Renamed Iteration")

    assert updated.name == "Renamed Iteration"
    assert vm.get_iteration(root.uid).name == "Renamed Iteration"


def test_simulation_vm_editing_passthrough(
    data_repository, filter_repository, metric_repository
):
    vm, _sim_repo = _simulation_vm(
        data_repository, filter_repository, metric_repository
    )
    sim_id, so = _create_output_simulation(vm, _sim_repo)
    root = vm.open_iteration_from_output(sim_id, so.uid)

    clone = vm.create_editable_clone(root.uid)
    n_working = len(clone.groups)
    vm.add_new_group(clone.uid)
    assert len(vm.get_iteration(clone.uid).groups) == n_working + 1

    # set_controls replaces the working bands wholesale.
    from collections import OrderedDict

    from risc_tool_v2.data.simulation.models.groups import NumericalGroup

    working = OrderedDict(
        (gid, NumericalGroup(lower_bound=0.0, upper_bound=100.0))
        for gid in clone.groups
    )
    vm.set_controls(clone.uid, working)
    assert all(
        isinstance(g, NumericalGroup) for g in vm.get_iteration(clone.uid).groups.values()
    )

    # Double-variable edits: grid and mask passthrough.
    double_var = vm.create_double_var_iteration(
        root.uid, new_variable_name="income", new_variable_type=VariableType.NUMERICAL
    )
    dv_clone = vm.create_editable_clone(double_var.uid)
    grid = dict(dv_clone.effective_risk_segment_grid())
    vm.set_risk_segment_grid(dv_clone.uid, grid)
    assert vm.get_iteration(dv_clone.uid).risk_segment_grid == grid

    mask = {gid: (position == 0) for position, gid in enumerate(dv_clone.default_groups)}
    vm.select_groups(dv_clone.uid, mask=mask)
    assert vm.get_iteration(dv_clone.uid).groups_mask == mask


def test_simulation_vm_remove_double_var_cascades(
    data_repository, filter_repository, metric_repository
):
    vm, sim_repo = _simulation_vm(
        data_repository, filter_repository, metric_repository
    )
    sim_id, so = _create_output_simulation(vm, sim_repo)
    root = vm.open_iteration_from_output(sim_id, so.uid)
    double_var = vm.create_double_var_iteration(
        root.uid, new_variable_name="income", new_variable_type=VariableType.NUMERICAL
    )

    vm.remove_iteration(double_var.uid)

    assert vm.mode == "graph"
    assert double_var.uid not in sim_repo.iterations
    assert root.uid in sim_repo.iterations
