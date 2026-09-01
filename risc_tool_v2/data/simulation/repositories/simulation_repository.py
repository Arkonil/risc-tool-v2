"""Repository for managing simulations and their configs/outputs with change notification."""

import typing as t
from collections import OrderedDict
from datetime import UTC, datetime

from risc_tool_v2.data.core.changes import BaseRepository
from risc_tool_v2.data.core.enums import LossRateTypes, Signature, VariableType
from risc_tool_v2.data.core.id_remap import Remaps, get_remap
from risc_tool_v2.data.core.types import ChangeIDs
from risc_tool_v2.data.core.uid import (
    FilterID,
    GroupID,
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
    BadRateConfigJSON,
    CategoricalGroupJSON,
    LossRateScalarJSON,
    NumericalGroupJSON,
    RiskSegmentConfigJSON,
    RiskSegmentJSON,
    ScalarConfigJSON,
    SimulationConfigGeneratorJSON,
    SimulationConfigJSON,
    SimulationJSON,
    SimulationOutputJSON,
    SimulationRepositoryJSON,
)
from risc_tool_v2.data.simulation.models.groups import (
    CategoricalGroup,
    NumericalGroup,
)
from risc_tool_v2.data.simulation.models.risk_segment import RiskSegmentConfig
from risc_tool_v2.data.simulation.models.scalar import LossRateScalar, ScalarConfig
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


class SimulationRepository(BaseRepository):
    """Manages Simulation objects (each owning an SCG) with caching by SC content hash."""

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

        self.__data_repository = data_repository
        self.__filter_repository = filter_repository
        self.__metric_repository = metric_repository

    # Simulation lifecycle
    def create_simulation(self, scg: SimulationConfigGenerator) -> Simulation:
        """Create a new Simulation wrapping the given SimulationConfigGenerator."""
        simulation = Simulation(
            simulation_config_generator=scg,
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

    def get_simulations(self) -> dict[SimulationID, Simulation]:
        """Return all simulations keyed by ID."""
        return self.simulations

    def remove_simulation(self, sim_id: SimulationID) -> None:
        """Remove a Simulation and its associated SCG/SC/SO entries."""
        if sim_id not in self.simulations:
            return
        sim = self.simulations[sim_id]
        scg = sim.simulation_config_generator
        for sc in scg.get_configs():
            self.scs.pop(sc.uid, None)
            self._so_cache.pop(sc.uid, None)
        self.scgs.pop(scg.uid, None)
        if sim.output is not None:
            self.sos.pop(sim.output.uid, None)
        del self.simulations[sim_id]
        self.notify_subscribers()

    # SCG Management
    def create_scg(self, name: str, sc: SimulationConfig) -> SimulationConfigGenerator:
        """Create a new SimulationConfigGenerator with a single SC."""
        scg = SimulationConfigGenerator(
            name=name,
            risk_segment_config=sc.risk_segment_config,
            dev_unit_bad_rate=sc.dev_unit_bad_rate,
            dev_dollar_bad_rate=sc.dev_dollar_bad_rate,
            test_unit_bad_rate=sc.test_unit_bad_rate,
            test_dollar_bad_rate=sc.test_dollar_bad_rate,
            bad_rate_type=sc.bad_rate_type,
            scalar_config=sc.scalar_config,
            filter_ids=sc.filter_ids,
            remove_outliers=sc.remove_outliers,
            variable_name=sc.variable_name,
            variable_type=sc.variable_type,
            auto_band=sc.auto_band,
            use_scalars=sc.use_scalars,
        )
        for generated_sc in scg.get_configs():
            self.scs[generated_sc.uid] = generated_sc
        self.scgs[scg.uid] = scg
        self.notify_subscribers()
        return scg

    def get_scg(self, scg_id: SimulationConfigGeneratorID) -> SimulationConfigGenerator:
        """Get a SimulationConfigGenerator by ID."""
        if scg_id not in self.scgs:
            raise ValueError(f"SimulationConfigGenerator {scg_id} does not exist.")
        return self.scgs[scg_id]

    # SC Management
    def register_sc(self, sc: SimulationConfig) -> SimulationConfig:
        """Register SC, return existing if same content hash exists."""
        if sc.uid in self.scs:
            return self.scs[sc.uid]
        self.scs[sc.uid] = sc
        self.notify_subscribers()
        return sc

    def get_sc(self, sc_id: SimulationConfigID) -> SimulationConfig:
        """Get a SimulationConfig by ID."""
        if sc_id not in self.scs:
            raise ValueError(f"SimulationConfig {sc_id} does not exist.")
        return self.scs[sc_id]

    def remove_sc(self, sc_id: SimulationConfigID) -> None:
        """Remove a SimulationConfig."""
        if sc_id not in self.scs:
            return
        del self.scs[sc_id]
        self._so_cache.pop(sc_id, None)
        self.notify_subscribers()

    def _replace_sc(self, old_id: SimulationConfigID, new_sc: SimulationConfig) -> None:
        """Replace a SimulationConfig in place."""
        new_id = new_sc.uid
        if new_id == old_id:
            self.scs[old_id] = new_sc
            return

        items = [
            (new_id, new_sc) if sc_id == old_id else (sc_id, sc)
            for sc_id, sc in self.scs.items()
        ]
        self.scs.clear()
        self.scs.update(items)

        if old_id in self._so_cache and self._so_cache[old_id] in self.sos:
            so_id = self._so_cache.pop(old_id)
            del self.sos[so_id]

    # SO Generation (Core Simulation Execution)
    def _run_sc(self, sc: SimulationConfig) -> SimulationOutput:
        """Generate SO from SC using auto-banding; cache by SC content hash."""
        # 1. Check cache by SC content hash
        if sc.uid in self._so_cache:
            cached_so_id = self._so_cache[sc.uid]
            if cached_so_id in self.sos:
                return self.sos[cached_so_id]

        # 2. Get filtered LazyFrame
        data_filter = self.__filter_repository.get_combined_expression(
            list(sc.filter_ids), remove_outliers=sc.remove_outliers
        )
        lf = self.__data_repository.get_lazyframe()
        lf = lf.filter(data_filter)

        # 3. Get selected dev bad rate based on bad_rate_type
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

        # 4. Build Metric from BadRateConfig
        metric = bad_rate_config.to_metric(
            uid=MetricID.TEMPORARY,
            name=f"sim_{sc.uid}_bad_rate",
        )
        # Validate against available columns
        available_cols = [c[0] for c in self.__data_repository.common_columns()]
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
                OrderedDict[GroupID, NumericalGroup | CategoricalGroup], groups
            ),
            created_at=datetime.now(UTC),
        )

        # 7. Cache and store
        self._so_cache[sc.uid] = so.uid
        self.sos[so.uid] = so
        return so

    def run_simulation(self, sim_id: SimulationID) -> Simulation:
        """Run a Simulation (producing an output) and return the updated object."""
        sim = self.get_simulation(sim_id)
        scg = sim.simulation_config_generator
        sc = scg.get_configs()[0]

        running = sim.with_updates(
            status=SimulationStatus.RUNNING,
            run_started_at=datetime.now(UTC),
            error_message=None,
        )
        self.simulations[sim_id] = running

        try:
            so = self._run_sc(sc)
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
            output=so,
            run_completed_at=datetime.now(UTC),
        )
        self.simulations[sim_id] = completed
        self.notify_subscribers()
        return completed

    def get_so(self, so_id: SimulationOutputID) -> SimulationOutput:
        """Get a SimulationOutput by ID."""
        if so_id not in self.sos:
            raise ValueError(f"SimulationOutput {so_id} does not exist.")
        return self.sos[so_id]

    def get_so_for_sc(self, sc_id: SimulationConfigID) -> SimulationOutput | None:
        """Get the cached SO for a given SC."""
        if sc_id in self._so_cache:
            so_id = self._so_cache[sc_id]
            return self.sos.get(so_id)
        return None

    # Dependency handling
    def on_dependency_update(self, change_ids: ChangeIDs) -> None:
        # Invalidate outputs/cache if data/filters change
        self._so_cache.clear()
        for so_id in list(self.sos.keys()):
            del self.sos[so_id]
        # Reset any completed/failed/pending simulations so they may be re-run.
        for sim_id, sim in list(self.simulations.items()):
            if sim.output is not None:
                self.simulations[sim_id] = sim.with_updates(
                    output=None,
                    status=SimulationStatus.PENDING,
                    error_message=None,
                    run_started_at=None,
                    run_completed_at=None,
                )
        self.notify_subscribers()

    def on_dependency_remap(self, remaps: Remaps) -> None:
        # Remap filter_ids in SCs if FilterIDs change
        filter_remap = get_remap(remaps, FilterID)
        if not filter_remap:
            return
        for sc_id, sc in list(self.scs.items()):
            new_filter_ids = tuple(filter_remap.get(fid, fid) for fid in sc.filter_ids)
            if new_filter_ids != sc.filter_ids:
                new_sc = sc.with_updates(filter_ids=new_filter_ids)
                self._replace_sc(sc_id, new_sc)
        # Also remap SCGs
        for sim_id, sim in list(self.simulations.items()):
            scg = sim.simulation_config_generator
            new_filter_ids = tuple(filter_remap.get(fid, fid) for fid in scg.filter_ids)
            if new_filter_ids == scg.filter_ids:
                continue
            old_sc = scg.get_configs()[0]
            new_scg = scg.with_updates(filter_ids=new_filter_ids)
            new_sc = new_scg.get_configs()[0]

            self.scs.pop(old_sc.uid, None)
            self._so_cache.pop(old_sc.uid, None)
            self.scs[new_sc.uid] = new_sc

            self.scgs[new_scg.uid] = new_scg
            self.scgs.pop(scg.uid, None)
            self.simulations[sim_id] = sim.with_updates(
                simulation_config_generator=new_scg,
                output=None,
                status=SimulationStatus.PENDING,
                error_message=None,
                run_started_at=None,
                run_completed_at=None,
            )

    # Serialization
    def to_dict(self) -> SimulationRepositoryJSON:
        """Serialize SimulationRepository state to JSON."""
        return SimulationRepositoryJSON(
            simulations={
                sim.uid: self._simulation_to_json(sim)
                for sim in self.simulations.values()
            },
        )

    def _simulation_to_json(self, sim: Simulation) -> SimulationJSON:
        return SimulationJSON(
            uid=sim.uid,
            simulation_config_generator=self._scg_to_json(
                sim.simulation_config_generator
            ),
            status=sim.status.value,
            output=self._so_to_json(sim.output) if sim.output is not None else None,
            error_message=sim.error_message,
            created_at=sim.created_at,
            run_started_at=sim.run_started_at,
            run_completed_at=sim.run_completed_at,
        )

    def _scg_to_json(
        self, scg: SimulationConfigGenerator
    ) -> SimulationConfigGeneratorJSON:
        def bad_rate_to_json(br: BadRateConfig | None):
            return self._bad_rate_config_to_json(br) if br is not None else None

        return SimulationConfigGeneratorJSON(
            uid=scg.uid,
            name=scg.name,
            risk_segment_config=self._risk_segment_config_to_json(
                scg.risk_segment_config
            ),
            dev_unit_bad_rate=bad_rate_to_json(scg.dev_unit_bad_rate),
            dev_dollar_bad_rate=bad_rate_to_json(scg.dev_dollar_bad_rate),
            test_unit_bad_rate=bad_rate_to_json(scg.test_unit_bad_rate),
            test_dollar_bad_rate=bad_rate_to_json(scg.test_dollar_bad_rate),
            bad_rate_type=scg.bad_rate_type,
            scalar_config=self._scalar_config_to_json(scg.scalar_config),
            filter_ids=list(scg.filter_ids),
            remove_outliers=scg.remove_outliers,
            variable_name=scg.variable_name,
            variable_type=scg.variable_type,
            auto_band=scg.auto_band,
            use_scalars=scg.use_scalars,
        )

    def _sc_to_json(self, sc: SimulationConfig) -> SimulationConfigJSON:
        def bad_rate_to_json(br: BadRateConfig | None):
            return self._bad_rate_config_to_json(br) if br is not None else None

        return SimulationConfigJSON(
            uid=sc.uid,
            risk_segment_config=self._risk_segment_config_to_json(
                sc.risk_segment_config
            ),
            dev_unit_bad_rate=bad_rate_to_json(sc.dev_unit_bad_rate),
            dev_dollar_bad_rate=bad_rate_to_json(sc.dev_dollar_bad_rate),
            test_unit_bad_rate=bad_rate_to_json(sc.test_unit_bad_rate),
            test_dollar_bad_rate=bad_rate_to_json(sc.test_dollar_bad_rate),
            bad_rate_type=sc.bad_rate_type,
            scalar_config=self._scalar_config_to_json(sc.scalar_config),
            filter_ids=list(sc.filter_ids),
            remove_outliers=sc.remove_outliers,
            variable_name=sc.variable_name,
            variable_type=sc.variable_type,
            auto_band=sc.auto_band,
            use_scalars=sc.use_scalars,
        )

    def _risk_segment_config_to_json(
        self, config: RiskSegmentConfig
    ) -> RiskSegmentConfigJSON:
        return RiskSegmentConfigJSON(
            segments=OrderedDict(
                (
                    seg_id,
                    RiskSegmentJSON(
                        name=seg.name,
                        upper_rate=seg.upper_rate,
                        bg_color=seg.bg_color,
                        font_color=seg.font_color,
                        maf_dlr=seg.maf_dlr,
                        maf_ulr=seg.maf_ulr,
                        selected=seg.selected,
                    ),
                )
                for seg_id, seg in config.segments.items()
            )
        )

    def _bad_rate_config_to_json(self, config: BadRateConfig) -> BadRateConfigJSON:
        return BadRateConfigJSON(
            loss_rate_type=config.loss_rate_type,
            numerator_col=config.numerator_col,
            denominator_col=config.denominator_col,
            current_rate_mob=config.current_rate_mob,
            data_source_ids=list(config.data_source_ids),
            is_annualized=config.is_annualized,
        )

    def _scalar_config_to_json(self, config: ScalarConfig) -> ScalarConfigJSON:
        return ScalarConfigJSON(
            ulr_scalar=LossRateScalarJSON(
                loss_rate_type=config.ulr_scalar.loss_rate_type,
                current_rate=config.ulr_scalar.current_rate,
                lifetime_rate=config.ulr_scalar.lifetime_rate,
            ),
            dlr_scalar=LossRateScalarJSON(
                loss_rate_type=config.dlr_scalar.loss_rate_type,
                current_rate=config.dlr_scalar.current_rate,
                lifetime_rate=config.dlr_scalar.lifetime_rate,
            ),
        )

    def _so_to_json(self, so: SimulationOutput) -> SimulationOutputJSON:
        return SimulationOutputJSON(
            uid=so.uid,
            simulation_config_id=so.simulation_config_id,
            simulation_config_hash=so.simulation_config_hash,
            variable_name=so.variable_name,
            variable_type=so.variable_type,
            groups=OrderedDict(
                (
                    gid,
                    NumericalGroupJSON(
                        type="numerical",
                        lower_bound=g.lower_bound,
                        upper_bound=g.upper_bound,
                    )
                    if isinstance(g, NumericalGroup)
                    else CategoricalGroupJSON(
                        type="categorical",
                        categories=sorted(g.categories),
                    ),
                )
                for gid, g in so.groups.items()
            ),
            created_at=so.created_at,
            is_valid=so.is_valid,
            validation_warnings=list(so.validation_warnings),
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

        for sim_json in data.simulations.values():
            scg = cls._scg_from_json(sim_json.simulation_config_generator)
            repo.scgs[scg.uid] = scg
            for sc in scg.get_configs():
                repo.scs[sc.uid] = sc

            output = (
                cls._so_from_json(sim_json.output)
                if sim_json.output is not None
                else None
            )
            if output is not None:
                repo.sos[output.uid] = output
                repo._so_cache[output.simulation_config_hash] = output.uid

            sim = Simulation(
                uid=sim_json.uid,
                simulation_config_generator=scg,
                status=SimulationStatus(sim_json.status),
                output=output,
                error_message=sim_json.error_message,
                created_at=sim_json.created_at,
                run_started_at=sim_json.run_started_at,
                run_completed_at=sim_json.run_completed_at,
            )
            repo.simulations[sim.uid] = sim

        repo.notify_subscribers()
        return repo

    @classmethod
    def _scg_from_json(
        cls, data: SimulationConfigGeneratorJSON
    ) -> SimulationConfigGenerator:
        def json_to_bad_rate(br_json: BadRateConfigJSON | None) -> BadRateConfig | None:
            return (
                cls._bad_rate_config_from_json(br_json) if br_json is not None else None
            )

        return SimulationConfigGenerator(
            uid=data.uid,
            name=data.name,
            risk_segment_config=cls._risk_segment_config_from_json(
                data.risk_segment_config
            ),
            dev_unit_bad_rate=json_to_bad_rate(data.dev_unit_bad_rate),
            dev_dollar_bad_rate=json_to_bad_rate(data.dev_dollar_bad_rate),
            test_unit_bad_rate=json_to_bad_rate(data.test_unit_bad_rate),
            test_dollar_bad_rate=json_to_bad_rate(data.test_dollar_bad_rate),
            bad_rate_type=data.bad_rate_type,
            scalar_config=cls._scalar_config_from_json(data.scalar_config),
            filter_ids=tuple(data.filter_ids),
            remove_outliers=data.remove_outliers,
            variable_name=data.variable_name,
            variable_type=data.variable_type,
            auto_band=data.auto_band,
            use_scalars=data.use_scalars,
        )

    @classmethod
    def _sc_from_json(cls, data: SimulationConfigJSON) -> SimulationConfig:
        def json_to_bad_rate(br_json: BadRateConfigJSON | None) -> BadRateConfig | None:
            return (
                cls._bad_rate_config_from_json(br_json) if br_json is not None else None
            )

        risk_segment_config = cls._risk_segment_config_from_json(
            data.risk_segment_config
        )
        scalar_config = cls._scalar_config_from_json(data.scalar_config)

        return SimulationConfig(
            uid=data.uid,
            risk_segment_config=risk_segment_config,
            dev_unit_bad_rate=json_to_bad_rate(data.dev_unit_bad_rate),
            dev_dollar_bad_rate=json_to_bad_rate(data.dev_dollar_bad_rate),
            test_unit_bad_rate=json_to_bad_rate(data.test_unit_bad_rate),
            test_dollar_bad_rate=json_to_bad_rate(data.test_dollar_bad_rate),
            bad_rate_type=data.bad_rate_type,
            scalar_config=scalar_config,
            filter_ids=tuple(data.filter_ids),
            remove_outliers=data.remove_outliers,
            variable_name=data.variable_name,
            variable_type=data.variable_type,
            auto_band=data.auto_band,
            use_scalars=data.use_scalars,
        )

    @classmethod
    def _risk_segment_config_from_json(
        cls, data: RiskSegmentConfigJSON
    ) -> RiskSegmentConfig:
        from risc_tool_v2.data.simulation.models.risk_segment import RiskSegment

        new_segments: OrderedDict[RiskSegmentID, RiskSegment] = OrderedDict()
        for seg_id, seg_json in data.segments.items():
            new_segments[seg_id] = RiskSegment(
                uid=seg_id,
                name=seg_json.name,
                upper_rate=seg_json.upper_rate,
                bg_color=seg_json.bg_color,
                font_color=seg_json.font_color,
                maf_dlr=seg_json.maf_dlr,
                maf_ulr=seg_json.maf_ulr,
                selected=seg_json.selected,
            )
        return RiskSegmentConfig(segments=new_segments)

    @classmethod
    def _bad_rate_config_from_json(cls, data: BadRateConfigJSON) -> BadRateConfig:
        return BadRateConfig(
            loss_rate_type=data.loss_rate_type,
            numerator_col=data.numerator_col,
            denominator_col=data.denominator_col,
            current_rate_mob=data.current_rate_mob,
            data_source_ids=tuple(data.data_source_ids),
            is_annualized=data.is_annualized,
        )

    @classmethod
    def _scalar_config_from_json(cls, data: ScalarConfigJSON) -> ScalarConfig:
        return ScalarConfig(
            ulr_scalar=LossRateScalar(
                loss_rate_type=data.ulr_scalar.loss_rate_type,
                current_rate=data.ulr_scalar.current_rate,
                lifetime_rate=data.ulr_scalar.lifetime_rate,
            ),
            dlr_scalar=LossRateScalar(
                loss_rate_type=data.dlr_scalar.loss_rate_type,
                current_rate=data.dlr_scalar.current_rate,
                lifetime_rate=data.dlr_scalar.lifetime_rate,
            ),
        )

    @classmethod
    def _so_from_json(cls, data: SimulationOutputJSON) -> SimulationOutput:
        groups: OrderedDict[GroupID, NumericalGroup | CategoricalGroup] = OrderedDict()
        for gid, group_json in data.groups.items():
            if group_json.type == "numerical":
                groups[gid] = NumericalGroup(
                    lower_bound=group_json.lower_bound,
                    upper_bound=group_json.upper_bound,
                )
            else:
                groups[gid] = CategoricalGroup(
                    categories=frozenset(group_json.categories)
                )

        return SimulationOutput(
            uid=data.uid,
            simulation_config_id=data.simulation_config_id,
            simulation_config_hash=data.simulation_config_hash,
            variable_name=data.variable_name,
            variable_type=data.variable_type,
            groups=groups,
            created_at=data.created_at,
            is_valid=data.is_valid,
            validation_warnings=tuple(data.validation_warnings),
        )


__all__ = ["SimulationRepository"]
