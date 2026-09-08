import pytest

from risc_tool_v2.data.core.enums import LossRateTypes
from risc_tool_v2.data.core.uid import RiskSegmentID, SimulationID
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
    assert metadata.metric_ids == ()


def test_simulation_vm_update_iteration_metadata_prunes_invalid_ids(
    data_repository, filter_repository, metric_repository
):
    vm, sim_repo = _simulation_vm(data_repository, filter_repository, metric_repository)
    sim_id, so = _create_output_simulation(vm, sim_repo)
    iteration = vm.open_iteration_from_output(sim_id, so.uid)

    from risc_tool_v2.data.core.uid import FilterID, MetricID

    vm.update_iteration_metadata(
        iteration.uid,
        metric_ids=(MetricID(int=1), MetricID(int=2)),
        filter_ids=(FilterID(int=3),),
    )
    metadata = vm.iteration_metadata(iteration.uid)
    assert metadata.metric_ids == ()
    assert metadata.filter_ids == ()


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
