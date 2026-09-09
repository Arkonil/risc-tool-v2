"""Tests for the iteration family feature (fixed/editable/double-variable).

Covers the repository lifecycle: snapshotted fixed iterations, editable clones
that fan from a family root, double-variable planning and grid evaluation,
per-band editing, cascade deletion, and graph-aware serialization.
"""

from collections import OrderedDict

import pytest

from risc_tool_v2.data.core.enums import IterationType, LossRateTypes, VariableType
from risc_tool_v2.data.core.uid import IterationID, MetricID, RiskSegmentID
from risc_tool_v2.data.simulation.models.risk_segment import RiskSegmentConfig
from risc_tool_v2.data.simulation.models.scalar import ScalarConfig
from risc_tool_v2.data.simulation.models.simulation_config import (
    BadRateConfig,
    SimulationConfigGenerator,
)
from risc_tool_v2.data.simulation.repositories.simulation_repository import (
    SimulationRepository,
)


def _make_scg(data_repository, **overrides) -> SimulationConfigGenerator:
    defaults = {
        "risk_segment_config": RiskSegmentConfig(),
        "dev_unit_bad_rate": BadRateConfig(
            loss_rate_type=LossRateTypes.ULR,
            numerator_col="unt_bad",
            data_source_ids=tuple(data_repository.data_sources.keys()),
            is_annualized=True,
        ),
        "dev_dollar_bad_rate": None,
        "test_unit_bad_rate": None,
        "test_dollar_bad_rate": None,
        "bad_rate_type": LossRateTypes.ULR,
        "scalar_config": ScalarConfig(),
        "variable_name": "credit_score",
        "variable_type": VariableType.NUMERICAL,
    }
    defaults.update(overrides)
    return SimulationConfigGenerator(name="iteration-v2-test", **defaults)


def _run_output(repo: SimulationRepository, sim_id):
    repo.run_simulation(sim_id)
    outputs = repo.get_simulation_outputs(sim_id)
    assert len(outputs) == 1
    return outputs[0]


@pytest.fixture
def repo(data_repository, filter_repository, metric_repository) -> SimulationRepository:
    return SimulationRepository(data_repository, filter_repository, metric_repository)


@pytest.fixture
def root_iteration(repo, data_repository):
    sim = repo.create_simulation(_make_scg(data_repository))
    so = _run_output(repo, sim.uid)
    return sim, so, repo.create_iteration(sim.uid, so.uid)


def test_create_iteration_snapshots_output_groups(repo, data_repository):
    sim = repo.create_simulation(_make_scg(data_repository))
    so = _run_output(repo, sim.uid)

    iteration = repo.create_iteration(sim.uid, so.uid)

    assert iteration.iter_type == IterationType.SINGLE
    assert iteration.is_editable is False
    assert iteration.family_root_id == iteration.uid
    assert iteration.source_iteration_id == IterationID.UNSET
    assert iteration.previous_iteration_id == IterationID.UNSET
    assert iteration.default_groups == so.groups
    assert iteration.groups == so.groups
    assert iteration.uid in repo.iteration_graph.connections


def test_create_editable_clone_branches_from_family_root(repo, root_iteration):
    _, _, root = root_iteration

    clone = repo.create_editable_clone(root.uid)

    assert clone.is_editable is True
    assert clone.iter_type == IterationType.SINGLE
    assert clone.family_root_id == root.uid
    assert clone.source_iteration_id == root.uid
    assert clone.default_groups == root.default_groups
    assert clone.groups == root.groups
    assert repo.iteration_graph.get_parent(clone.uid) == root.uid
    assert clone.name == "Iteration #2 (editable)"

    grandchild = repo.create_editable_clone(clone.uid)
    assert grandchild.family_root_id == root.uid
    assert repo.iteration_graph.get_parent(grandchild.uid) == root.uid
    assert repo.iteration_graph.children(root.uid) == (clone.uid, grandchild.uid)


def test_clone_of_editable_keeps_edited_groups_as_working(repo, root_iteration):
    _, _, root = root_iteration
    clone = repo.create_editable_clone(root.uid)

    edited = OrderedDict()
    for gid, group in list(clone.groups.items())[::-1]:
        edited[gid] = group
    repo.set_controls(clone.uid, edited)

    cloned_clone = repo.create_editable_clone(clone.uid)

    assert cloned_clone.default_groups == root.default_groups
    assert list(cloned_clone.groups) == list(edited)


def test_create_double_var_numeric_over_root(repo, root_iteration):
    _, _, root = root_iteration

    iteration = repo.create_double_var_iteration(
        root.uid, new_variable_name="income", new_variable_type=VariableType.NUMERICAL
    )

    assert iteration.is_double_var
    assert iteration.iter_type == IterationType.DOUBLE
    assert iteration.is_editable is False
    assert iteration.family_root_id == iteration.uid
    assert iteration.previous_iteration_id == root.uid
    assert len(iteration.groups) >= 1
    assert iteration.default_groups == iteration.groups
    assert len(iteration.risk_segment_grid) == len(iteration.groups)
    assert set(iteration.groups_mask) == set(iteration.groups)
    assert all(iteration.groups_mask.values())
    assert repo.iteration_graph.get_parent(iteration.uid) == root.uid


def test_get_iteration_grid_evaluates_all_cells(repo, root_iteration):
    _, _, root = root_iteration
    iteration = repo.create_double_var_iteration(
        root.uid, new_variable_name="income", new_variable_type=VariableType.NUMERICAL
    )

    grid = repo.get_iteration_grid(
        iteration.uid, metric_ids=(MetricID.DEV_UNT_BAD_RATE,)
    )

    assert grid.errors == []
    assert [name for name, _ in grid.columns] == ["Dev # Bad Rate"]
    assert list(grid.row_groups) == list(iteration.groups)
    assert len(grid.parent_segments) == len(root.groups)
    for row_gid in grid.row_groups:
        for parent_seg_id in grid.parent_segments:
            assert (row_gid, parent_seg_id) in grid.values
    assert any(
        grid.cell(row_gid, parent_seg_id, "Dev # Bad Rate") is not None
        for row_gid in grid.row_groups
        for parent_seg_id in grid.parent_segments
    )


def test_get_iteration_grid_totals_row_and_column(repo, root_iteration):
    _, _, root = root_iteration
    iteration = repo.create_double_var_iteration(
        root.uid, new_variable_name="income", new_variable_type=VariableType.NUMERICAL
    )

    grid = repo.get_iteration_grid(
        iteration.uid,
        metric_ids=(MetricID.DEV_UNT_BAD_RATE,),
        show_total_row=True,
        show_total_column=True,
    )

    assert grid.errors == []
    assert set(grid.total_row) == {"Dev # Bad Rate"}
    assert set(grid.total_column) == {"Dev # Bad Rate"}
    assert grid.corner_total["Dev # Bad Rate"] is not None
    assert set(grid.total_row["Dev # Bad Rate"]).issubset(grid.parent_segments)
    assert set(grid.total_column["Dev # Bad Rate"]).issubset(grid.row_groups)
    assert any(
        value is not None for value in grid.total_row["Dev # Bad Rate"].values()
    )


def test_get_iteration_grid_totals_absent_by_default(repo, root_iteration):
    _, _, root = root_iteration
    iteration = repo.create_double_var_iteration(
        root.uid, new_variable_name="income", new_variable_type=VariableType.NUMERICAL
    )

    grid = repo.get_iteration_grid(iteration.uid)

    assert grid.total_row == {}
    assert grid.total_column == {}
    assert grid.corner_total == {}


def test_get_iteration_default_uses_pinned_groups(repo, root_iteration):
    _, _, root = root_iteration
    clone = repo.create_editable_clone(root.uid)

    edited = OrderedDict()
    for gid, group in list(clone.groups.items())[::-1]:
        edited[gid] = group
    repo.set_controls(clone.uid, edited)

    working_table = repo.get_iteration_table(clone.uid)
    default_table = repo.get_iteration_table(clone.uid, default=True)

    assert list(working_table.segments) == list(edited)
    assert list(default_table.segments) == list(root.groups)
    assert list(default_table.segments) != list(working_table.segments)

    iteration = repo.create_double_var_iteration(
        clone.uid, new_variable_name="income", new_variable_type=VariableType.NUMERICAL
    )
    dv_clone = repo.create_editable_clone(iteration.uid)
    repo.add_new_group(dv_clone.uid)

    working_grid = repo.get_iteration_grid(dv_clone.uid)
    default_grid = repo.get_iteration_grid(dv_clone.uid, default=True)

    assert working_grid.errors == []
    assert default_grid.errors == []
    assert list(working_grid.row_groups) == list(dv_clone.groups)
    assert list(default_grid.row_groups) == list(dv_clone.default_groups)
    assert len(working_grid.row_groups) > len(default_grid.row_groups)


def test_get_iteration_table_rejects_double_var(repo, root_iteration):
    _, _, root = root_iteration
    iteration = repo.create_double_var_iteration(
        root.uid, new_variable_name="income", new_variable_type=VariableType.NUMERICAL
    )

    with pytest.raises(ValueError):
        repo.get_iteration_table(iteration.uid)


def test_get_iteration_grid_rejects_single_var(repo, root_iteration):
    _, _, root = root_iteration

    with pytest.raises(ValueError):
        repo.get_iteration_grid(root.uid)


def test_create_double_var_categorical_over_double_var(repo, root_iteration):
    _, _, root = root_iteration
    numeric = repo.create_double_var_iteration(
        root.uid, new_variable_name="income", new_variable_type=VariableType.NUMERICAL
    )

    categorical = repo.create_double_var_iteration(
        numeric.uid,
        new_variable_name="status",
        new_variable_type=VariableType.CATEGORICAL,
    )

    assert categorical.is_double_var
    assert categorical.previous_iteration_id == numeric.uid
    assert repo.iteration_graph.get_parent(categorical.uid) == numeric.uid
    assert len(categorical.groups) >= 1

    grid = repo.get_iteration_grid(
        categorical.uid, metric_ids=(MetricID.DEV_UNT_BAD_RATE,)
    )
    assert grid.errors == []
    assert len(grid.parent_segments) >= 1
    assert any(
        grid.cell(row_gid, parent_seg_id, "Dev # Bad Rate") is not None
        for row_gid in grid.row_groups
        for parent_seg_id in grid.parent_segments
    )


def test_create_double_var_validates_variable(repo, root_iteration):
    _, _, root = root_iteration

    with pytest.raises(ValueError):
        repo.create_double_var_iteration(
            root.uid,
            new_variable_name="nonexistent_column",
            new_variable_type=VariableType.NUMERICAL,
        )
    with pytest.raises(ValueError):
        repo.create_double_var_iteration(
            root.uid,
            new_variable_name="income",
            new_variable_type=VariableType.CATEGORICAL,
        )


def test_double_var_over_editable_source_evaluates(repo, root_iteration):
    _, _, root = root_iteration
    clone = repo.create_editable_clone(root.uid)
    repo.set_controls(clone.uid, OrderedDict(reversed(list(clone.groups.items()))))

    iteration = repo.create_double_var_iteration(
        clone.uid, new_variable_name="income", new_variable_type=VariableType.NUMERICAL
    )

    grid = repo.get_iteration_grid(iteration.uid)
    assert grid.errors == []
    assert len(grid.row_groups) == len(iteration.groups)


def test_select_groups_updates_mask_only_for_defaults(repo, root_iteration):
    _, _, root = root_iteration
    iteration = repo.create_double_var_iteration(
        root.uid, new_variable_name="income", new_variable_type=VariableType.NUMERICAL
    )

    first = next(iter(iteration.groups))
    repo.select_groups(iteration.uid, mask={first: False})

    assert iteration.groups_mask[first] is False
    assert all(
        is_visible
        for gid, is_visible in iteration.groups_mask.items()
        if gid != first
    )


def test_add_new_group_inherits_last_grid_row(repo, root_iteration):
    _, _, root = root_iteration
    clone = repo.create_editable_clone(root.uid)

    last_gid, _last_group = next(reversed(clone.groups.items()))
    count = len(clone.groups)
    updated = repo.add_new_group(clone.uid)

    assert len(updated.groups) == count + 1
    new_gid = max(int(g) for g in updated.groups)
    assert new_gid > int(last_gid)
    last_row = updated.risk_segment_grid.get(last_gid, {})
    assert updated.risk_segment_grid.get(RiskSegmentID(int=new_gid), {}) == last_row

    with pytest.raises(ValueError):
        repo.add_new_group(root.uid)


def test_editing_rejected_for_fixed_iterations(repo, root_iteration):
    _, _, root = root_iteration
    grid = {
        gid: {} for gid in root.groups
    }
    with pytest.raises(ValueError):
        repo.set_controls(root.uid, grid)
    with pytest.raises(ValueError):
        repo.set_risk_segment_grid(root.uid, {})
    with pytest.raises(ValueError):
        repo.select_groups(root.uid, mask={})


def test_set_risk_segment_grid_requires_double_var(repo, root_iteration):
    _, _, root = root_iteration
    clone = repo.create_editable_clone(root.uid)
    with pytest.raises(ValueError):
        repo.set_risk_segment_grid(clone.uid, {})


def test_remove_iteration_cascades_descendants(repo, root_iteration):
    _, _, root = root_iteration
    sibling = repo.create_editable_clone(root.uid)
    numeric = repo.create_double_var_iteration(
        root.uid, new_variable_name="income", new_variable_type=VariableType.NUMERICAL
    )
    categorical = repo.create_double_var_iteration(
        numeric.uid,
        new_variable_name="status",
        new_variable_type=VariableType.CATEGORICAL,
    )
    dv_clone = repo.create_editable_clone(numeric.uid)

    repo.remove_iteration(numeric.uid)

    assert numeric.uid not in repo.iterations
    assert categorical.uid not in repo.iterations
    assert dv_clone.uid not in repo.iterations
    assert root.uid in repo.iterations
    assert sibling.uid in repo.iterations


def test_serialization_round_trip_preserves_graph_and_edits(
    repo, data_repository, filter_repository, metric_repository, root_iteration
):
    _, _, root = root_iteration
    clone = repo.create_editable_clone(root.uid)
    numeric = repo.create_double_var_iteration(
        root.uid, new_variable_name="income", new_variable_type=VariableType.NUMERICAL
    )
    repo.add_new_group(clone.uid)

    data = repo.to_dict()
    restored = SimulationRepository.from_dict(
        data,
        data_repository=data_repository,
        filter_repository=filter_repository,
        metric_repository=metric_repository,
    )

    assert restored.iterations.keys() == repo.iterations.keys()
    assert restored.iteration_graph.to_dict() == repo.iteration_graph.to_dict()
    for key in repo.iterations:
        original = repo.iterations[key]
        copy = restored.iterations[key]
        assert copy.name == original.name
        assert copy.is_editable == original.is_editable
        assert copy.iter_type == original.iter_type
        assert copy.family_root_id == original.family_root_id
        assert copy.previous_iteration_id == original.previous_iteration_id
        assert copy.default_groups == original.default_groups
        assert copy.groups == original.groups
        assert copy.risk_segment_grid == original.risk_segment_grid
        assert copy.default_risk_segment_grid == original.default_risk_segment_grid

    restored_numeric = restored.get_iteration(numeric.uid)
    assert restored_numeric.is_double_var