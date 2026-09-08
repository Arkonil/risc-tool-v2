from collections import OrderedDict
from pathlib import Path

import pandas as pd

from risc_tool_v2.data.core.enums import LossRateTypes, VariableType
from risc_tool_v2.data.core.uid import DataSourceID, FilterID
from risc_tool_v2.data.data_source.models.data_source import DataSource, ReadConfig
from risc_tool_v2.data.data_source.repositories.data_repository import DataRepository
from risc_tool_v2.data.filter.repositories.filter_repository import FilterRepository
from risc_tool_v2.data.metric.repositories.metric_repository import MetricRepository
from risc_tool_v2.data.simulation.models.risk_segment import RiskSegmentConfig
from risc_tool_v2.data.simulation.models.scalar import ScalarConfig
from risc_tool_v2.data.simulation.models.simulation import Simulation, SimulationStatus
from risc_tool_v2.data.simulation.models.simulation_config import (
    BadRateConfig,
    SimulationConfig,
    SimulationConfigGenerator,
    SimulationOutput,
)
from risc_tool_v2.data.simulation.repositories.simulation_repository import (
    SimulationRepository,
)


def _make_sc(data_repository) -> SimulationConfig:
    return SimulationConfig(
        risk_segment_config=RiskSegmentConfig(),
        dev_unit_bad_rate=BadRateConfig(
            loss_rate_type=LossRateTypes.ULR,
            numerator_col="unt_bad",
            data_source_ids=(next(iter(data_repository.data_sources)),),
            is_annualized=True,
        ),
        dev_dollar_bad_rate=None,
        test_unit_bad_rate=None,
        test_dollar_bad_rate=None,
        bad_rate_type=LossRateTypes.ULR,
        scalar_config=ScalarConfig(),
        variable_name="credit_score",
        variable_type=VariableType.NUMERICAL,
    )


def _make_scg(data_repository) -> SimulationConfigGenerator:
    return SimulationConfigGenerator(name="base", **_sc_fields(data_repository))


def _sc_fields(data_repository) -> dict:
    sc = _make_sc(data_repository)
    return {
        "risk_segment_config": sc.risk_segment_config,
        "dev_unit_bad_rate": sc.dev_unit_bad_rate,
        "dev_dollar_bad_rate": sc.dev_dollar_bad_rate,
        "test_unit_bad_rate": sc.test_unit_bad_rate,
        "test_dollar_bad_rate": sc.test_dollar_bad_rate,
        "bad_rate_type": sc.bad_rate_type,
        "scalar_config": sc.scalar_config,
        "filter_ids": sc.filter_ids,
        "remove_outliers": sc.remove_outliers,
        "variable_name": sc.variable_name,
        "variable_type": sc.variable_type,
        "auto_band": sc.auto_band,
        "use_scalars": sc.use_scalars,
    }


def _scg_of(repo: SimulationRepository, sim: Simulation) -> SimulationConfigGenerator:
    """Resolve a Simulation's SCG from the repository store."""
    return repo.scgs[sim.simulation_config_generator_id]


def _add_divergent_csv_sources(
    data_repository: DataRepository, tmp_path: Path
) -> tuple[DataSourceID, DataSourceID]:
    """Register two data sources with divergent column sets.

    The train-like source holds ``credit_default_flag``; the val-like source
    holds ``val_only_col`` instead. Returns the two data source IDs in order.
    """
    train_df = pd.DataFrame({
        "credit_score": [650, 700, 750, 620],
        "unt_bad": [0, 0, 0, 1],
        "credit_default_flag": [0, 0, 0, 1],
    })

    val_df = pd.DataFrame({
        "credit_score": [800, 580, 710],
        "unt_bad": [0, 1, 0],
        "val_only_col": [10, 20, 30],
    })

    train_file = tmp_path / "train_dev.csv"
    val_file = tmp_path / "val_dev.csv"
    train_df.to_csv(train_file, index=False)
    val_df.to_csv(val_file, index=False)

    read_config = ReadConfig(read_mode="CSV", delimiter=",", header_row=0)
    train_ds = data_repository.add_data_source(
        label="Train Dev", filepath=train_file, read_config=read_config
    )
    val_ds = data_repository.add_data_source(
        label="Val Dev", filepath=val_file, read_config=read_config
    )
    return train_ds.uid, val_ds.uid


def test_create_and_get_simulation(
    data_repository, filter_repository, metric_repository
) -> None:
    repo = SimulationRepository(data_repository, filter_repository, metric_repository)
    scg = _make_scg(data_repository)

    sim = repo.create_simulation(scg)

    assert sim.simulation_config_generator_id == scg.uid
    assert sim.status == SimulationStatus.PENDING
    assert sim.uid in repo.simulations
    assert repo.get_simulation(sim.uid).uid == sim.uid


def test_created_simulations_get_unique_ids(
    data_repository, filter_repository, metric_repository
) -> None:
    repo = SimulationRepository(data_repository, filter_repository, metric_repository)
    scg = _make_scg(data_repository)

    sim1 = repo.create_simulation(scg)
    sim2 = repo.create_simulation(scg)

    assert sim1.uid != sim2.uid


def test_update_simulation_scg_repoints_and_preserves_uid(
    data_repository, filter_repository, metric_repository
) -> None:
    """Editing an existing simulation's SCG repoints it at the new SCG,
    preserves the simulation uid, resets it to PENDING, and retains the old
    SCG/SC/SO in the cache."""
    repo = SimulationRepository(data_repository, filter_repository, metric_repository)
    sim = repo.create_simulation(_make_scg(data_repository))
    old_scg_uid = sim.simulation_config_generator_id
    repo.run_simulation(sim.uid)
    old_so = repo.get_simulation_outputs(sim.uid)[0]

    edited_scg = _make_scg(data_repository).with_updates(variable_name="edited_var")

    updated = repo.update_simulation_scg(sim.uid, edited_scg)

    assert updated.uid == sim.uid
    assert updated.simulation_config_generator_id == edited_scg.uid
    assert updated.simulation_config_generator_id != old_scg_uid
    assert updated.status == SimulationStatus.PENDING
    assert edited_scg.uid in repo.scgs
    assert old_scg_uid in repo.scgs
    assert old_so.uid in repo.sos
    assert repo.get_simulation_outputs(sim.uid) == ()


def test_update_simulation_scg_recycles_shared_outputs(
    data_repository, filter_repository, metric_repository
) -> None:
    """Editing a simulation back to an SCG content that already has a cached SO
    recycles that output through the content-addressed chain."""
    repo = SimulationRepository(data_repository, filter_repository, metric_repository)
    scg = _make_scg(data_repository)
    sim = repo.create_simulation(scg)
    repo.run_simulation(sim.uid)
    first_so = repo.get_simulation_outputs(sim.uid)[0]

    edited_scg = scg.with_updates(variable_name="income")
    repo.update_simulation_scg(sim.uid, edited_scg)
    repo.run_simulation(sim.uid)
    second_so = repo.get_simulation_outputs(sim.uid)[0]
    assert second_so.uid != first_so.uid

    repo.update_simulation_scg(sim.uid, scg)
    repo.run_simulation(sim.uid)
    assert repo.get_simulation_outputs(sim.uid)[0].uid == first_so.uid


def test_run_simulation_produces_output_and_caches(
    data_repository, filter_repository, metric_repository
) -> None:
    repo = SimulationRepository(data_repository, filter_repository, metric_repository)
    sim = repo.create_simulation(_make_scg(data_repository))
    generated_sc = _scg_of(repo, sim).get_configs()[0]

    first = repo.run_simulation(sim.uid)
    second = repo.run_simulation(sim.uid)

    assert first.status == SimulationStatus.COMPLETED
    assert second.status == SimulationStatus.COMPLETED
    outputs_first = repo.get_simulation_outputs(sim.uid)
    outputs_second = repo.get_simulation_outputs(sim.uid)
    assert len(outputs_first) == 1
    assert outputs_first[0].uid == outputs_second[0].uid
    assert generated_sc.uid in repo.scs
    assert repo.get_so_for_sc(generated_sc.uid) is not None


def _make_divergent_scg(
    train_id: DataSourceID,
    numerator_col: str,
    data_source_ids: tuple[DataSourceID, ...],
) -> SimulationConfigGenerator:
    return SimulationConfigGenerator(
        name="divergent",
        risk_segment_config=RiskSegmentConfig(),
        dev_unit_bad_rate=BadRateConfig(
            loss_rate_type=LossRateTypes.ULR,
            numerator_col=numerator_col,
            data_source_ids=data_source_ids,
            is_annualized=True,
        ),
        dev_dollar_bad_rate=None,
        test_unit_bad_rate=None,
        test_dollar_bad_rate=None,
        bad_rate_type=LossRateTypes.ULR,
        scalar_config=ScalarConfig(),
        variable_name="credit_score",
        variable_type=VariableType.NUMERICAL,
    )


def test_run_scopes_to_dev_bad_rate_data_sources(tmp_path) -> None:
    """A simulation runs only on the dev bad rate's selected data sources.

    Regression for the train/val divergence: the numerator exists only in the
    selected (train-like) source, so validation must scope to that source's
    columns rather than the intersection across all sources.
    """
    data_repository = DataRepository()
    train_id, _val_id = _add_divergent_csv_sources(data_repository, tmp_path)
    filter_repository = FilterRepository(data_repository=data_repository)
    metric_repository = MetricRepository(data_repository=data_repository)
    repo = SimulationRepository(data_repository, filter_repository, metric_repository)

    scg = _make_divergent_scg(train_id, "credit_default_flag", (train_id,))
    sim = repo.create_simulation(scg)

    result = repo.run_simulation(sim.uid)

    assert result.status == SimulationStatus.COMPLETED
    outputs = repo.get_simulation_outputs(sim.uid)
    assert len(outputs) == 1
    assert "credit_score" == outputs[0].variable_name


def test_run_rejects_column_undefined_in_selected_sources(tmp_path) -> None:
    """A metric column present only outside the selected dev sources fails."""
    data_repository = DataRepository()
    train_id, _val_id = _add_divergent_csv_sources(data_repository, tmp_path)
    filter_repository = FilterRepository(data_repository=data_repository)
    metric_repository = MetricRepository(data_repository=data_repository)
    repo = SimulationRepository(data_repository, filter_repository, metric_repository)

    scg = _make_divergent_scg(train_id, "val_only_col", (train_id,))
    sim = repo.create_simulation(scg)

    result = repo.run_simulation(sim.uid)

    assert result.status == SimulationStatus.FAILED
    assert result.error_message is not None
    assert "val_only_col" in result.error_message
    assert "not found in the data" in result.error_message


def test_run_without_dev_data_sources_fails_with_clear_message(tmp_path) -> None:
    """A dev bad rate with no data sources fails with a clear run error."""
    data_repository = DataRepository()
    train_id, _val_id = _add_divergent_csv_sources(data_repository, tmp_path)
    filter_repository = FilterRepository(data_repository=data_repository)
    metric_repository = MetricRepository(data_repository=data_repository)
    repo = SimulationRepository(data_repository, filter_repository, metric_repository)

    scg = _make_divergent_scg(train_id, "credit_default_flag", ())
    sim = repo.create_simulation(scg)

    result = repo.run_simulation(sim.uid)

    assert result.status == SimulationStatus.FAILED
    assert result.error_message is not None
    assert "data source" in result.error_message
    assert "dev bad rate" in result.error_message


def test_get_simulation_outputs_via_chain_returns_cached_so(
    data_repository, filter_repository, metric_repository
) -> None:
    """SOs are resolved via sim -> scg -> sc -> so, not stored on the sim."""
    repo = SimulationRepository(data_repository, filter_repository, metric_repository)
    sim = repo.create_simulation(_make_scg(data_repository))
    scg_id = sim.simulation_config_generator_id

    assert repo.get_simulation_outputs(sim.uid) == ()

    repo.run_simulation(sim.uid)
    outputs = repo.get_simulation_outputs(sim.uid)
    assert len(outputs) == 1
    so = outputs[0]
    assert so.simulation_config_id == so.simulation_config_hash
    assert repo.scgs[scg_id].get_configs()[0].uid == so.simulation_config_hash

    # Group keys are the risk-segment identities of the SCG's segments.
    scg_segment_ids = set(repo.scgs[scg_id].risk_segment_config.segments)
    assert set(so.groups) <= scg_segment_ids

    # Re-running recycles the same cached SO (no re-generation).
    repo.run_simulation(sim.uid)
    assert repo.get_simulation_outputs(sim.uid)[0].uid == so.uid


def test_serialization_round_trip_preserves_outputs(
    data_repository, filter_repository, metric_repository
) -> None:
    """to_dict/from_dict round-trips the sim->scg->sc->so chain and SO cache."""
    repo = SimulationRepository(data_repository, filter_repository, metric_repository)
    sim = repo.create_simulation(_make_scg(data_repository))
    repo.run_simulation(sim.uid)
    original_outputs = repo.get_simulation_outputs(sim.uid)
    assert len(original_outputs) == 1

    data = repo.to_dict()
    restored = SimulationRepository.from_dict(
        data,
        data_repository=data_repository,
        filter_repository=filter_repository,
        metric_repository=metric_repository,
    )

    restored_outputs = restored.get_simulation_outputs(sim.uid)
    assert len(restored_outputs) == 1
    assert restored_outputs[0].uid == original_outputs[0].uid
    assert restored.simulations[sim.uid].status == SimulationStatus.COMPLETED

    restored_scg = _scg_of(restored, restored.simulations[sim.uid])
    assert restored_scg.uid == sim.simulation_config_generator_id


def test_remove_simulation_cleans_up(
    data_repository, filter_repository, metric_repository
) -> None:
    repo = SimulationRepository(data_repository, filter_repository, metric_repository)
    sim = repo.create_simulation(_make_scg(data_repository))
    scg_uid = _scg_of(repo, sim).uid

    repo.remove_simulation(sim.uid)

    assert sim.uid not in repo.simulations
    assert scg_uid not in repo.scgs


def test_on_dependency_remap_data_source_ids(
    data_repository, filter_repository, metric_repository
) -> None:
    repo = SimulationRepository(data_repository, filter_repository, metric_repository)
    sim = repo.create_simulation(_make_scg(data_repository))
    scg = _scg_of(repo, sim)

    old_scg_uid = scg.uid
    assert scg.dev_unit_bad_rate is not None

    old_ds = next(iter(data_repository.data_sources))
    new_ds = DataSourceID(int=2)
    repo.on_dependency_remap({DataSourceID: {old_ds: new_ds}})

    updated = repo.simulations[sim.uid]
    new_scg = _scg_of(repo, updated)
    new_sc = new_scg.get_configs()[0]

    assert new_scg.dev_unit_bad_rate is not None
    assert new_scg.dev_unit_bad_rate.data_source_ids == (new_ds,)
    assert new_sc.dev_unit_bad_rate is not None
    assert new_sc.dev_unit_bad_rate.data_source_ids == (new_ds,)
    assert new_scg.uid != old_scg_uid
    assert new_scg.uid in repo.scgs
    assert updated.status == SimulationStatus.PENDING


def test_on_dependency_remap_filter_ids(
    data_repository, filter_repository, metric_repository
) -> None:
    repo = SimulationRepository(data_repository, filter_repository, metric_repository)
    scg = _make_scg(data_repository).with_updates(
        filter_ids=(FilterID(int=1), FilterID(int=99))
    )
    sim = repo.create_simulation(scg)
    old_scg_uid = scg.uid

    old_fid = FilterID(int=99)
    new_fid = FilterID(int=55)
    repo.on_dependency_remap({FilterID: {old_fid: new_fid}})

    updated = repo.simulations[sim.uid]
    new_scg = _scg_of(repo, updated)
    new_sc = new_scg.get_configs()[0]

    assert new_scg.filter_ids == (FilterID(int=1), new_fid)
    assert new_sc.filter_ids == (FilterID(int=1), new_fid)
    assert new_scg.uid != old_scg_uid
    assert updated.status == SimulationStatus.PENDING


def test_on_dependency_remap_combined(
    data_repository, filter_repository, metric_repository
) -> None:
    repo = SimulationRepository(data_repository, filter_repository, metric_repository)
    scg = _make_scg(data_repository).with_updates(filter_ids=(FilterID(int=1),))
    sim = repo.create_simulation(scg)

    old_ds = next(iter(data_repository.data_sources))
    new_ds = DataSourceID(int=2)
    old_fid = FilterID(int=1)
    new_fid = FilterID(int=7)
    repo.on_dependency_remap({
        DataSourceID: {old_ds: new_ds},
        FilterID: {old_fid: new_fid},
    })

    updated = repo.simulations[sim.uid]
    new_scg = _scg_of(repo, updated)
    new_sc = new_scg.get_configs()[0]

    assert new_scg.dev_unit_bad_rate is not None
    assert new_scg.dev_unit_bad_rate.data_source_ids == (new_ds,)
    assert new_sc.dev_unit_bad_rate is not None
    assert new_sc.dev_unit_bad_rate.data_source_ids == (new_ds,)
    assert new_scg.filter_ids == (new_fid,)
    assert new_sc.filter_ids == (new_fid,)


def test_on_dependency_remap_noop_leaves_configs_unchanged(
    data_repository, filter_repository, metric_repository
) -> None:
    repo = SimulationRepository(data_repository, filter_repository, metric_repository)
    scg = _make_scg(data_repository)
    sim = repo.create_simulation(scg)
    scg_uid = scg.uid
    sc_uid = scg.get_configs()[0].uid

    repo.on_dependency_remap({DataSourceID: {DataSourceID(int=5): DataSourceID(int=6)}})

    assert sim.uid in repo.simulations
    updated = repo.simulations[sim.uid]
    assert updated.simulation_config_generator_id == scg_uid
    assert scg_uid in repo.scgs
    assert sc_uid in repo.scs


def _make_orphan_so(sc: SimulationConfig) -> SimulationOutput:
    """Build a SimulationOutput directly (empty groups) without running the sim."""
    return SimulationOutput(
        simulation_config_id=sc.uid,
        simulation_config_hash=sc.uid,
        variable_name=sc.variable_name,
        variable_type=sc.variable_type,
        groups=OrderedDict(),
    )


def test_plain_update_retains_cache_but_resets_to_pending(
    data_repository, filter_repository, metric_repository
) -> None:
    """A non-remap dependency change retains all cached SCG/SC/SO entries
    (even stale ones) and only resets simulations back to PENDING."""
    repo = SimulationRepository(data_repository, filter_repository, metric_repository)
    sim = repo.create_simulation(_make_scg(data_repository))
    live_sc = _scg_of(repo, sim).get_configs()[0]
    repo.run_simulation(sim.uid)
    live_so = repo.get_so_for_sc(live_sc.uid)
    assert live_so is not None

    # An orphaned SC with a cached SO that is not referenced by any simulation.
    orphan_sc = _make_sc(data_repository).with_updates(variable_name="orphan")
    repo.scs[orphan_sc.uid] = orphan_sc
    orphan_so = _make_orphan_so(orphan_sc)
    repo.sos[orphan_so.uid] = orphan_so
    repo._so_cache[orphan_sc.uid] = orphan_so.uid

    repo.on_dependency_update({})

    assert repo.get_so_for_sc(live_sc.uid) == live_so
    assert repo.get_so_for_sc(orphan_sc.uid) == orphan_so
    assert repo.simulations[sim.uid].status == SimulationStatus.PENDING


def test_remap_recycles_shared_sc_outputs(
    data_repository, filter_repository, metric_repository
) -> None:
    """Identical SC content yields the same SC uid, so its cached SO is
    recycled automatically when a remap rebuilds the SCG."""
    repo = SimulationRepository(data_repository, filter_repository, metric_repository)
    sim = repo.create_simulation(_make_scg(data_repository))
    original_scg_uid = _scg_of(repo, sim).uid

    # An unrelated remap leaves the SCG content unchanged, so the same SCG is
    # re-registered under the same uid and the cached SO survives.
    repo.run_simulation(sim.uid)
    repo.on_dependency_remap({FilterID: {FilterID(int=900): FilterID(int=901)}})

    updated = repo.simulations[sim.uid]
    assert updated.simulation_config_generator_id == original_scg_uid
    sc = _scg_of(repo, updated).get_configs()[0]
    assert repo.get_so_for_sc(sc.uid) is not None

    # A remap that does change content builds a NEW SCG under a new uid, and the
    # new SC has no cached SO until re-run.
    registered_ds = next(iter(data_repository.data_sources))
    repo.on_dependency_remap({DataSourceID: {registered_ds: DataSourceID(int=3)}})
    new_scg = _scg_of(repo, repo.simulations[sim.uid])
    assert new_scg.uid != original_scg_uid
    new_sc = new_scg.get_configs()[0]
    assert new_sc.uid != sc.uid
    assert repo.get_so_for_sc(new_sc.uid) is None


def test_cache_retained_for_unreferenced_entries(
    data_repository, filter_repository, metric_repository
) -> None:
    """SCG/SC/SO caches are retained indefinitely, even when unreferenced by
    any live simulation."""
    repo = SimulationRepository(data_repository, filter_repository, metric_repository)
    sim = repo.create_simulation(_make_scg(data_repository))
    live_sc = _scg_of(repo, sim).get_configs()[0]
    repo.run_simulation(sim.uid)
    live_so = repo.get_so_for_sc(live_sc.uid)
    assert live_so is not None

    # Cache set of an unreferenced SCG/SC/SO.
    orphan_scg = SimulationConfigGenerator(name="orphan", **_sc_fields(data_repository))
    repo.scgs[orphan_scg.uid] = orphan_scg
    orphan_sc = _make_sc(data_repository).with_updates(variable_name="orphan_so")
    repo.scs[orphan_sc.uid] = orphan_sc
    orphan_so = _make_orphan_so(orphan_sc)
    repo.sos[orphan_so.uid] = orphan_so
    repo._so_cache[orphan_sc.uid] = orphan_so.uid

    repo.on_dependency_update({})

    assert repo.get_so_for_sc(live_sc.uid) == live_so
    assert repo.get_so_for_sc(orphan_sc.uid) == orphan_so
    assert orphan_scg.uid in repo.scgs
    assert orphan_sc.uid in repo.scs


def test_add_data_source_does_not_rebuild_scg(
    data_repository, filter_repository, metric_repository
) -> None:
    """Adding a data source must not rebuild any SCG; the SCG referencing a
    still-existing source keeps its content uid and the sim resets to PENDING."""
    repo = SimulationRepository(data_repository, filter_repository, metric_repository)
    registered = next(iter(data_repository.data_sources))
    sim = repo.create_simulation(
        _make_scg(data_repository).with_updates(
            dev_unit_bad_rate=BadRateConfig(
                loss_rate_type=LossRateTypes.ULR,
                numerator_col="unt_bad",
                data_source_ids=(registered,),
                is_annualized=True,
            )
        )
    )
    original_scg_uid = _scg_of(repo, sim).uid

    extra = DataSource(
        label="Extra Data",
        filepath=Path("unused.csv"),
        read_config=ReadConfig(),
    )
    data_repository.data_sources[extra.uid] = extra
    data_repository.notify_subscribers()

    assert _scg_of(repo, repo.simulations[sim.uid]).uid == (original_scg_uid)
    assert original_scg_uid in repo.scgs


def test_remove_filter_rebuilds_scg_retains_cache(
    data_repository, filter_repository, metric_repository
) -> None:
    """Removing a filter referenced by an SCG rebuilds a new SCG that no longer
    references the removed id, while the old SCG/SC/SO stay in the cache."""
    repo = SimulationRepository(data_repository, filter_repository, metric_repository)
    registered = next(iter(data_repository.data_sources))
    missing_fid = FilterID(int=4242)
    scg = _make_scg(data_repository).with_updates(
        dev_unit_bad_rate=BadRateConfig(
            loss_rate_type=LossRateTypes.ULR,
            numerator_col="unt_bad",
            data_source_ids=(registered,),
            is_annualized=True,
        ),
        filter_ids=(missing_fid,),
    )
    sim = repo.create_simulation(scg)
    old_scg_uid = scg.uid
    old_sc_uid = scg.get_configs()[0].uid

    repo.on_dependency_update({})

    updated = repo.simulations[sim.uid]
    new_scg = _scg_of(repo, updated)
    assert new_scg.uid != old_scg_uid
    assert new_scg.filter_ids == ()
    assert old_scg_uid in repo.scgs
    assert old_sc_uid in repo.scs
    assert updated.status == SimulationStatus.PENDING


def test_remove_data_source_rebuilds_scg_blanks_columns_retains(
    data_repository, filter_repository, metric_repository
) -> None:
    """Removing a data source referenced by a bad rate rebuilds a new SCG that
    drops the dangling source id and blanks the column selections, while the
    old SCG/SC/SO stay cached."""
    repo = SimulationRepository(data_repository, filter_repository, metric_repository)
    missing_ds = DataSourceID(int=9999)
    scg = _make_scg(data_repository).with_updates(
        dev_unit_bad_rate=BadRateConfig(
            loss_rate_type=LossRateTypes.ULR,
            numerator_col="unt_bad",
            data_source_ids=(missing_ds,),
            is_annualized=True,
        )
    )
    sim = repo.create_simulation(scg)
    old_scg_uid = scg.uid
    old_sc_uid = scg.get_configs()[0].uid

    repo.on_dependency_update({})

    updated = repo.simulations[sim.uid]
    new_scg = _scg_of(repo, updated)
    assert new_scg.uid != old_scg_uid
    assert new_scg.dev_unit_bad_rate is not None
    assert new_scg.dev_unit_bad_rate.data_source_ids == ()
    assert new_scg.dev_unit_bad_rate.numerator_col is None
    assert new_scg.dev_unit_bad_rate.denominator_col is None
    assert old_scg_uid in repo.scgs
    assert old_sc_uid in repo.scs
    assert updated.status == SimulationStatus.PENDING


def test_removal_of_unreferenced_entities_keeps_scg(
    data_repository, filter_repository, metric_repository
) -> None:
    """A removal that does not reference any simulation's SCG must not rebuild
    the SCG (no dangling references -> same content uid)."""
    repo = SimulationRepository(data_repository, filter_repository, metric_repository)
    registered = next(iter(data_repository.data_sources))
    sim = repo.create_simulation(
        _make_scg(data_repository).with_updates(
            dev_unit_bad_rate=BadRateConfig(
                loss_rate_type=LossRateTypes.ULR,
                numerator_col="unt_bad",
                data_source_ids=(registered,),
                is_annualized=True,
            )
        )
    )
    original_scg_uid = _scg_of(repo, sim).uid

    repo.on_dependency_update({})

    assert _scg_of(repo, repo.simulations[sim.uid]).uid == (original_scg_uid)
    assert repo.simulations[sim.uid].status == SimulationStatus.PENDING
