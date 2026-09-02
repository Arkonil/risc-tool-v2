"""Session management for the risc-tool-v2 application."""

from risc_tool_v2.data.core.utils.logging import get_logger
from risc_tool_v2.data.data_source.repositories.data_repository import DataRepository
from risc_tool_v2.data.filter.repositories.filter_repository import FilterRepository
from risc_tool_v2.data.metric.repositories.metric_repository import MetricRepository
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

logger = get_logger(__name__)


class Session:
    """Container for risc-tool-v2 session state."""

    def __init__(self):
        self.reset()
        logger.info("risc-tool-v2 Session initialized")

    def reset(self):
        # Core Repositories
        self.data_repository = DataRepository()
        self.filter_repository = FilterRepository(self.data_repository)
        self.metric_repository = MetricRepository(self.data_repository)
        self.simulation_repository = SimulationRepository(
            self.data_repository,
            self.filter_repository,
            self.metric_repository,
        )

        # View Models
        self.data_importer_view_model = DataImporterViewModel(self.data_repository)
        self.data_explorer_view_model = DataExplorerViewModel(
            self.data_repository, self.filter_repository
        )
        self.filter_editor_view_model = FilterViewModel(
            self.data_repository, self.filter_repository
        )
        self.metric_editor_view_model = MetricViewModel(
            self.data_repository, self.metric_repository
        )
        self.simulation_view_model = SimulationViewModel(
            self.data_repository,
            self.simulation_repository,
            self.filter_repository,
            self.metric_repository,
        )

    # Aliases for convenience
    @property
    def filter_view_model(self) -> FilterViewModel:
        return self.filter_editor_view_model

    @property
    def metric_view_model(self) -> MetricViewModel:
        return self.metric_editor_view_model


__all__ = ["Session"]
