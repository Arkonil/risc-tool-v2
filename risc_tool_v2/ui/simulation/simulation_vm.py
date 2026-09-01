"""View model for the Simulation page."""

import typing as t
from collections import OrderedDict

from risc_tool_v2.data.core.changes import ChangeTracker
from risc_tool_v2.data.core.enums import LossRateTypes, Signature, VariableType
from risc_tool_v2.data.core.id_remap import Remaps, get_remap
from risc_tool_v2.data.core.types import ChangeIDs
from risc_tool_v2.data.core.uid import DataSourceID, FilterID, MetricID, SimulationID
from risc_tool_v2.data.data_source.repositories.data_repository import DataRepository
from risc_tool_v2.data.filter.models.filter import Filter
from risc_tool_v2.data.filter.repositories.filter_repository import FilterRepository
from risc_tool_v2.data.metric.models.metric import Metric
from risc_tool_v2.data.metric.repositories.metric_repository import MetricRepository
from risc_tool_v2.data.simulation.models.risk_segment import RiskSegmentConfig
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

    def update_draft_settings(
        self,
        *,
        name: str,
        variable_name: str,
        variable_type: VariableType,
        bad_rate_type: LossRateTypes,
        filter_ids: tuple[FilterID, ...],
        auto_band: bool,
        use_scalars: bool,
        remove_outliers: bool,
    ) -> None:
        draft = self._ensure_draft()
        self.__draft_scg = draft.with_updates(
            name=name,
            variable_name=variable_name,
            variable_type=variable_type,
            bad_rate_type=bad_rate_type,
            filter_ids=filter_ids,
            auto_band=auto_band,
            use_scalars=use_scalars,
            remove_outliers=remove_outliers,
        )

    def update_draft_risk_segments(
        self, risk_segment_config: RiskSegmentConfig
    ) -> None:
        draft = self._ensure_draft()
        self.__draft_scg = draft.with_updates(risk_segment_config=risk_segment_config)

    def update_draft_scalars(
        self,
        scalar_config: ScalarConfig,
        risk_segment_config: RiskSegmentConfig,
    ) -> None:
        draft = self._ensure_draft()
        self.__draft_scg = draft.with_updates(
            scalar_config=scalar_config,
            risk_segment_config=risk_segment_config,
        )

    def update_draft_bad_rates(
        self,
        dev_unit_bad_rate: BadRateConfig,
        dev_dollar_bad_rate: BadRateConfig,
        test_unit_bad_rate: BadRateConfig,
        test_dollar_bad_rate: BadRateConfig,
    ) -> None:
        draft = self._ensure_draft()
        self.__draft_scg = draft.with_updates(
            dev_unit_bad_rate=dev_unit_bad_rate,
            dev_dollar_bad_rate=dev_dollar_bad_rate,
            test_unit_bad_rate=test_unit_bad_rate,
            test_dollar_bad_rate=test_dollar_bad_rate,
        )

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
