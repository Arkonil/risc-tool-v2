"""Repository for managing simulations and their configs/outputs with change notification."""

import typing as t
from collections import OrderedDict
from datetime import UTC, datetime

import polars as pl

from risc_tool_v2.data.core.changes import BaseRepository
from risc_tool_v2.data.core.enums import (
    IterationType,
    LossRateTypes,
    Signature,
    VariableType,
)
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
from risc_tool_v2.data.simulation.models.iteration_graph import IterationGraph
from risc_tool_v2.data.simulation.models.risk_segment import RiskSegment
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
    MetricGridResult,
    double_var_assignment_expr,
    evaluate_band_table,
    evaluate_metric_grid,
    segment_assignment_expr,
)
from risc_tool_v2.data.simulation.services.iteration_banding import (
    plan_double_var_bands,
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
        # Lineage graph linking iterations (parents to double-var children and
        # editable clones to their family root).
        self.iteration_graph = IterationGraph()

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
            removed_ids = {
                iter_id
                for iter_id, iteration in self.iterations.items()
                if iteration.simulation_id == sim_id
            }
            self.iterations = {
                iter_id: iteration
                for iter_id, iteration in self.iterations.items()
                if iteration.simulation_id != sim_id
            }
            for iter_id in removed_ids:
                self.iteration_graph.remove_iteration(iter_id)
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

    # Iterations (analyses derived from simulation outputs)
    def _next_iteration_id(self) -> IterationID:
        """Return the next sequential iteration id assigned in creation order."""
        next_id = (
            max(
                (int(iteration.uid) for iteration in self.iterations.values()),
                default=0,
            )
            + 1
        )
        return IterationID(int=next_id)

    def create_iteration(
        self, sim_id: SimulationID, so_id: SimulationOutputID
    ) -> SimulationIteration:
        """Create an iteration over one of a simulation's outputs.

        The iteration stores only references (``simulation_id``, ``scg_id``,
        ``sc_id``, ``so_id``); banding and configuration resolve from the
        cached SCG/SC/SO. The output's bands are snapshotted into
        ``default_groups`` and ``groups`` so the iteration owns a read-only
        copy that survives later changes to the output. Iteration identity is a
        sequential integer assigned in creation order. Creating an iteration for
        an output that already has one is idempotent and returns the existing
        iteration.
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

        next_id = self._next_iteration_id()
        iteration = SimulationIteration(
            uid=next_id,
            name=f"Iteration #{int(next_id)}",
            simulation_id=sim_id,
            scg_id=sim.simulation_config_generator_id,
            sc_id=so.simulation_config_hash,
            so_id=so_id,
            variable_name=so.variable_name,
            variable_type=so.variable_type,
            iter_type=IterationType.SINGLE,
            is_editable=False,
            family_root_id=next_id,
            source_iteration_id=IterationID.UNSET,
            previous_iteration_id=IterationID.UNSET,
            default_groups=so.groups,
            groups=so.groups,
        )
        self.iterations[iteration.uid] = iteration
        self.iteration_graph.connections.setdefault(iteration.uid, [])
        self.notify_subscribers()
        return iteration

    def create_editable_clone(
        self, iteration_id: IterationID
    ) -> SimulationIteration:
        """Clone an iteration into a new editable variant.

        Clones always branch from their family's fixed root: the clone's
        ``default_groups``/``default_risk_segment_grid`` stay pinned to the
        founding iteration while ``groups``/``risk_segment_grid`` hold a
        modifiable copy of the source's working bands.
        """
        source = self.get_iteration(iteration_id)
        family_root_id = (
            source.family_root_id
            if source.family_root_id != IterationID.UNSET
            else source.uid
        )
        family_root = self.get_iteration(family_root_id)

        next_id = self._next_iteration_id()
        clone = SimulationIteration(
            uid=next_id,
            name=f"Iteration #{int(next_id)} (editable)",
            simulation_id=source.simulation_id,
            scg_id=source.scg_id,
            sc_id=source.sc_id,
            so_id=source.so_id,
            variable_name=source.variable_name,
            variable_type=source.variable_type,
            iter_type=source.iter_type,
            is_editable=True,
            family_root_id=family_root.uid,
            source_iteration_id=source.uid,
            previous_iteration_id=family_root.uid,
            default_groups=family_root.effective_groups(default=True),
            groups=source.effective_groups(),
            groups_mask=dict(source.groups_mask),
            risk_segment_grid=source.effective_risk_segment_grid(),
            default_risk_segment_grid=family_root.effective_risk_segment_grid(
                default=True
            ),
        )
        self.iterations[clone.uid] = clone
        self.iteration_graph.add_child(family_root.uid, clone.uid)
        self.notify_subscribers()
        return clone

    def create_double_var_iteration(
        self,
        iteration_id: IterationID,
        *,
        new_variable_name: str,
        new_variable_type: VariableType,
        upgrade_limit: int = 2,
        downgrade_limit: int = 2,
        auto_rank_ordering: bool = True,
    ) -> SimulationIteration:
        """Layer a new banded variable over an iteration's bands.

        Bands are planned with :func:`plan_double_var_bands`, which auto-bands
        the new variable inside a limited window around each parent band and
        maps every ``(child group, parent band)`` cell to a target band by the
        cell's dev bad rate. The resulting groups and grid are snapshotted into
        both the working and default fields of a new fixed iteration.
        """
        parent = self.get_iteration(iteration_id)

        if parent.so_id not in self.sos:
            raise ValueError(
                f"Iteration {iteration_id} references missing output {parent.so_id}."
            )
        if parent.sc_id not in self.scs:
            raise ValueError(
                f"Iteration {iteration_id} references missing config {parent.sc_id}."
            )
        scg = self.scgs.get(parent.scg_id)
        if scg is None:
            raise ValueError(
                f"Iteration {iteration_id} references missing SCG {parent.scg_id}."
            )
        sc = self.scs[parent.sc_id]

        bad_rate_config = self._dev_bad_rate_for_sc(sc)

        source_ids = list(bad_rate_config.data_source_ids)
        common_columns = {
            (name, var_type)
            for name, var_type in self.__data_repository.common_columns(source_ids)
        }
        if (new_variable_name, new_variable_type) not in common_columns:
            raise ValueError(
                f"Variable '{new_variable_name}' is not available in the dev "
                "data sources or has a different type."
            )

        metric = bad_rate_config.to_metric(
            uid=MetricID.TEMPORARY,
            name=f"double_var_{parent.sc_id}_bad_rate",
        )
        available_cols = [c[0] for c in common_columns]
        metric.validate_query(available_columns=available_cols)

        base_lf = self.__data_repository.get_lazyframe(data_source_ids=source_ids)
        data_filter = self.__filter_repository.get_combined_expression(
            list(sc.filter_ids), remove_outliers=sc.remove_outliers
        )
        base_lf = base_lf.filter(data_filter)

        chain_exprs, parent_col = self._chain_exprs_for(iteration_id)
        for expr in chain_exprs:
            base_lf = base_lf.with_columns(expr)

        unfiltered_value_range = None
        if new_variable_type == VariableType.NUMERICAL:
            unfiltered_value_range = self._unfiltered_variable_range(
                data_source_ids=source_ids, variable_name=new_variable_name
            )

        ordered_parent_segments = list(sc.risk_segment_config.segments.keys())

        groups, grid, _warnings = plan_double_var_bands(
            base_lf=base_lf,
            variable_name=new_variable_name,
            variable_type=new_variable_type,
            parent_col=parent_col,
            metric=metric,
            loss_rate_scalar=sc.scalar_config.get_scalar(
                bad_rate_config.loss_rate_type
            ),
            numerator=t.cast(str, bad_rate_config.numerator_col),
            denominator=bad_rate_config.denominator_col,
            mob=bad_rate_config.current_rate_mob,
            risk_segment_config=sc.risk_segment_config,
            use_scalar=sc.use_scalars,
            upgrade_limit=upgrade_limit,
            downgrade_limit=downgrade_limit,
            auto_rank_ordering=auto_rank_ordering,
            ordered_parent_segments=ordered_parent_segments,
            unfiltered_value_range=unfiltered_value_range,
        )

        if not groups:
            raise ValueError(
                "Auto-banding produced no groups for the double-variable iteration."
            )

        next_id = self._next_iteration_id()
        iteration = SimulationIteration(
            uid=next_id,
            name=f"Iteration #{int(next_id)}",
            simulation_id=parent.simulation_id,
            scg_id=parent.scg_id,
            sc_id=parent.sc_id,
            so_id=parent.so_id,
            variable_name=new_variable_name,
            variable_type=new_variable_type,
            iter_type=IterationType.DOUBLE,
            is_editable=False,
            family_root_id=next_id,
            source_iteration_id=IterationID.UNSET,
            previous_iteration_id=parent.uid,
            default_groups=groups,
            groups=groups,
            groups_mask={gid: True for gid in groups},
            risk_segment_grid=grid,
            default_risk_segment_grid=grid,
        )
        self.iterations[iteration.uid] = iteration
        self.iteration_graph.add_child(parent.uid, iteration.uid)
        self.notify_subscribers()
        return iteration

    @classmethod
    def _dev_bad_rate_for_sc(cls, sc: SimulationConfig) -> BadRateConfig:
        """Return the SimulationConfig's selected dev bad rate."""
        if sc.bad_rate_type == LossRateTypes.ULR:
            bad_rate_config = sc.dev_unit_bad_rate
        else:
            bad_rate_config = sc.dev_dollar_bad_rate
        if bad_rate_config is None:
            raise ValueError(
                f"No dev bad rate configured for {sc.bad_rate_type.value}"
            )
        if bad_rate_config.numerator_col is None:
            raise ValueError(
                f"No bad count column configured for {sc.bad_rate_type.value}"
            )
        return bad_rate_config

    def _unfiltered_variable_range(
        self, *, data_source_ids: list[DataSourceID], variable_name: str
    ) -> tuple[float, float] | None:
        """Return the (min, max) of a numeric variable across unfiltered data."""
        lf = self.__data_repository.get_lazyframe(data_source_ids=data_source_ids)
        try:
            values = (
                lf.select(pl.col(variable_name).drop_nulls())
                .collect()
                .get_column(variable_name)
                .cast(pl.Float64)
            )
        except pl.exceptions.PolarsError:
            return None
        if values.is_empty():
            return None
        minimum = values.min()
        maximum = values.max()
        if minimum is None or maximum is None:
            return None
        minimum = t.cast(float, minimum)
        maximum = t.cast(float, maximum)
        if not (minimum < maximum):
            return None
        return (minimum, maximum)

    def _chain_exprs_for(self, iteration_id: IterationID) -> tuple[list[pl.Expr], str]:
        """Compose the dependent expressions that resolve an iteration's band column.

        Walks the graph from the iteration's root ancestor down to the
        iteration itself, producing one assignment expression per level. Each
        expression is aliased ``__RS_NODE_{level}__`` and must be applied
        sequentially (later expressions reference earlier aliases).

        Returns:
            A tuple of (expressions, final alias) where the final alias names
            the column holding ``iteration_id``'s own band assignment.
        """
        chain = self.iteration_graph.get_ancestors(iteration_id) + [iteration_id]
        exprs: list[pl.Expr] = []
        prev_col: str | None = None

        for level, iter_id in enumerate(chain):
            iteration = self.get_iteration(iter_id)
            alias = f"__RS_NODE_{level}__"
            groups = iteration.effective_groups()

            if iteration.is_double_var:
                if prev_col is None:
                    raise ValueError(
                        f"Double-variable iteration {iter_id} has no parent band "
                        "column."
                    )
                grid = iteration.effective_risk_segment_grid()
                if not groups or not grid:
                    raise ValueError(
                        f"Double-variable iteration {iter_id} has no bands or grid."
                    )
                expr = double_var_assignment_expr(
                    groups=groups,
                    variable_name=iteration.variable_name,
                    prev_col=prev_col,
                    grid=grid,
                )
            else:
                if not groups:
                    raise ValueError(f"Iteration {iter_id} has no bands.")
                expr = segment_assignment_expr(groups, iteration.variable_name)

            exprs.append(expr.alias(alias))
            prev_col = alias

        if prev_col is None:
            raise ValueError(f"Iteration {iteration_id} produced no band column.")
        return exprs, prev_col

    def _iteration_target_segment_ids(
        self, iteration: SimulationIteration
    ) -> set[RiskSegmentID]:
        """Return the iteration's working band ids expressed as root segments.

        Single-variable iterations band rows directly to root risk segments.
        Double-variable iterations band rows through their working grid, so the
        relevant parent columns are the grid-mapped target segments.
        """
        if iteration.is_double_var:
            return {
                target
                for grid in iteration.effective_risk_segment_grid().values()
                for target in grid.values()
            }
        return set(iteration.effective_groups())

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

    def rename_iteration(self, iteration_id: IterationID, name: str) -> SimulationIteration:
        """Rename an iteration and return the updated object."""
        iteration = self.get_iteration(iteration_id)
        iteration.name = name
        self.notify_subscribers()
        return iteration

    def remove_iteration(self, iteration_id: IterationID) -> None:
        """Remove an iteration and all of its graph descendants."""
        if iteration_id not in self.iterations:
            return
        ids_to_delete = self.iteration_graph.get_descendants(iteration_id) + [
            iteration_id
        ]
        for iter_id in ids_to_delete:
            self.iterations.pop(iter_id, None)
            self.iteration_graph.remove_iteration(iter_id)
        self.notify_subscribers()

    def get_iteration_table(
        self,
        iteration_id: IterationID,
        *,
        metric_ids: tuple[MetricID, ...] = (),
        filter_ids: tuple[FilterID, ...] = (),
        scalars_enabled: bool = True,
        remove_outliers: bool = True,
        show_total_row: bool = False,
        default: bool = False,
    ) -> BandTableResult:
        """Evaluate the per-band metric table for an iteration.

        Single-variable iterations (fixed or editable) resolve their bands from
        the iteration's working groups. Double-variable iterations have no
        single band table; use :meth:`get_iteration_grid` instead.

        Args:
            iteration_id: The iteration to evaluate.
            metric_ids: User metrics to include alongside the dev bad rate.
            filter_ids: Filters applied to every column.
            scalars_enabled: Whether to scale the dev bad rate by scalar factor.
            remove_outliers: Whether to drop outlier rows.
            show_total_row: Whether to compute a total aggregate over all rows.
            default: Whether to evaluate against the pinned default bands
                instead of the working (editable) ones.

        Returns:
            The per-band :class:`BandTableResult`.

        Raises:
            ValueError: If the iteration is a double-variable iteration or its
                output/SCG are missing.
        """
        iteration = self.get_iteration(iteration_id)
        if iteration.is_double_var:
            raise ValueError(
                f"Iteration {iteration_id} is a double-variable iteration and has "
                "no single band table; use get_iteration_grid instead."
            )
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
            groups=iteration.effective_groups(default=default),
            variable_name=iteration.variable_name,
            show_total_row=show_total_row,
        )

    def get_iteration_grid(
        self,
        iteration_id: IterationID,
        *,
        metric_ids: tuple[MetricID, ...] = (),
        filter_ids: tuple[FilterID, ...] = (),
        scalars_enabled: bool = True,
        remove_outliers: bool = True,
        show_total_row: bool = False,
        show_total_column: bool = False,
        default: bool = False,
    ) -> MetricGridResult:
        """Evaluate the double-variable metric grid for an iteration.

        Rows are the iteration's own (child) bands; columns are the graph
        parent's bands. Each cell is aggregated over ``(child group, parent
        band)`` pairs visible through the iteration chain.

        Args:
            iteration_id: The double-variable iteration to evaluate.
            metric_ids: User metrics to include alongside the dev bad rate.
            filter_ids: Filters applied to every column.
            scalars_enabled: Whether to scale the dev bad rate by scalar factor.
            remove_outliers: Whether to drop outlier rows.
            show_total_row: Whether to compute a total row (per parent band)
                and the corner total when ``show_total_column`` is also set.
            show_total_column: Whether to compute a total column (per row group).
            default: Whether to evaluate against the pinned default row groups
                and risk segment grid instead of the working (editable) ones.

        Returns:
            The per-cell :class:`MetricGridResult`.

        Raises:
            ValueError: If the iteration is not a double-variable iteration.
        """
        iteration = self.get_iteration(iteration_id)
        if not iteration.is_double_var:
            raise ValueError(
                f"Iteration {iteration_id} is not a double-variable iteration."
            )
        if iteration.so_id not in self.sos:
            raise ValueError(
                f"Iteration {iteration_id} references missing output {iteration.so_id}."
            )
        if iteration.scg_id not in self.scgs:
            raise ValueError(
                f"Iteration {iteration_id} references missing SCG {iteration.scg_id}."
            )

        parent = self.get_iteration(iteration.previous_iteration_id)
        row_groups = iteration.effective_groups(default=default)

        scg = self.scgs[iteration.scg_id]
        parent_segments: OrderedDict[RiskSegmentID, RiskSegment] = OrderedDict()
        for seg_id, segment in scg.risk_segment_config.segments.items():
            if seg_id in self._iteration_target_segment_ids(parent):
                parent_segments[seg_id] = segment

        chain_exprs, parent_col = self._chain_exprs_for(parent.uid)

        return evaluate_metric_grid(
            data_repository=self.__data_repository,
            filter_repository=self.__filter_repository,
            metric_repository=self.__metric_repository,
            scg=scg,
            variable_name=iteration.variable_name,
            row_groups=row_groups,
            parent_segments=parent_segments,
            parent_chain_exprs=chain_exprs,
            parent_col=parent_col,
            metric_ids=metric_ids,
            filter_ids=filter_ids,
            scalars_enabled=scalars_enabled,
            remove_outliers=remove_outliers,
            grid=iteration.effective_risk_segment_grid(default=default),
            show_total_row=show_total_row,
            show_total_column=show_total_column,
        )
    def select_groups(
        self, iteration_id: IterationID, *, mask: dict[RiskSegmentID, bool]
    ) -> SimulationIteration:
        """Update which default groups are active for a double-variable iteration.

        Args:
            iteration_id: The double-variable iteration to edit.
            mask: Per-default-group visibility (True = shown).

        Returns:
            The updated iteration.
        """
        iteration = self.get_iteration(iteration_id)
        if not iteration.is_double_var:
            raise ValueError(
                f"Iteration {iteration_id} is not a double-variable iteration."
            )
        for gid in iteration.default_groups:
            if gid not in mask:
                iteration.groups_mask[gid] = True
        for gid, is_visible in mask.items():
            if gid in iteration.default_groups:
                iteration.groups_mask[gid] = bool(is_visible)
        self.notify_subscribers()
        return iteration

    def add_new_group(
        self, iteration_id: IterationID
    ) -> SimulationIteration:
        """Append a blank group to an editable iteration's working bands.

        The new group inherits the last group's grid row (identity for an
        empty bands-only source) so the grid stays valid.

        Returns:
            The updated iteration.
        """
        iteration = self.get_iteration(iteration_id)
        if not iteration.is_editable:
            raise ValueError(
                f"Iteration {iteration_id} is not editable; cannot add groups."
            )

        if iteration.groups:
            last_gid, last_group = next(reversed(iteration.groups.items()))
        else:
            last_gid, last_group = None, None

        new_gid = RiskSegmentID(int=max((int(g) for g in iteration.groups), default=-1) + 1)
        if last_group is None:
            new_group: NumericalGroup | CategoricalGroup = NumericalGroup(
                lower_bound=float("-inf"), upper_bound=float("inf")
            )
        elif isinstance(last_group, NumericalGroup):
            new_group = NumericalGroup(
                lower_bound=last_group.upper_bound,
                upper_bound=last_group.upper_bound,
            )
        else:
            new_group = CategoricalGroup(categories=frozenset())

        iteration.groups[new_gid] = new_group
        if last_gid is not None:
            last_row = iteration.risk_segment_grid.get(last_gid, {})
            iteration.risk_segment_grid[new_gid] = dict(last_row)
        self.notify_subscribers()
        return iteration

    def set_controls(
        self,
        iteration_id: IterationID,
        groups: OrderedDict[RiskSegmentID, NumericalGroup | CategoricalGroup],
    ) -> SimulationIteration:
        """Replace an editable iteration's working bands wholesale.

        Returns:
            The updated iteration.
        """
        iteration = self.get_iteration(iteration_id)
        if not iteration.is_editable:
            raise ValueError(
                f"Iteration {iteration_id} is not editable; cannot set groups."
            )
        iteration.groups = groups
        if iteration.is_double_var:
            iteration.groups_mask = {gid: True for gid in groups}
        self.notify_subscribers()
        return iteration

    def set_risk_segment_grid(
        self,
        iteration_id: IterationID,
        grid: dict[RiskSegmentID, dict[RiskSegmentID, RiskSegmentID]],
    ) -> SimulationIteration:
        """Replace an editable double-variable iteration's working grid.

        Returns:
            The updated iteration.
        """
        iteration = self.get_iteration(iteration_id)
        if not iteration.is_editable:
            raise ValueError(
                f"Iteration {iteration_id} is not editable; cannot edit the grid."
            )
        if not iteration.is_double_var:
            raise ValueError(
                f"Iteration {iteration_id} is not a double-variable iteration."
            )
        iteration.risk_segment_grid = grid
        self.notify_subscribers()
        return iteration

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
            iteration_graph=self.iteration_graph.to_dict(),
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

        repo.iteration_graph = IterationGraph.from_dict(data.iteration_graph)

        repo.notify_subscribers()
        return repo


__all__ = ["SimulationRepository"]
