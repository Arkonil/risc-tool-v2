"""Session management for the RISC Tool application.

This module provides the Session class which holds the application state
including repositories and view models.
"""

from risc_tool.data.repositories.data import DataRepository
from risc_tool.data.repositories.filter import FilterRepository
from risc_tool.data.repositories.metric import MetricRepository
from risc_tool.ui.data_explorer.data_explorer_vm import DataExplorerViewModel
from risc_tool.ui.data_importer.data_importer_vm import DataImporterViewModel
from risc_tool.ui.filters.filters_vm import FilterViewModel
from risc_tool.ui.metrics.metrics_vm import MetricViewModel
from risc_tool.utils.logging import get_logger

logger = get_logger(__name__)


class Session:
    """Container for the application's session state.

    Holds references to the data repository and view models, allowing
    them to persist across Streamlit reruns via session state.

    Attributes:
        data_repository: Repository for managing data sources.
        filter_repository: Repository for managing filters.
        data_importer_view_model: View model for the data importer UI.
        data_explorer_view_model: View model for the data explorer UI.
        filter_editor_view_model: View model for the filters UI.
    """

    def __init__(self):
        """Initialize a new session with default repositories and view models."""
        self.reset()
        logger.info(
            "Session initialized with DataRepository, FilterRepository, and 3 view models"
        )

    def reset(self):
        """Reset the session to its initial state.

        Creates a new DataRepository, FilterRepository, and respective view models.
        """
        logger.debug("Resetting session: recreating all repositories and view models")

        # Repositories
        self.data_repository = DataRepository()
        self.filter_repository = FilterRepository(self.data_repository)
        self.metric_repository = MetricRepository(self.data_repository)

        # View Models
        self.data_importer_view_model = DataImporterViewModel(self.data_repository)
        self.data_explorer_view_model = DataExplorerViewModel(
            self.data_repository,
            self.filter_repository,
        )
        self.filter_editor_view_model = FilterViewModel(
            self.data_repository,
            self.filter_repository,
        )
        self.metric_editor_view_model = MetricViewModel(
            self.data_repository,
            self.metric_repository,
        )
