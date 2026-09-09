"""Tests for simulation iterations (single-variable analyses).

Iterations are lightweight reference objects (simulation/scg/sc/so ids) with
sequential integer identities; their band tables resolve from the cached SCG/SO
at evaluation time.
"""

from pathlib import Path

import pandas as pd
import pytest

from risc_tool_v2.data.core.enums import LossRateTypes, VariableType
from risc_tool_v2.data.core.uid import IterationID, MetricID, SimulationID
from risc_tool_v2.data.data_source.models.data_source import ReadConfig
from risc_tool_v2.data.simulation.models.risk_segment import RiskSegmentConfig
from risc_tool_v2.data.simulation.models.scalar import LossRateScalar, ScalarConfig
from risc_tool_v2.data.simulation.models.simulation import SimulationStatus
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
    return SimulationConfigGenerator(name="iteration-test", **defaults)


def _run_output(repo: SimulationRepository, sim_id: SimulationID):
    repo.run_simulation(sim_id)
    outputs = repo.get_simulation_outputs(sim_id)
    assert len(outputs) == 1
    return outputs[0]


def test_create_iteration_sequential_ids_and_idempotent(
    data_repository, filter_repository, metric_repository
) -> None:
    repo = SimulationRepository(data_repository, filter_repository, metric_repository)
    sim = repo.create_simulation(_make_scg(data_repository))
    so = _run_output(repo, sim.uid)

    iteration = repo.create_iteration(sim.uid, so.uid)
    again = repo.create_iteration(sim.uid, so.uid)

    assert iteration.uid == IterationID(int=1)
    assert iteration.uid == again.uid
    assert iteration.name == "Iteration #1"

    other_sim = repo.create_simulation(
        _make_scg(data_repository, variable_name="income")
    )
    other_so = _run_output(repo, other_sim.uid)
    other_iteration = repo.create_iteration(other_sim.uid, other_so.uid)
    assert other_iteration.uid == IterationID(int=2)

    assert len(repo.iterations) == 2
    assert [int(it.uid) for it in repo.iterations.values()] == [1, 2]


def test_iteration_stores_references_only(
    data_repository, filter_repository, metric_repository
) -> None:
    repo = SimulationRepository(data_repository, filter_repository, metric_repository)
    sim = repo.create_simulation(_make_scg(data_repository))
    so = _run_output(repo, sim.uid)

    iteration = repo.create_iteration(sim.uid, so.uid)

    assert iteration.simulation_id == sim.uid
    assert iteration.scg_id == sim.simulation_config_generator_id
    assert iteration.sc_id == so.simulation_config_hash
    assert iteration.so_id == so.uid
    assert iteration.variable_name == so.variable_name
    assert iteration.variable_type == so.variable_type
    assert iteration.scg_id in repo.scgs
    assert iteration.so_id in repo.sos


def test_create_iteration_validates_sim_and_output(
    data_repository, filter_repository, metric_repository
) -> None:
    repo = SimulationRepository(data_repository, filter_repository, metric_repository)
    sim = repo.create_simulation(_make_scg(data_repository))
    so = _run_output(repo, sim.uid)

    other_sim = repo.create_simulation(
        _make_scg(data_repository, variable_name="income")
    )
    other_so = _run_output(repo, other_sim.uid)

    with pytest.raises(ValueError):
        repo.create_iteration(SimulationID(int=4242), so.uid)
    with pytest.raises(ValueError):
        repo.create_iteration(sim.uid, other_so.uid)
    with pytest.raises(ValueError):
        repo.get_iteration(IterationID(int=999))


def test_iterations_for_sim_scoped_to_simulation(
    data_repository, filter_repository, metric_repository
) -> None:
    repo = SimulationRepository(data_repository, filter_repository, metric_repository)
    sim = repo.create_simulation(_make_scg(data_repository))
    so = _run_output(repo, sim.uid)
    repo.create_iteration(sim.uid, so.uid)

    other_sim = repo.create_simulation(
        _make_scg(data_repository, variable_name="income")
    )
    other_so = _run_output(repo, other_sim.uid)
    repo.create_iteration(other_sim.uid, other_so.uid)

    sim_iterations = repo.iterations_for_sim(sim.uid)
    assert [it.uid for it in sim_iterations] == [IterationID(int=1)]
    assert repo.iterations_for_sim(other_sim.uid)[0].uid == IterationID(int=2)


def test_remove_simulation_cascades_iterations(
    data_repository, filter_repository, metric_repository
) -> None:
    repo = SimulationRepository(data_repository, filter_repository, metric_repository)
    sim = repo.create_simulation(_make_scg(data_repository))
    so = _run_output(repo, sim.uid)
    iteration = repo.create_iteration(sim.uid, so.uid)
    assert iteration.uid in repo.iterations

    repo.remove_simulation(sim.uid)

    assert iteration.uid not in repo.iterations
    assert repo.iterations_for_sim(sim.uid) == ()
    # Caches (SOs included) are retained by design; only iterations cascade.
    assert so.uid in repo.sos


def test_remove_iteration_removes_single(
    data_repository, filter_repository, metric_repository
) -> None:
    repo = SimulationRepository(data_repository, filter_repository, metric_repository)
    sim = repo.create_simulation(_make_scg(data_repository))
    so = _run_output(repo, sim.uid)
    iteration = repo.create_iteration(sim.uid, so.uid)

    repo.remove_iteration(iteration.uid)

    assert iteration.uid not in repo.iterations
    assert sim.uid in repo.simulations
    assert so.uid in repo.sos
    # Ids are max(existing)+1, so the freed slot is reused.
    replacement = repo.create_iteration(sim.uid, so.uid)
    assert replacement.uid == IterationID(int=1)


def test_get_iteration_table_always_has_dev_bad_rate_column(
    data_repository, filter_repository, metric_repository
) -> None:
    repo = SimulationRepository(data_repository, filter_repository, metric_repository)
    sim = repo.create_simulation(_make_scg(data_repository))
    so = _run_output(repo, sim.uid)
    iteration = repo.create_iteration(sim.uid, so.uid)

    result = repo.get_iteration_table(
        iteration.uid, metric_ids=(MetricID.DEV_UNT_BAD_RATE,)
    )

    assert result.errors == []
    assert result.columns == [("Dev # Bad Rate", result.columns[0][1])]
    name, metric = result.columns[0]
    assert name == "Dev # Bad Rate"
    assert metric.is_percentage
    # Segments mirror the output's groups in band order.
    assert list(result.segments) == list(so.groups)
    # Every segment row carries the dev bad rate key.
    for seg_id in result.segments:
        assert "Dev # Bad Rate" in result.values[seg_id]
    assert any(
        result.values[seg_id]["Dev # Bad Rate"] is not None
        for seg_id in result.segments
    )


def test_get_iteration_table_total_row(
    data_repository, filter_repository, metric_repository
) -> None:
    repo = SimulationRepository(data_repository, filter_repository, metric_repository)
    sim = repo.create_simulation(_make_scg(data_repository))
    so = _run_output(repo, sim.uid)
    iteration = repo.create_iteration(sim.uid, so.uid)

    result = repo.get_iteration_table(
        iteration.uid,
        metric_ids=(MetricID.DEV_UNT_BAD_RATE,),
        show_total_row=True,
    )

    assert result.errors == []
    assert set(result.total) == {"Dev # Bad Rate"}
    assert result.total["Dev # Bad Rate"] is not None

    without = repo.get_iteration_table(
        iteration.uid, metric_ids=(MetricID.DEV_UNT_BAD_RATE,)
    )
    assert without.total == {}


def test_get_iteration_table_total_not_scaled(
    data_repository, filter_repository, metric_repository
) -> None:
    """The total row is the ungrouped aggregate and never carries scalars."""
    repo = SimulationRepository(data_repository, filter_repository, metric_repository)
    scalar_config = ScalarConfig(
        ulr_scalar=LossRateScalar(
            loss_rate_type=LossRateTypes.ULR,
            current_rate=0.01,
            lifetime_rate=0.02,
        )
    )
    sim = repo.create_simulation(
        _make_scg(data_repository, scalar_config=scalar_config)
    )
    so = _run_output(repo, sim.uid)
    iteration = repo.create_iteration(sim.uid, so.uid)

    scaled = repo.get_iteration_table(
        iteration.uid,
        metric_ids=(MetricID.DEV_UNT_BAD_RATE,),
        scalars_enabled=True,
        show_total_row=True,
    )
    unscaled = repo.get_iteration_table(
        iteration.uid,
        metric_ids=(MetricID.DEV_UNT_BAD_RATE,),
        scalars_enabled=False,
        show_total_row=True,
    )

    assert scaled.total["Dev # Bad Rate"] is not None
    assert scaled.total["Dev # Bad Rate"] == pytest.approx(
        unscaled.total["Dev # Bad Rate"]
    )
    # ...while individual bands are still scaled.
    factors = {
        seg_id: max(seg.maf(LossRateTypes.ULR) * 2.0, 1.0)
        for seg_id, seg in scaled.segments.items()
    }
    assert {factors[seg_id] for seg_id in scaled.segments} != {1.0}


def test_get_iteration_table_applies_scalars_to_bad_rate_only(
    data_repository, filter_repository, metric_repository
) -> None:
    repo = SimulationRepository(data_repository, filter_repository, metric_repository)
    scalar_config = ScalarConfig(
        ulr_scalar=LossRateScalar(
            loss_rate_type=LossRateTypes.ULR,
            current_rate=0.01,
            lifetime_rate=0.02,
        )
    )
    sim = repo.create_simulation(
        _make_scg(data_repository, scalar_config=scalar_config)
    )
    so = _run_output(repo, sim.uid)
    iteration = repo.create_iteration(sim.uid, so.uid)

    unscaled = repo.get_iteration_table(
        iteration.uid, metric_ids=(MetricID.DEV_UNT_BAD_RATE,), scalars_enabled=False
    )
    scaled = repo.get_iteration_table(
        iteration.uid, metric_ids=(MetricID.DEV_UNT_BAD_RATE,), scalars_enabled=True
    )

    for seg_id in scaled.segments:
        seg = scaled.segments[seg_id]
        factor = max(seg.maf(LossRateTypes.ULR) * 2.0, 1.0)
        expected = unscaled.values[seg_id]["Dev # Bad Rate"]
        if expected is None:
            assert scaled.values[seg_id]["Dev # Bad Rate"] is None
        else:
            assert scaled.values[seg_id]["Dev # Bad Rate"] == pytest.approx(
                expected * factor
            )


def test_get_iteration_table_builtin_bad_rates_each_selectable(
    data_repository, filter_repository, metric_repository
) -> None:
    """Each of the four built-in bad rates renders and is keyed by its name."""
    repo = SimulationRepository(data_repository, filter_repository, metric_repository)
    sim = repo.create_simulation(_make_scg(data_repository))
    so = _run_output(repo, sim.uid)
    iteration = repo.create_iteration(sim.uid, so.uid)

    for metric_id, expected_name in (
        (MetricID.DEV_UNT_BAD_RATE, "Dev # Bad Rate"),
        (MetricID.DEV_DLR_BAD_RATE, "Dev $ Bad Rate"),
        (MetricID.TST_UNT_BAD_RATE, "Test # Bad Rate"),
        (MetricID.TST_DLR_BAD_RATE, "Test $ Bad Rate"),
    ):
        result = repo.get_iteration_table(iteration.uid, metric_ids=(metric_id,))
        assert result.errors == []
        assert [name for name, _ in result.columns] == [expected_name]
        for seg_id in result.segments:
            assert expected_name in result.values[seg_id]


def test_get_iteration_table_undefined_builtin_yields_empty_cells(
    data_repository, filter_repository, metric_repository
) -> None:
    """An unconfigured (None) bad rate still renders as selectable with empty cells."""
    repo = SimulationRepository(data_repository, filter_repository, metric_repository)
    sim = repo.create_simulation(_make_scg(data_repository))  # only dev_unit set
    so = _run_output(repo, sim.uid)
    iteration = repo.create_iteration(sim.uid, so.uid)

    result = repo.get_iteration_table(
        iteration.uid, metric_ids=(MetricID.TST_DLR_BAD_RATE,)
    )
    assert result.errors == []
    assert [name for name, _ in result.columns] == ["Test $ Bad Rate"]
    assert all(
        result.values[seg_id]["Test $ Bad Rate"] is None for seg_id in result.segments
    )


def test_get_iteration_table_scales_dev_not_test(
    data_repository, filter_repository, metric_repository
) -> None:
    """When scalars are enabled the dev bad rate is scaled, the test is not."""
    repo = SimulationRepository(data_repository, filter_repository, metric_repository)
    scalar_config = ScalarConfig(
        ulr_scalar=LossRateScalar(
            loss_rate_type=LossRateTypes.ULR,
            current_rate=0.01,
            lifetime_rate=0.02,
        )
    )
    sim = repo.create_simulation(
        _make_scg(
            data_repository,
            scalar_config=scalar_config,
            test_unit_bad_rate=BadRateConfig(
                loss_rate_type=LossRateTypes.ULR,
                numerator_col="unt_bad",
                data_source_ids=tuple(data_repository.data_sources.keys()),
                is_annualized=False,
            ),
        )
    )
    so = _run_output(repo, sim.uid)
    iteration = repo.create_iteration(sim.uid, so.uid)

    ids = (MetricID.DEV_UNT_BAD_RATE, MetricID.TST_UNT_BAD_RATE)
    unscaled = repo.get_iteration_table(iteration.uid, metric_ids=ids, scalars_enabled=False)
    scaled = repo.get_iteration_table(iteration.uid, metric_ids=ids, scalars_enabled=True)

    for seg_id in scaled.segments:
        seg = scaled.segments[seg_id]
        factor = max(seg.maf(LossRateTypes.ULR) * 2.0, 1.0)
        dev_unscaled = unscaled.values[seg_id]["Dev # Bad Rate"]
        if dev_unscaled is not None:
            assert scaled.values[seg_id]["Dev # Bad Rate"] == pytest.approx(
                dev_unscaled * factor
            )
        assert (
            scaled.values[seg_id]["Test # Bad Rate"]
            == unscaled.values[seg_id]["Test # Bad Rate"]
        )


def test_get_iteration_table_applies_filters(
    data_repository, filter_repository, metric_repository
) -> None:
    filter_repository.create_filter("High Score", "credit_score > 700")
    credential_filter = next(iter(filter_repository.filters))
    repo = SimulationRepository(data_repository, filter_repository, metric_repository)
    sim = repo.create_simulation(_make_scg(data_repository))
    so = _run_output(repo, sim.uid)
    iteration = repo.create_iteration(sim.uid, so.uid)

    unfiltered = repo.get_iteration_table(
        iteration.uid, metric_ids=(MetricID.DEV_UNT_BAD_RATE,)
    )
    filtered = repo.get_iteration_table(
        iteration.uid,
        metric_ids=(MetricID.DEV_UNT_BAD_RATE,),
        filter_ids=(credential_filter,),
    )

    assert [n for n, _ in unfiltered.columns] == [n for n, _ in filtered.columns]
    changed = [
        seg_id
        for seg_id in unfiltered.segments
        if unfiltered.values[seg_id]["Dev # Bad Rate"]
        != filtered.values[seg_id]["Dev # Bad Rate"]
    ]
    assert changed, "At least one segment's bad rate should change under a filter."


def test_get_iteration_table_includes_and_scopes_user_metrics(tmp_path) -> None:
    """User metrics join the table and are evaluated on their own sources."""
    data_repository, _ = _make_two_sources(tmp_path)
    metric_repository = _metric_repo(data_repository)
    filter_repository = _filter_repo(data_repository)

    second_only = data_repository.data_sources.keys()
    second_ds = list(second_only)[1]
    metric_ids = []
    for name, query, sources in (
        ("Avg Credit", "`credit_score`.mean()", list(second_only)),
        ("Avg Credit (2nd)", "`credit_score`.mean()", [second_ds]),
    ):
        metric_repository.create_metric(
            name=name,
            query=query,
            is_cumulative=False,
            use_thousand_sep=True,
            is_percentage=False,
            decimal_places=2,
            data_source_ids=sources,
        )
        metric_ids.append(next(reversed(metric_repository.metrics)))

    repo = SimulationRepository(data_repository, filter_repository, metric_repository)
    sim = repo.create_simulation(_make_scg(data_repository))
    so = _run_output(repo, sim.uid)
    iteration = repo.create_iteration(sim.uid, so.uid)

    result = repo.get_iteration_table(
        iteration.uid, metric_ids=(MetricID.DEV_UNT_BAD_RATE, *metric_ids)
    )

    names = [name for name, _ in result.columns]
    assert names == ["Dev # Bad Rate", "Avg Credit", "Avg Credit (2nd)"]
    assert any(
        result.values[seg_id]["Avg Credit"] is not None for seg_id in result.segments
    )
    assert any(
        result.values[seg_id]["Avg Credit (2nd)"] is not None
        for seg_id in result.segments
    )


def test_get_iteration_table_drops_invalid_metric_with_warning(tmp_path) -> None:
    """A metric undefined for its selected sources is dropped with a warning."""
    data_repository, _ = _make_two_sources(tmp_path)
    metric_repository = _metric_repo(data_repository)
    filter_repository = _filter_repo(data_repository)

    # "income" exists only in the first source, so it is undefined for both.
    # The public create_metric API refuses such a query, so inject directly.
    from risc_tool_v2.data.metric.models.metric import Metric

    invalid_metric = Metric(
        name="Mean Income",
        query="`income`.mean()",
        data_source_ids=list(data_repository.data_sources.keys()),
        is_cumulative=False,
        use_thousand_sep=True,
        is_percentage=False,
        decimal_places=2,
    )
    metric_repository.metrics[invalid_metric.uid] = invalid_metric
    metric_id = invalid_metric.uid

    repo = SimulationRepository(data_repository, filter_repository, metric_repository)
    sim = repo.create_simulation(_make_scg(data_repository))
    so = _run_output(repo, sim.uid)
    iteration = repo.create_iteration(sim.uid, so.uid)

    result = repo.get_iteration_table(
        iteration.uid, metric_ids=(MetricID.DEV_UNT_BAD_RATE, metric_id)
    )

    assert [name for name, _ in result.columns] == ["Dev # Bad Rate"]
    assert any("Mean Income" in warning for warning in result.warnings)


def test_serialization_round_trip_preserves_iterations(
    data_repository, filter_repository, metric_repository
) -> None:
    repo = SimulationRepository(data_repository, filter_repository, metric_repository)
    sim = repo.create_simulation(_make_scg(data_repository))
    so = _run_output(repo, sim.uid)
    iteration = repo.create_iteration(sim.uid, so.uid)

    data = repo.to_dict()
    restored = SimulationRepository.from_dict(
        data,
        data_repository=data_repository,
        filter_repository=filter_repository,
        metric_repository=metric_repository,
    )

    assert iteration.uid in restored.iterations
    restored_iteration = restored.iterations[iteration.uid]
    assert restored_iteration.name == iteration.name
    assert restored_iteration.simulation_id == iteration.simulation_id
    assert restored_iteration.scg_id == iteration.scg_id
    assert restored_iteration.sc_id == iteration.sc_id
    assert restored_iteration.so_id == iteration.so_id
    assert restored_iteration.variable_name == iteration.variable_name

    # Repo state after restore: sim status and cached outputs preserved.
    assert restored.simulations[sim.uid].status == SimulationStatus.COMPLETED
    assert restored.sos[so.uid].uid == so.uid

    # Idempotent create still holds after a round trip.
    duplicate = restored.create_iteration(sim.uid, so.uid)
    assert duplicate.uid == iteration.uid


def _make_two_sources(tmp_path: Path):
    """Return (data_repository with two sources, ids). The second source has
    only credit_score/unt_bad/status (no income)."""
    from risc_tool_v2.data.data_source.repositories.data_repository import (
        DataRepository,
    )

    source_df = pd.DataFrame({
        "credit_score": [650, 700, 750, 620],
        "income": [50000, 60000, 75000, 45000],
        "unt_bad": [0, 0, 0, 1],
        "dlr_bad": [0.0, 0.0, 0.0, 500.0],
        "status": ["Approved", "Approved", "Approved", "Declined"],
    })
    second_df = pd.DataFrame({
        "credit_score": [800, 580],
        "unt_bad": [0, 1],
        "status": ["Approved", "Declined"],
    })
    first_file = tmp_path / "first.csv"
    second_file = tmp_path / "second.csv"
    source_df.to_csv(first_file, index=False)
    second_df.to_csv(second_file, index=False)

    read_config = ReadConfig(read_mode="CSV", delimiter=",", header_row=0)
    data_repository = DataRepository()
    data_repository.add_data_source(
        label="First", filepath=first_file, read_config=read_config
    )
    data_repository.add_data_source(
        label="Second", filepath=second_file, read_config=read_config
    )
    return data_repository, list(data_repository.data_sources.keys())


def _metric_repo(data_repository):
    from risc_tool_v2.data.metric.repositories.metric_repository import (
        MetricRepository,
    )

    return MetricRepository(data_repository=data_repository)


def _filter_repo(data_repository):
    from risc_tool_v2.data.filter.repositories.filter_repository import (
        FilterRepository,
    )

    return FilterRepository(data_repository=data_repository)
