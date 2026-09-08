"""Repository for managing simulations and their configs/outputs with change notification."""

import typing as t
from collections import OrderedDict
from datetime import UTC, datetime

from risc_tool_v2.data.core.changes import BaseRepository
from risc_tool_v2.data.core.enums import LossRateTypes, Signature, VariableType
from risc_tool_v2.data.core.id_remap import Remaps, get_remap
from risc_tool_v2.data.core.types import ChangeIDs
from risc_tool_v2.data.core.uid import (
    DataSourceID,
    FilterID,
    IterationID,
    MetricID,
    RiskSegmentID,
    SimulationConfigGeneratorID,
    SimulationConfigID,
    SimulationID,
    SimulationOutputID,
)
from risc_tool_v2.data.data_source.repositories.data_repository import DataRepository
from risc_tool_v2.data.filter.repositories.filter_repository import FilterRepository
from risc_tool_v2.data.metric.repositories.metric_repository import MetricRepository
from risc_tool_v2.data.simulation.json.simulation_json import (
    SimulationJSON,
    SimulationRepositoryJSON,
)
from risc_tool_v2.data.simulation.models.groups import (
    CategoricalGroup,
    NumericalGroup,
)
from risc_tool_v2.data.simulation.models.iteration import SimulationIteration
from risc_tool_v2.data.simulation.models.simulation import Simulation, SimulationStatus
from risc_tool_v2.data.simulation.models.simulation_config import (
    BadRateConfig,
    SimulationConfig,
    SimulationConfigGenerator,
    SimulationOutput,
)
from risc_tool_v2.data.simulation.services.auto_band import (
    create_auto_categorical_bands,
    create_auto_numeric_bands,
)
from risc_tool_v2.data.simulation.services.iterate import (
    BandTableResult,
    evaluate_band_table,
)


class SimulationRepository(BaseRepository):
    """Manages Simulation objects (each referencing an SCG by ID) with caching by SC content hash."""

    @property
    def signature(self) -> Signature:
        return Signature.SIMULATION_REPOSITORY

    def __init__(
        self,
        data_repository: DataRepository,
        filter_repository: FilterRepository,
        metric_repository: MetricRepository,
    ) -> None:
        super().__init__(
            dependencies=[data_repository, filter_repository, metric_repository]
        )

        self.simulations: dict[SimulationID, Simulation] = {}
        self.scgs: dict[SimulationConfigGeneratorID, SimulationConfigGenerator] = {}
        self.scs: dict[SimulationConfigID, SimulationConfig] = {}
        self.sos: dict[SimulationOutputID, SimulationOutput] = {}
        # Cache: SC content hash -> SO (for recycling across simulations)
        self._so_cache: dict[SimulationConfigID, SimulationOutputID] = {}
        # Iterations derived from simulation outputs (sequential integer ids)
        self.iterations: dict[IterationID, SimulationIteration] = {}

        self.__data_repository = data_repository
        self.__filter_repository = filter_repository
        self.__metric_repository = metric_repository

    # Simulation lifecycle
    def create_simulation(self, scg: SimulationConfigGenerator) -> Simulation:
        """Create a new Simulation referencing the given SimulationConfigGenerator."""
        simulation = Simulation(
            simulation_config_generator_id=scg.uid,
            status=SimulationStatus.PENDING,
            created_at=datetime.now(UTC),
        )
        self.simulations[simulation.uid] = simulation
        self.scgs[scg.uid] = scg
        for sc in scg.get_configs():
            self.scs[sc.uid] = sc
        self.notify_subscribers()
        return simulation

    def get_simulation(self, sim_id: SimulationID) -> Simulation:
        """Get a Simulation by ID."""
        if sim_id not in self.simulations:
            raise ValueError(f"Simulation {sim_id} does not exist.")
        return self.simulations[sim_id]

    def _get_scg(self, sim: Simulation) -> SimulationConfigGenerator:
        """Resolve the Simulation's SCG from the repository store."""
        scg_id = sim.simulation_config_generator_id
        if scg_id not in self.scgs:
            raise KeyError(f"Simulation {sim.uid} references missing SCG {scg_id}.")
        return self.scgs[scg_id]

    def remove_simulation(self, sim_id: SimulationID) -> None:
        """Remove a Simulation, its SCG/SC/SO chain, and its iterations."""
        if sim_id not in self.simulations:
            return
        sim = self.simulations[sim_id]
        scg = self._get_scg(sim)
        for sc in scg.get_configs():
            self.scs.pop(sc.uid, None)
            self._so_cache.pop(sc.uid, None)
        self.scgs.pop(scg.uid, None)
        del self.simulations[sim_id]
        if self.iterations:
            # Cascade: iterations are derived from this simulation's outputs.
            self.iterations = {
                iter_id: iteration
                for iter_id, iteration in self.iterations.items()
                if iteration.simulation_id != sim_id
            }
        self.notify_subscribers()

    def update_simulation_scg(
        self, sim_id: SimulationID, new_scg: SimulationConfigGenerator
    ) -> Simulation:
        """Replace the SCG referenced by an existing Simulation.

        Registers the new SCG and its generated SCs (reusing existing entries
        so cached outputs are recycled), then repoints the Simulation at the new
        SCG and resets its lifecycle back to PENDING. The Simulation's own
        ``uid`` is preserved; the previous SCG/SC/SO stay in the cache.
        """
        sim = self.get_simulation(sim_id)
        self.scgs[new_scg.uid] = new_scg
        for sc in new_scg.get_configs():
            self.scs.setdefault(sc.uid, sc)
        updated = sim.with_updates(
            simulation_config_generator_id=new_scg.uid,
            status=SimulationStatus.PENDING,
            error_message=None,
            run_started_at=None,
            run_completed_at=None,
        )
        self.simulations[sim_id] = updated
        self.notify_subscribers()
        return updated

    # SO Generation (Core Simulation Execution)
    def _run_sc(self, sc: SimulationConfig) -> SimulationOutput:
        """Generate SO from SC using auto-banding; cache by SC content hash."""
        # 1. Check cache by SC content hash
        if sc.uid in self._so_cache:
            cached_so_id = self._so_cache[sc.uid]
            if cached_so_id in self.sos:
                return self.sos[cached_so_id]

        # 2. Get selected dev bad rate based on bad_rate_type
        if sc.bad_rate_type == LossRateTypes.ULR:
            bad_rate_config = sc.dev_unit_bad_rate
        else:
            bad_rate_config = sc.dev_dollar_bad_rate

        if bad_rate_config is None:
            raise ValueError(f"No dev bad rate configured for {sc.bad_rate_type.value}")

        if bad_rate_config.numerator_col is None:
            raise ValueError(
                f"No bad count column configured for {bad_rate_config.loss_rate_type.value}"
            )

        if not bad_rate_config.data_source_ids:
            raise ValueError(
                "No dev bad rate data sources configured; select at least one "
                "data source for the dev bad rate."
            )

        # 3. Get filtered LazyFrame scoped to the dev bad rate's data sources.
        # Metrics (and thus simulations) are defined only for their selected
        # data sources; outside of those they are undefined.
        data_filter = self.__filter_repository.get_combined_expression(
            list(sc.filter_ids), remove_outliers=sc.remove_outliers
        )
        lf = self.__data_repository.get_lazyframe(
            data_source_ids=list(bad_rate_config.data_source_ids)
        )
        lf = lf.filter(data_filter)

        # 4. Build Metric from BadRateConfig
        metric = bad_rate_config.to_metric(
            uid=MetricID.TEMPORARY,
            name=f"sim_{sc.uid}_bad_rate",
        )
        # Validate against the columns common to the selected dev data sources
        available_cols = [
            c[0]
            for c in self.__data_repository.common_columns(
                list(bad_rate_config.data_source_ids)
            )
        ]
        metric.validate_query(available_columns=available_cols)

        # 5. Run auto-banding
        if sc.variable_type == VariableType.NUMERICAL:
            groups = create_auto_numeric_bands(
                base_lf=lf,
                variable=sc.variable_name,
                risk_segment_config=sc.risk_segment_config,
                loss_rate_scalar=sc.scalar_config.get_scalar(
                    bad_rate_config.loss_rate_type
                ),
                numerator=bad_rate_config.numerator_col,
                denominator=bad_rate_config.denominator_col,
                mob=bad_rate_config.current_rate_mob,
                use_scalar=sc.use_scalars,
            )
        else:
            groups = create_auto_categorical_bands(
                base_lf=lf,
                variable=sc.variable_name,
                risk_segment_config=sc.risk_segment_config,
                loss_rate_scalar=sc.scalar_config.get_scalar(
                    bad_rate_config.loss_rate_type
                ),
                numerator=bad_rate_config.numerator_col,
                denominator=bad_rate_config.denominator_col,
                mob=bad_rate_config.current_rate_mob,
                use_scalar=sc.use_scalars,
            )

        # 6. Create SO
        so = SimulationOutput(
            simulation_config_id=sc.uid,
            simulation_config_hash=sc.uid,
            variable_name=sc.variable_name,
            variable_type=sc.variable_type,
            groups=t.cast(
                OrderedDict[RiskSegmentID, NumericalGroup | CategoricalGroup], groups
            ),
            created_at=datetime.now(UTC),
        )

        # 7. Cache and store
        self._so_cache[sc.uid] = so.uid
        self.sos[so.uid] = so
        return so

    def run_simulation(self, sim_id: SimulationID) -> Simulation:
        """Run a Simulation, producing an SO for every SC in its SCG.

        Each SC is run through :meth:`_run_sc`, which recycles an existing
        cached SimulationOutput when an SC with the same content hash is
        already present; otherwise a new SO is generated and stored. Outputs
        are reachable via the ``sim -> scg -> sc -> so`` chain, not stored
        directly on the Simulation.
        """
        sim = self.get_simulation(sim_id)
        scg = self._get_scg(sim)

        running = sim.with_updates(
            status=SimulationStatus.RUNNING,
            run_started_at=datetime.now(UTC),
            error_message=None,
        )
        self.simulations[sim_id] = running

        try:
            for sc in scg.get_configs():
                self._run_sc(sc)
        except Exception as exc:  # noqa: BLE001 - surface any run error on the sim
            failed = running.with_updates(
                status=SimulationStatus.FAILED,
                error_message=str(exc),
                run_completed_at=datetime.now(UTC),
            )
            self.simulations[sim_id] = failed
            self.notify_subscribers()
            return failed

        completed = running.with_updates(
            status=SimulationStatus.COMPLETED,
            run_completed_at=datetime.now(UTC),
            error_message=None,
        )
        self.simulations[sim_id] = completed
        self.notify_subscribers()
        return completed

    def get_simulation_outputs(
        self, sim_id: SimulationID
    ) -> tuple[SimulationOutput, ...]:
        """Resolve a Simulation's outputs via ``sim -> scg -> sc -> so``.

        Returns one SimulationOutput per SC in the SCG, in SC order. Only SCs
        that have a cached SO contribute; missing outputs are skipped.
        """
        sim = self.get_simulation(sim_id)
        outputs: list[SimulationOutput] = []
        for sc in self._get_scg(sim).get_configs():
            so = self.get_so_for_sc(sc.uid)
            if so is not None:
                outputs.append(so)
        return tuple(outputs)

    def get_so_for_sc(self, sc_id: SimulationConfigID) -> SimulationOutput | None:
        """Get the cached SO for a given SC."""
        if sc_id in self._so_cache:
            so_id = self._so_cache[sc_id]
            return self.sos.get(so_id)
        return None

    # Iterations (single-variable analyses derived from simulation outputs)
    def create_iteration(
        self, sim_id: SimulationID, so_id: SimulationOutputID
    ) -> SimulationIteration:
        """Create an iteration over one of a simulation's outputs.

        The iteration stores only references (``simulation_id``, ``scg_id``,
        ``sc_id``, ``so_id``); banding and configuration resolve from the
        cached SCG/SC/SO. Iteration identity is a sequential integer assigned
        in creation order. Creating an iteration for an output that already
        has one is idempotent and returns the existing iteration.
        """
        sim = self.get_simulation(sim_id)

        if so_id not in self.sos:
            raise ValueError(f"Simulation output {so_id} does not exist.")
        so = self.sos[so_id]

        output_so_ids = {out.uid for out in self.get_simulation_outputs(sim_id)}
        if so_id not in output_so_ids:
            raise ValueError(f"Output {so_id} does not belong to simulation {sim_id}.")

        for iteration in self.iterations.values():
            if iteration.simulation_id == sim_id and iteration.so_id == so_id:
                return iteration

        next_id = (
            max(
                (int(iteration.uid) for iteration in self.iterations.values()),
                default=0,
            )
            + 1
        )
        iteration = SimulationIteration(
            uid=IterationID(int=next_id),
            name=f"Iteration #{next_id}",
            simulation_id=sim_id,
            scg_id=sim.simulation_config_generator_id,
            sc_id=so.simulation_config_hash,
            so_id=so_id,
            variable_name=so.variable_name,
            variable_type=so.variable_type,
        )
        self.iterations[iteration.uid] = iteration
        self.notify_subscribers()
        return iteration

    def get_iteration(self, iteration_id: IterationID) -> SimulationIteration:
        """Get an iteration by ID, raising when it does not exist."""
        if iteration_id not in self.iterations:
            raise ValueError(f"Iteration {iteration_id} does not exist.")
        return self.iterations[iteration_id]

    def iterations_for_sim(
        self, sim_id: SimulationID
    ) -> tuple[SimulationIteration, ...]:
        """Return the iterations derived from a simulation's outputs."""
        return tuple(
            iteration
            for iteration in self.iterations.values()
            if iteration.simulation_id == sim_id
        )

    def remove_iteration(self, iteration_id: IterationID) -> None:
        """Remove an iteration."""
        self.iterations.pop(iteration_id, None)
        self.notify_subscribers()

    def get_iteration_table(
        self,
        iteration_id: IterationID,
        *,
        metric_ids: tuple[MetricID, ...] = (),
        filter_ids: tuple[FilterID, ...] = (),
        scalars_enabled: bool = True,
        remove_outliers: bool = True,
    ) -> BandTableResult:
        """Evaluate the per-band metric table for an iteration.

        The iteration's groups/concurrency resolve from its cached SO and SCG;
        the selected metrics and filters come from the caller (the view model's
        iteration metadata).
        """
        iteration = self.get_iteration(iteration_id)
        if iteration.so_id not in self.sos:
            raise ValueError(
                f"Iteration {iteration_id} references missing output {iteration.so_id}."
            )
        if iteration.scg_id not in self.scgs:
            raise ValueError(
                f"Iteration {iteration_id} references missing SCG {iteration.scg_id}."
            )
        return evaluate_band_table(
            data_repository=self.__data_repository,
            filter_repository=self.__filter_repository,
            metric_repository=self.__metric_repository,
            scg=self.scgs[iteration.scg_id],
            so=self.sos[iteration.so_id],
            metric_ids=metric_ids,
            filter_ids=filter_ids,
            scalars_enabled=scalars_enabled,
            remove_outliers=remove_outliers,
        )

    # Dependency handling
    def on_dependency_update(self, change_ids: ChangeIDs) -> None:
        # A removal (data source or filter) is delivered as a plain update, so
        # detect it here by diffing each simulation's references against the
        # entities that still exist. Affected simulations get a new SCG that
        # drops the dangling references; the old SCG/SC/SO stay in the cache.
        self._drop_dangling_references()

        # The SCG/SC/SO cache is retained indefinitely, even when the underlying
        # data or filter that produced it changes. Only reset simulations back
        # to PENDING so they may be re-run (a re-run recycles the cached SO).
        self._reset_simulations_to_pending()

    def on_dependency_remap(self, remaps: Remaps) -> None:
        # Build a new SCG (new content -> new uid) for every simulation whose
        # SCG references a remapped identity, register the new SCG and its SCs,
        # and repoint the simulation at it. Existing store entries are never
        # mutated in place: identical SCs keep the same content hash and are
        # reused, so their cached SOs are automatically recycled.
        filter_remap = get_remap(remaps, FilterID)
        ds_remap = get_remap(remaps, DataSourceID)
        if not filter_remap and not ds_remap:
            return

        for sim_id, sim in list(self.simulations.items()):
            scg = self._get_scg(sim)
            new_scg = self._remap_scg(scg, filter_remap, ds_remap)
            if new_scg.uid == scg.uid:
                continue
            for generated_sc in new_scg.get_configs():
                self.scs.setdefault(generated_sc.uid, generated_sc)
            self.scgs[new_scg.uid] = new_scg
            self.simulations[sim_id] = sim.with_updates(
                simulation_config_generator_id=new_scg.uid,
                status=SimulationStatus.PENDING,
                error_message=None,
                run_started_at=None,
                run_completed_at=None,
            )

    def _reset_simulations_to_pending(self) -> None:
        """Reset every simulation back to PENDING.

        Outputs are resolved through the chain, so the reset simply clears the
        lifecycle timestamps; cached SOs are retained indefinitely.
        """
        for sim_id, sim in list(self.simulations.items()):
            self.simulations[sim_id] = sim.with_updates(
                status=SimulationStatus.PENDING,
                error_message=None,
                run_started_at=None,
                run_completed_at=None,
            )

    def _drop_dangling_references(self) -> None:
        """Rebuild SCGs that reference removed data sources or filters.

        Removals arrive as plain dependency updates, so this pass reconciles
        every simulation's SCG against the entities that still exist. A removed
        filter ID is dropped from ``filter_ids``; a removed data source is
        dropped from the affected bad rate's ``data_source_ids`` and, because
        its column selection can no longer resolve, that bad rate's
        ``numerator_col``/``denominator_col`` are blanked. Because SCG identity
        is content-addressed, the rebuilt SCG gets a new uid and leaves the old
        SCG/SC/SO untouched in the cache, where they remain recyclable.
        """
        registered_filters = set(self.__filter_repository.filters)
        registered_sources = set(self.__data_repository.data_sources)

        for sim_id, sim in list(self.simulations.items()):
            scg = self._get_scg(sim)
            new_scg = scg.with_updates(
                dev_unit_bad_rate=self._drop_dangling_bad_rate(
                    scg.dev_unit_bad_rate,
                    registered_sources,
                ),
                dev_dollar_bad_rate=self._drop_dangling_bad_rate(
                    scg.dev_dollar_bad_rate,
                    registered_sources,
                ),
                test_unit_bad_rate=self._drop_dangling_bad_rate(
                    scg.test_unit_bad_rate,
                    registered_sources,
                ),
                test_dollar_bad_rate=self._drop_dangling_bad_rate(
                    scg.test_dollar_bad_rate,
                    registered_sources,
                ),
                filter_ids=tuple(
                    fid for fid in scg.filter_ids if fid in registered_filters
                ),
            )
            if new_scg.uid == scg.uid:
                continue
            for generated_sc in new_scg.get_configs():
                self.scs.setdefault(generated_sc.uid, generated_sc)
            self.scgs[new_scg.uid] = new_scg
            self.simulations[sim_id] = sim.with_updates(
                simulation_config_generator_id=new_scg.uid,
                status=SimulationStatus.PENDING,
                error_message=None,
                run_started_at=None,
                run_completed_at=None,
            )

    @classmethod
    def _drop_dangling_bad_rate(
        cls,
        bad_rate: BadRateConfig | None,
        registered_sources: set[DataSourceID],
    ) -> BadRateConfig | None:
        """Drop removed data sources from a bad rate, blanking its columns.

        If a removed source leaves the bad rate without any resolving source,
        the numerator/denominator columns are blanked (set to None) so the
        resulting SCG fails at run time only. Returns the original bad rate
        when nothing changed.
        """
        if bad_rate is None:
            return bad_rate
        kept_ids = tuple(
            ds_id for ds_id in bad_rate.data_source_ids if ds_id in registered_sources
        )
        if kept_ids == bad_rate.data_source_ids:
            return bad_rate
        updates: dict[str, t.Any] = {"data_source_ids": kept_ids}
        if not kept_ids:
            updates["numerator_col"] = None
            updates["denominator_col"] = None
        return bad_rate.with_updates(**updates)

    @staticmethod
    def _remap_bad_rate(
        bad_rate: BadRateConfig | None,
        ds_remap: dict[DataSourceID, DataSourceID] | None,
    ) -> BadRateConfig | None:
        """Rewrite a bad rate's data source references, preserving None."""
        if bad_rate is None or not ds_remap:
            return bad_rate
        new_ids = tuple(
            ds_remap.get(ds_id, ds_id) for ds_id in bad_rate.data_source_ids
        )
        if new_ids == bad_rate.data_source_ids:
            return bad_rate
        return bad_rate.with_updates(data_source_ids=new_ids)

    def _remap_scg(
        self,
        scg: SimulationConfigGenerator,
        filter_remap: dict[FilterID, FilterID] | None,
        ds_remap: dict[DataSourceID, DataSourceID] | None,
    ) -> SimulationConfigGenerator:
        """Return the SCG rewritten with remapped filter/data-source references."""
        new_filter_ids = (
            tuple(filter_remap.get(fid, fid) for fid in scg.filter_ids)
            if filter_remap
            else scg.filter_ids
        )
        return scg.with_updates(
            dev_unit_bad_rate=self._remap_bad_rate(scg.dev_unit_bad_rate, ds_remap),
            dev_dollar_bad_rate=self._remap_bad_rate(scg.dev_dollar_bad_rate, ds_remap),
            test_unit_bad_rate=self._remap_bad_rate(scg.test_unit_bad_rate, ds_remap),
            test_dollar_bad_rate=self._remap_bad_rate(
                scg.test_dollar_bad_rate, ds_remap
            ),
            filter_ids=new_filter_ids,
        )

    # Serialization
    def to_dict(self) -> SimulationRepositoryJSON:
        """Serialize SimulationRepository state to JSON."""
        return SimulationRepositoryJSON(
            simulations={
                sim.uid: self._simulation_to_json(sim)
                for sim in self.simulations.values()
            },
            generators={scg.uid: scg.to_dict() for scg in self.scgs.values()},
            outputs={
                sc_uid: so.to_dict()
                for sc_uid, so_id in self._so_cache.items()
                if (so := self.sos.get(so_id)) is not None
            },
            iterations={
                iteration.uid: iteration.to_dict()
                for iteration in self.iterations.values()
            },
        )

    def _simulation_to_json(self, sim: Simulation) -> SimulationJSON:
        return SimulationJSON(
            uid=sim.uid,
            simulation_config_generator_id=sim.simulation_config_generator_id,
            status=sim.status.value,
            error_message=sim.error_message,
            created_at=sim.created_at,
            run_started_at=sim.run_started_at,
            run_completed_at=sim.run_completed_at,
        )

    @classmethod
    def from_dict(
        cls,
        data: SimulationRepositoryJSON,
        data_repository: DataRepository,
        filter_repository: FilterRepository,
        metric_repository: MetricRepository,
        errors: t.Literal["ignore", "raise"] = "ignore",
    ) -> "SimulationRepository":
        """Reconstruct SimulationRepository from JSON."""
        repo = cls(data_repository, filter_repository, metric_repository)

        for scg_uid, scg_json in data.generators.items():
            scg = SimulationConfigGenerator.from_dict(scg_json)
            repo.scgs[scg_uid] = scg
            for sc in scg.get_configs():
                repo.scs[sc.uid] = sc

        for sim_json in data.simulations.values():
            sim = Simulation(
                uid=sim_json.uid,
                simulation_config_generator_id=sim_json.simulation_config_generator_id,
                status=SimulationStatus(sim_json.status),
                error_message=sim_json.error_message,
                created_at=sim_json.created_at,
                run_started_at=sim_json.run_started_at,
                run_completed_at=sim_json.run_completed_at,
            )
            repo.simulations[sim.uid] = sim

        for sc_uid, output_json in data.outputs.items():
            output = SimulationOutput.from_dict(output_json)
            repo.sos[output.uid] = output
            repo._so_cache[sc_uid] = output.uid

        for iter_uid, iteration_json in data.iterations.items():
            iteration = SimulationIteration.from_dict(iteration_json)
            repo.iterations[iter_uid] = iteration

        repo.notify_subscribers()
        return repo


__all__ = ["SimulationRepository"]
