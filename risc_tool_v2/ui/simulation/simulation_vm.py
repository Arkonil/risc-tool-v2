"""View model for the Simulation page."""

import typing as t
from collections import OrderedDict

from risc_tool_v2.data.core.changes import ChangeTracker
from risc_tool_v2.data.core.enums import LossRateTypes, Signature, VariableType
from risc_tool_v2.data.core.id_remap import Remaps, get_remap
from risc_tool_v2.data.core.types import ChangeIDs
from risc_tool_v2.data.core.uid import (
    DataSourceID,
    FilterID,
    MetricID,
    RiskSegmentID,
    SimulationID,
)
from risc_tool_v2.data.data_source.repositories.data_repository import DataRepository
from risc_tool_v2.data.filter.models.filter import Filter
from risc_tool_v2.data.filter.repositories.filter_repository import FilterRepository
from risc_tool_v2.data.metric.models.metric import Metric
from risc_tool_v2.data.metric.repositories.metric_repository import MetricRepository
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
)
from risc_tool_v2.data.simulation.repositories.simulation_repository import (
    SimulationRepository,
)


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
        self.__view_mode: t.Literal["graph", "create", "view"] = "graph"
        self.__current_simulation_id: SimulationID | None = None
        self.__draft_scg: SimulationConfigGenerator | None = None
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

    def on_dependency_remap(self, remaps: Remaps) -> None:
        filter_remap = get_remap(remaps, FilterID)
        if filter_remap:
            self.logger.debug("Filter remap applied to simulations: %s", filter_remap)

    @property
    def data_loaded(self) -> bool:
        return self.__data_repository.has_valid_sources

    @property
    def mode(self) -> t.Literal["graph", "create", "view"]:
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
        mode: t.Literal["graph", "create", "view"],
        sim_id: SimulationID | None = None,
    ) -> None:
        self.__view_mode = mode
        self.__current_simulation_id = sim_id
        if mode == "create":
            self.begin_draft()

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
        sim = self.__simulation_repository.create_simulation(draft)
        self.__draft_scg = None
        self.__current_simulation_id = sim.uid
        self.__view_mode = "graph"

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

    def run_simulation(self, sim_id: SimulationID) -> Simulation:
        return self.__simulation_repository.run_simulation(sim_id)

    def remove_simulation(self, sim_id: SimulationID) -> None:
        self.__simulation_repository.remove_simulation(sim_id)
        if self.__current_simulation_id == sim_id:
            self.__current_simulation_id = None
            self.__view_mode = "graph"

    @property
    def common_columns(self) -> list[str]:
        return [c[0] for c in self.__data_repository.common_columns()]

    @property
    def data_source_labels(self) -> dict[DataSourceID, str]:
        return {ds.uid: ds.label for ds in self.__data_repository.data_sources.values()}


__all__ = ["SimulationViewModel"]
