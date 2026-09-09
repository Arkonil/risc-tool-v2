"""View model for the Simulation page."""

import dataclasses
import typing as t
from collections import OrderedDict

from risc_tool_v2.data.core.changes import ChangeTracker
from risc_tool_v2.data.core.enums import LossRateTypes, Signature, VariableType
from risc_tool_v2.data.core.id_remap import Remaps, get_remap
from risc_tool_v2.data.core.types import ChangeIDs
from risc_tool_v2.data.core.uid import (
    DataSourceID,
    FilterID,
    IterationID,
    MetricID,
    RiskSegmentID,
    SimulationID,
    SimulationOutputID,
)
from risc_tool_v2.data.data_source.repositories.data_repository import DataRepository
from risc_tool_v2.data.filter.models.filter import Filter
from risc_tool_v2.data.filter.repositories.filter_repository import FilterRepository
from risc_tool_v2.data.metric.models.metric import Metric
from risc_tool_v2.data.metric.repositories.metric_repository import MetricRepository
from risc_tool_v2.data.simulation.models.iteration import (
    BandGroups,
    SimulationIteration,
)
from risc_tool_v2.data.simulation.models.iteration_graph import IterationGraph
from risc_tool_v2.data.simulation.models.risk_segment import (
    RiskSegment,
    RiskSegmentConfig,
    get_default_risk_segments,
    is_valid_hex_color,
)
from risc_tool_v2.data.simulation.models.scalar import ScalarConfig
from risc_tool_v2.data.simulation.models.simulation import Simulation
from risc_tool_v2.data.simulation.models.simulation_config import (
    BadRateConfig,
    SimulationConfigGenerator,
    SimulationOutput,
)
from risc_tool_v2.data.simulation.repositories.simulation_repository import (
    SimulationRepository,
)
from risc_tool_v2.data.simulation.services.iterate import (
    BandTableResult,
    MetricGridResult,
    builtin_bad_rate_metric_options,
)

Mode = t.Literal["graph", "create", "view", "iteration", "iteration_create"]

# The four built-in bad rate metrics (dev/test x unit/dollar), keyed to their
# reserved MetricID sentinels. They are selectable per iteration and resolve
# from the iteration's SCG during evaluation, whether or not the simulation
# configured each rate.
BUILTIN_BAD_RATE_IDS: tuple[MetricID, ...] = (
    MetricID.DEV_UNT_BAD_RATE,
    MetricID.DEV_DLR_BAD_RATE,
    MetricID.TST_UNT_BAD_RATE,
    MetricID.TST_DLR_BAD_RATE,
)


def is_builtin_bad_rate_id(metric_id: MetricID) -> bool:
    """Return whether a metric id is one of the four built-in bad rates."""
    return metric_id in BUILTIN_BAD_RATE_IDS


@dataclasses.dataclass
class IterationMetadata:
    """Per-iteration view metadata (metrics, filters, flags).

    This is view state only and is deliberately not serialized with the
    simulation repository.
    """

    metric_ids: tuple[MetricID, ...] = ()
    filter_ids: tuple[FilterID, ...] = ()
    scalars_enabled: bool = True
    remove_outliers: bool = True
    split_view_enabled: bool = False
    show_prev_iter_details: bool = False


class SimulationViewModel(ChangeTracker):
    @property
    def signature(self) -> Signature:
        return Signature.SIMULATION_VIEW_MODEL

    def __init__(
        self,
        data_repository: DataRepository,
        simulation_repository: SimulationRepository,
        filter_repository: FilterRepository,
        metric_repository: MetricRepository,
    ) -> None:
        super().__init__(
            dependencies=[
                data_repository,
                simulation_repository,
                filter_repository,
                metric_repository,
            ]
        )
        self.__data_repository = data_repository
        self.__simulation_repository = simulation_repository
        self.__filter_repository = filter_repository
        self.__metric_repository = metric_repository

        # UI state
        self.__view_mode: Mode = "graph"
        self.__current_simulation_id: SimulationID | None = None
        self.__editing_sim_id: SimulationID | None = None
        self.__draft_scg: SimulationConfigGenerator | None = None
        self.__current_iteration_id: IterationID | None = None
        self.__iteration_create_base: IterationID | None = None
        self.__iteration_metadata: dict[IterationID, IterationMetadata] = {}
        self.__errors: list[str] = []

    def on_dependency_update(self, change_ids: ChangeIDs) -> None:
        # If the current simulation no longer exists, fall back to the graph view.
        if (
            self.__current_simulation_id is not None
            and self.__current_simulation_id
            not in self.__simulation_repository.simulations
        ):
            self.__current_simulation_id = None
            self.__view_mode = "graph"

        # Prune metadata for iterations that no longer exist (cascade delete),
        # and drop stale metric/filter ids from the surviving entries.
        self.__iteration_metadata = {
            iter_id: meta
            for iter_id, meta in self.__iteration_metadata.items()
            if iter_id in self.__simulation_repository.iterations
        }
        for iter_id, meta in self.__iteration_metadata.items():
            valid_metric_ids = tuple(
                metric_id
                for metric_id in meta.metric_ids
                if is_builtin_bad_rate_id(metric_id)
                or metric_id in self.__metric_repository.metrics
            )
            valid_filter_ids = tuple(
                filter_id
                for filter_id in meta.filter_ids
                if filter_id in self.__filter_repository.filters
            )
            if (
                valid_metric_ids != meta.metric_ids
                or valid_filter_ids != meta.filter_ids
            ):
                self.__iteration_metadata[iter_id] = dataclasses.replace(
                    meta,
                    metric_ids=valid_metric_ids,
                    filter_ids=valid_filter_ids,
                )

        if (
            self.__current_iteration_id is not None
            and self.__current_iteration_id
            not in self.__simulation_repository.iterations
        ):
            self.__current_iteration_id = None
            if self.__view_mode == "iteration":
                self.__view_mode = "graph"

        # Leave iteration-creation mode if its base iteration was deleted.
        if (
            self.__iteration_create_base is not None
            and self.__iteration_create_base
            not in self.__simulation_repository.iterations
        ):
            self.__iteration_create_base = None
            if self.__view_mode == "iteration_create":
                self.__view_mode = "graph"

    def on_dependency_remap(self, remaps: Remaps) -> None:
        filter_remap = get_remap(remaps, FilterID)
        if filter_remap:
            self.logger.debug("Filter remap applied to simulations: %s", filter_remap)

    @property
    def data_loaded(self) -> bool:
        return self.__data_repository.has_valid_sources

    @property
    def mode(self) -> Mode:
        return self.__view_mode

    @property
    def current_simulation_id(self) -> SimulationID | None:
        return self.__current_simulation_id

    @property
    def current_simulation(self) -> Simulation | None:
        if self.__current_simulation_id is None:
            return None
        return self.__simulation_repository.simulations.get(
            self.__current_simulation_id
        )

    def set_mode(
        self,
        mode: Mode,
        sim_id: SimulationID | None = None,
        iter_id: IterationID | None = None,
    ) -> None:
        self.__view_mode = mode
        self.__current_simulation_id = sim_id
        if iter_id is not None:
            self.__current_iteration_id = iter_id
        if mode != "create":
            self.__editing_sim_id = None
        if mode == "create":
            self.begin_draft()
        if mode != "iteration_create":
            self.__iteration_create_base = None

    @property
    def is_editing(self) -> bool:
        return self.__editing_sim_id is not None

    @property
    def editing_simulation_id(self) -> SimulationID | None:
        return self.__editing_sim_id

    def begin_edit_draft(self, sim_id: SimulationID) -> None:
        """Populate the draft from an existing Simulation's SCG for editing."""
        sim = self.__simulation_repository.get_simulation(sim_id)
        scg_id = sim.simulation_config_generator_id
        if scg_id not in self.__simulation_repository.scgs:
            raise ValueError(f"Simulation {sim_id} references missing SCG {scg_id}.")
        self.__editing_sim_id = sim_id
        self.__current_simulation_id = sim_id
        self.__draft_scg = self.__simulation_repository.scgs[scg_id]
        self.__view_mode = "create"

    def cancel_edit_draft(self) -> None:
        """Abandon an in-progress edit without saving."""
        self.__editing_sim_id = None
        self.__current_simulation_id = None
        self.__draft_scg = None
        self.__view_mode = "graph"

    @property
    def filters(self) -> dict[FilterID, Filter]:
        return self.__filter_repository.filters

    @property
    def metrics(self) -> OrderedDict[MetricID, Metric]:
        return self.__metric_repository.metrics

    @property
    def data_source_ids(self) -> list[DataSourceID]:
        return [ds_id for ds_id in self.__data_repository.data_sources]

    @property
    def draft_scg(self) -> SimulationConfigGenerator:
        return self._ensure_draft()

    def _ensure_draft(self) -> SimulationConfigGenerator:
        if self.__draft_scg is None:
            self.__draft_scg = self._empty_draft
        return self.__draft_scg

    def begin_draft(self) -> None:
        self._ensure_draft()

    def clear_draft(self) -> None:
        self.__draft_scg = None

    def clear_errors(self) -> None:
        self.__errors = []

    def add_error(self, message: str) -> None:
        self.__errors.append(message)

    @property
    def errors(self) -> tuple[str, ...]:
        return tuple(self.__errors)

    def update_draft_name(self, name: str) -> None:
        draft = self._ensure_draft()
        self.__draft_scg = draft.with_updates(name=name)

    def update_draft_variable_name(self, variable_name: str) -> None:
        draft = self._ensure_draft()
        self.__draft_scg = draft.with_updates(variable_name=variable_name)

    def update_draft_variable_type(self, variable_type: VariableType) -> None:
        draft = self._ensure_draft()
        self.__draft_scg = draft.with_updates(variable_type=variable_type)

    def update_draft_bad_rate_type(self, bad_rate_type: LossRateTypes) -> None:
        draft = self._ensure_draft()
        self.__draft_scg = draft.with_updates(bad_rate_type=bad_rate_type)

    def update_draft_filter_ids(self, filter_ids: tuple[FilterID, ...]) -> None:
        draft = self._ensure_draft()
        self.__draft_scg = draft.with_updates(filter_ids=filter_ids)

    def _update_draft_flag(self, field: str, value: bool) -> None:
        draft = self._ensure_draft()
        self.__draft_scg = draft.with_updates(**{field: value})

    def update_draft_auto_band(self, value: bool) -> None:
        self._update_draft_flag("auto_band", value)

    def update_draft_use_scalars(self, value: bool) -> None:
        self._update_draft_flag("use_scalars", value)

    def update_draft_remove_outliers(self, value: bool) -> None:
        self._update_draft_flag("remove_outliers", value)

    def update_draft_risk_segments(
        self, risk_segment_config: RiskSegmentConfig
    ) -> None:
        draft = self._ensure_draft()
        self.__draft_scg = draft.with_updates(risk_segment_config=risk_segment_config)

    def add_risk_segment(self) -> None:
        draft = self._ensure_draft()
        config = draft.risk_segment_config
        existing = {seg.name for seg in config.segments.values()}
        n = 1
        while f"Segment {n}" in existing:
            n += 1
        segment = RiskSegment(name=f"Segment {n}", upper_rate=float("inf"))
        new_segments: OrderedDict[RiskSegmentID, RiskSegment] = OrderedDict(
            config.segments
        )
        new_segments[segment.uid] = segment
        self.update_draft_risk_segments(RiskSegmentConfig(segments=new_segments))

    def delete_risk_segments(self, seg_ids: t.Sequence[RiskSegmentID]) -> None:
        draft = self._ensure_draft()
        config = draft.risk_segment_config
        new_segments = OrderedDict(
            (sid, seg)
            for sid, seg in config.segments.items()
            if sid not in set(seg_ids)
        )
        self.update_draft_risk_segments(RiskSegmentConfig(segments=new_segments))

    def apply_color_to_segments(
        self,
        color: str,
        field: t.Literal["bg_color", "font_color"],
        seg_ids: t.Sequence[RiskSegmentID],
    ) -> None:
        if not is_valid_hex_color(color):
            return
        normalized = color.upper()
        config = self._ensure_draft().risk_segment_config
        updated = config
        for seg_id in seg_ids:
            updated = updated.with_updates(seg_id, **{field: normalized})
        self.update_draft_risk_segments(updated)

    def reset_risk_segments(self) -> None:
        self.update_draft_risk_segments(
            RiskSegmentConfig(segments=get_default_risk_segments())
        )

    def update_draft_scalar_rate(
        self,
        loss_rate_type: LossRateTypes,
        field: t.Literal["current_rate", "lifetime_rate"],
        value: float | None,
    ) -> None:
        draft = self._ensure_draft()
        scalar_config = draft.scalar_config
        scalar = (
            scalar_config.ulr_scalar
            if loss_rate_type == LossRateTypes.ULR
            else scalar_config.dlr_scalar
        )
        updated_scalar = scalar.model_copy(update={field: value})
        if loss_rate_type == LossRateTypes.ULR:
            updated_scalar_config = scalar_config.model_copy(
                update={"ulr_scalar": updated_scalar}
            )
        else:
            updated_scalar_config = scalar_config.model_copy(
                update={"dlr_scalar": updated_scalar}
            )
        self.__draft_scg = draft.with_updates(scalar_config=updated_scalar_config)

    def _update_draft_bad_rate(
        self,
        *,
        which: t.Literal["dev", "test"],
        loss_rate_type: LossRateTypes,
        updates: dict[str, t.Any],
    ) -> None:
        draft = self._ensure_draft()
        field = {
            ("dev", LossRateTypes.ULR): "dev_unit_bad_rate",
            ("dev", LossRateTypes.DLR): "dev_dollar_bad_rate",
            ("test", LossRateTypes.ULR): "test_unit_bad_rate",
            ("test", LossRateTypes.DLR): "test_dollar_bad_rate",
        }[(which, loss_rate_type)]
        current = getattr(draft, field)
        if current is None:
            data_source_ids: tuple[DataSourceID, ...] = ()
            is_annualized = which == "dev"
            current = BadRateConfig(
                loss_rate_type=loss_rate_type,
                data_source_ids=data_source_ids,
                is_annualized=is_annualized,
            )
        updated = current.with_updates(**updates)
        self.__draft_scg = draft.with_updates(**{field: updated})

    def _bad_rate_for(
        self, draft: SimulationConfigGenerator, field: str
    ) -> BadRateConfig:
        current = getattr(draft, field)
        if current is not None:
            return current
        which, loss_rate_type = {
            "dev_unit_bad_rate": ("dev", LossRateTypes.ULR),
            "dev_dollar_bad_rate": ("dev", LossRateTypes.DLR),
            "test_unit_bad_rate": ("test", LossRateTypes.ULR),
            "test_dollar_bad_rate": ("test", LossRateTypes.DLR),
        }[field]
        return BadRateConfig(
            loss_rate_type=loss_rate_type,
            data_source_ids=(),
            is_annualized=which == "dev",
        )

    def update_draft_bad_rate_data_sources(
        self,
        which: t.Literal["dev", "test"],
        data_source_ids: tuple[DataSourceID, ...],
    ) -> None:
        draft = self._ensure_draft()
        fields = (
            ("dev_unit_bad_rate", "dev_dollar_bad_rate")
            if which == "dev"
            else ("test_unit_bad_rate", "test_dollar_bad_rate")
        )
        unit = self._bad_rate_for(draft, fields[0]).with_updates(
            data_source_ids=data_source_ids
        )
        dollar = self._bad_rate_for(draft, fields[1]).with_updates(
            data_source_ids=data_source_ids
        )
        self.__draft_scg = draft.with_updates(**{fields[0]: unit, fields[1]: dollar})

    def update_draft_bad_rate_column(
        self,
        *,
        which: t.Literal["dev", "test"],
        loss_rate_type: LossRateTypes,
        field: t.Literal["numerator_col", "denominator_col"],
        value: str | None,
    ) -> None:
        self._update_draft_bad_rate(
            which=which,
            loss_rate_type=loss_rate_type,
            updates={field: value},
        )

    def update_draft_mob(self, mob: int) -> None:
        draft = self._ensure_draft()
        unit = self._bad_rate_for(draft, "dev_unit_bad_rate").with_updates(
            current_rate_mob=mob
        )
        dollar = self._bad_rate_for(draft, "dev_dollar_bad_rate").with_updates(
            current_rate_mob=mob
        )
        self.__draft_scg = draft.with_updates(
            dev_unit_bad_rate=unit, dev_dollar_bad_rate=dollar
        )

    def update_draft_lifetime_mob(self, mob: int) -> None:
        draft = self._ensure_draft()
        self.__draft_scg = draft.with_updates(lifetime_rate_mob=mob)

    def confirm_draft(self) -> None:
        draft = self.__draft_scg
        if draft is None:
            raise RuntimeError("Cannot confirm simulation without a draft.")
        if self.__editing_sim_id is not None:
            sim = self.__simulation_repository.update_simulation_scg(
                self.__editing_sim_id, draft
            )
        else:
            sim = self.__simulation_repository.create_simulation(draft)
        editing = self.__editing_sim_id is not None
        self.__editing_sim_id = None
        self.__draft_scg = None
        self.__current_simulation_id = sim.uid
        self.__view_mode = "view" if editing else "graph"

    @property
    def _empty_draft(self) -> SimulationConfigGenerator:
        return SimulationConfigGenerator(
            name="New Simulation",
            risk_segment_config=RiskSegmentConfig(),
            dev_unit_bad_rate=None,
            dev_dollar_bad_rate=None,
            test_unit_bad_rate=None,
            test_dollar_bad_rate=None,
            bad_rate_type=LossRateTypes.ULR,
            scalar_config=ScalarConfig(),
            variable_name="",
            variable_type=VariableType.NUMERICAL,
            auto_band=True,
            use_scalars=True,
        )

    @property
    def simulations(self) -> dict[SimulationID, Simulation]:
        return self.__simulation_repository.simulations

    def scg_for(self, sim: Simulation) -> SimulationConfigGenerator:
        return self.__simulation_repository.scgs[sim.simulation_config_generator_id]

    def run_simulation(self, sim_id: SimulationID) -> Simulation:
        return self.__simulation_repository.run_simulation(sim_id)

    def get_simulation_outputs(
        self, sim_id: SimulationID
    ) -> tuple[SimulationOutput, ...]:
        return self.__simulation_repository.get_simulation_outputs(sim_id)

    def remove_simulation(self, sim_id: SimulationID) -> None:
        self.__simulation_repository.remove_simulation(sim_id)
        if self.__current_simulation_id == sim_id:
            self.__current_simulation_id = None
            self.__view_mode = "graph"

    # Iterations (single-variable analyses derived from simulation outputs)
    def open_iteration_from_output(
        self, sim_id: SimulationID, so_id: SimulationOutputID
    ) -> SimulationIteration:
        """Open (or create, idempotently) the iteration for an output."""
        iteration = self.__simulation_repository.create_iteration(sim_id, so_id)
        self._ensure_iteration_metadata(iteration)
        self.__current_iteration_id = iteration.uid
        self.__view_mode = "iteration"
        return iteration

    def open_iteration(self, iteration_id: IterationID) -> SimulationIteration:
        """Open an existing iteration by ID, seeding metadata on first access."""
        iteration = self.get_iteration(iteration_id)
        self._ensure_iteration_metadata(iteration)
        self.__current_iteration_id = iteration.uid
        self.__view_mode = "iteration"
        return iteration

    def get_iteration(self, iteration_id: IterationID) -> SimulationIteration:
        return self.__simulation_repository.get_iteration(iteration_id)

    def iterations_for_sim(
        self, sim_id: SimulationID
    ) -> tuple[SimulationIteration, ...]:
        return self.__simulation_repository.iterations_for_sim(sim_id)

    def remove_iteration(self, iteration_id: IterationID) -> None:
        """Delete an iteration; returns to the graph when deleting the open one."""
        self.__simulation_repository.remove_iteration(iteration_id)
        self.__iteration_metadata.pop(iteration_id, None)
        if self.__current_iteration_id == iteration_id:
            self.__current_iteration_id = None
            if self.__view_mode == "iteration":
                self.__view_mode = "graph"

    def update_iteration_metadata(
        self,
        iteration_id: IterationID,
        *,
        metric_ids: tuple[MetricID, ...] | None = None,
        filter_ids: tuple[FilterID, ...] | None = None,
        scalars_enabled: bool | None = None,
        remove_outliers: bool | None = None,
        split_view_enabled: bool | None = None,
        show_prev_iter_details: bool | None = None,
    ) -> None:
        """Update an iteration's view metadata, keeping only existing ids."""
        meta = self.iteration_metadata(iteration_id)
        if metric_ids is not None:
            valid = tuple(
                m
                for m in metric_ids
                if is_builtin_bad_rate_id(m) or m in self.metrics
            )
            meta.metric_ids = valid
        if filter_ids is not None:
            valid = tuple(
                f for f in filter_ids if f in self.__filter_repository.filters
            )
            meta.filter_ids = valid
        if scalars_enabled is not None:
            meta.scalars_enabled = scalars_enabled
        if remove_outliers is not None:
            meta.remove_outliers = remove_outliers
        if split_view_enabled is not None:
            meta.split_view_enabled = split_view_enabled
        if show_prev_iter_details is not None:
            meta.show_prev_iter_details = show_prev_iter_details

    def iteration_metadata(self, iteration_id: IterationID) -> IterationMetadata:
        return self.__iteration_metadata[iteration_id]

    def metric_options(
        self, iteration_id: IterationID
    ) -> OrderedDict[MetricID, Metric]:
        """Return every selectable metric for an iteration, built-ins first.

        The four built-in bad rates (dev/test x unit/dollar) are derived from
        the iteration's SCG, followed by the registered user metrics.
        """
        options: OrderedDict[MetricID, Metric] = OrderedDict()
        iteration = self.get_iteration(iteration_id)
        scg = self.__simulation_repository.scgs.get(iteration.scg_id)
        if scg is not None:
            for metric_id, (_name, metric) in builtin_bad_rate_metric_options(
                scg
            ).items():
                options[metric_id] = metric
        for metric_id, metric in self.__metric_repository.metrics.items():
            options[metric_id] = metric
        return options

    def get_iteration_table(
        self,
        iteration_id: IterationID,
        *,
        show_total_row: bool = False,
        default: bool = False,
    ) -> BandTableResult:
        """Evaluate the iteration's band table with its current view metadata."""
        meta = self.iteration_metadata(iteration_id)
        return self.__simulation_repository.get_iteration_table(
            iteration_id,
            metric_ids=meta.metric_ids,
            filter_ids=meta.filter_ids,
            scalars_enabled=meta.scalars_enabled,
            remove_outliers=meta.remove_outliers,
            show_total_row=show_total_row,
            default=default,
        )

    def get_iteration_grid(
        self,
        iteration_id: IterationID,
        *,
        show_total_row: bool = False,
        show_total_column: bool = False,
        default: bool = False,
    ) -> MetricGridResult:
        """Evaluate a double-variable iteration's grid with view metadata."""
        meta = self.iteration_metadata(iteration_id)
        return self.__simulation_repository.get_iteration_grid(
            iteration_id,
            metric_ids=meta.metric_ids,
            filter_ids=meta.filter_ids,
            scalars_enabled=meta.scalars_enabled,
            remove_outliers=meta.remove_outliers,
            show_total_row=show_total_row,
            show_total_column=show_total_column,
            default=default,
        )

    @property
    def iteration_graph(self) -> IterationGraph:
        """Return the iteration parent-child graph from the repository."""
        return self.__simulation_repository.iteration_graph

    def iteration_chain(self, iteration_id: IterationID) -> tuple[SimulationIteration, ...]:
        """Return the iteration's lineage root-first, including itself.

        The chain is derived from the repository graph (single-variable roots
        have an empty ancestor list, so the tuple is just ``(iteration,)``).
        """
        graph = self.__simulation_repository.iteration_graph
        chain = graph.get_ancestors(iteration_id) + [iteration_id]
        return tuple(self.get_iteration(iter_id) for iter_id in chain)

    def double_var_candidate_columns(
        self, iteration_id: IterationID
    ) -> list[tuple[str, VariableType]]:
        """Return ``(column, type)`` pairs usable for a double-variable iteration.

        Candidates are the columns shared by the iteration's dev bad rate data
        sources (falling back to all common columns), minus the iteration's own
        banded variable.
        """
        iteration = self.get_iteration(iteration_id)
        scg = self.__simulation_repository.scgs.get(iteration.scg_id)
        source_ids: list[DataSourceID] = []
        if scg is not None:
            bad_rate = (
                scg.dev_unit_bad_rate
                if scg.bad_rate_type == LossRateTypes.ULR
                else scg.dev_dollar_bad_rate
            )
            if bad_rate is not None:
                source_ids = list(bad_rate.data_source_ids)
        columns = (
            self.__data_repository.common_columns(source_ids)
            if source_ids
            else self.__data_repository.common_columns()
        )
        return [
            (name, var_type)
            for name, var_type in sorted(columns)
            if name != iteration.variable_name
        ]

    def create_editable_clone(self, iteration_id: IterationID) -> SimulationIteration:
        """Clone an iteration into an editable variant and open it."""
        iteration = self.__simulation_repository.create_editable_clone(iteration_id)
        self._ensure_iteration_metadata(iteration)
        self.__current_iteration_id = iteration.uid
        self.__view_mode = "iteration"
        return iteration

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
        """Create a double-variable iteration over another iteration and open it."""
        iteration = self.__simulation_repository.create_double_var_iteration(
            iteration_id,
            new_variable_name=new_variable_name,
            new_variable_type=new_variable_type,
            upgrade_limit=upgrade_limit,
            downgrade_limit=downgrade_limit,
            auto_rank_ordering=auto_rank_ordering,
        )
        self._ensure_iteration_metadata(iteration)
        self.__current_iteration_id = iteration.uid
        self.__view_mode = "iteration"
        return iteration

    def rename_iteration(self, iteration_id: IterationID, name: str) -> SimulationIteration:
        """Rename an iteration and return the updated object."""
        return self.__simulation_repository.rename_iteration(iteration_id, name)

    def begin_iteration_create(self, base_iteration_id: IterationID) -> None:
        """Enter the dedicated double-variable iteration creation page."""
        self.get_iteration(base_iteration_id)  # raises if missing
        self.__iteration_create_base = base_iteration_id
        self.__current_iteration_id = base_iteration_id
        self.__view_mode = "iteration_create"

    def cancel_iteration_create(self) -> None:
        """Abandon the creation page and return to the graph."""
        self.__iteration_create_base = None
        self.__view_mode = "graph"

    @property
    def iteration_create_base_id(self) -> IterationID | None:
        return self.__iteration_create_base

    @property
    def iteration_create_base(self) -> SimulationIteration | None:
        if self.__iteration_create_base is None:
            return None
        return self.__simulation_repository.iterations.get(
            self.__iteration_create_base
        )

    def select_groups(
        self, iteration_id: IterationID, *, mask: dict[RiskSegmentID, bool]
    ) -> SimulationIteration:
        """Update a double-variable iteration's active-group mask."""
        return self.__simulation_repository.select_groups(iteration_id, mask=mask)

    def add_new_group(self, iteration_id: IterationID) -> SimulationIteration:
        """Append a group to an editable iteration's working bands."""
        return self.__simulation_repository.add_new_group(iteration_id)

    def set_controls(
        self, iteration_id: IterationID, groups: BandGroups
    ) -> SimulationIteration:
        return self.__simulation_repository.set_controls(iteration_id, groups)

    def set_risk_segment_grid(
        self,
        iteration_id: IterationID,
        grid: dict[RiskSegmentID, dict[RiskSegmentID, RiskSegmentID]],
    ) -> SimulationIteration:
        return self.__simulation_repository.set_risk_segment_grid(iteration_id, grid)

    @property
    def current_iteration(self) -> SimulationIteration | None:
        if self.__current_iteration_id is None:
            return None
        return self.__simulation_repository.iterations.get(self.__current_iteration_id)

    @property
    def current_iteration_id(self) -> IterationID | None:
        return self.__current_iteration_id

    def _ensure_iteration_metadata(self, iteration: SimulationIteration) -> None:
        """Seed an iteration's metadata from its parent simulation on first use."""
        if iteration.uid in self.__iteration_metadata:
            return
        try:
            sim = self.__simulation_repository.get_simulation(iteration.simulation_id)
            scg = self.__simulation_repository.scgs[sim.simulation_config_generator_id]
            seed = IterationMetadata(
                metric_ids=BUILTIN_BAD_RATE_IDS,
                filter_ids=tuple(scg.filter_ids),
                scalars_enabled=scg.use_scalars,
                remove_outliers=scg.remove_outliers,
            )
        except (ValueError, KeyError):
            seed = IterationMetadata(metric_ids=BUILTIN_BAD_RATE_IDS)
        self.__iteration_metadata[iteration.uid] = seed

    @property
    def common_columns(self) -> list[str]:
        return [c[0] for c in self.__data_repository.common_columns()]

    def selected_common_columns(
        self, data_source_ids: t.Sequence[DataSourceID]
    ) -> list[str]:
        if not data_source_ids:
            return []
        return [
            c[0] for c in self.__data_repository.common_columns(list(data_source_ids))
        ]

    @property
    def data_source_labels(self) -> dict[DataSourceID, str]:
        return {ds.uid: ds.label for ds in self.__data_repository.data_sources.values()}


__all__ = ["SimulationViewModel"]
