"""Session management for the RISC Tool application.

This module provides the Session class which holds the application state
including repositories and view models.
"""

from risc_tool.data.models.json_models import SessionJSON
from risc_tool.data.repositories.data import DataRepository
from risc_tool.data.repositories.filter import FilterRepository
from risc_tool.data.repositories.iterations import IterationsRepository
from risc_tool.data.repositories.metric import MetricRepository
from risc_tool.data.repositories.options import OptionRepository
from risc_tool.data.repositories.scalar import ScalarRepository
from risc_tool.ui.components.variable_selector_vm import VariableSelectorViewModel
from risc_tool.ui.config.config_vm import ConfigViewModel
from risc_tool.ui.data_explorer.data_explorer_vm import DataExplorerViewModel
from risc_tool.ui.data_importer.data_importer_vm import DataImporterViewModel
from risc_tool.ui.export.export_vm import ExportViewModel
from risc_tool.ui.filters.filters_vm import FilterViewModel
from risc_tool.ui.home.home_vm import HomeViewModel
from risc_tool.ui.iterations.iterations_vm import IterationsViewModel
from risc_tool.ui.metrics.metrics_vm import MetricViewModel
from risc_tool.ui.summary.summary_vm import SummaryViewModel
from risc_tool.utils.logging import get_logger

logger = get_logger(__name__)


class Session:
    """Container for the application's session state.

    Holds references to the repositories and view models, allowing
    them to persist across Streamlit reruns via session state.

    Attributes:
        data_repository: Repository for managing data sources.
        filter_repository: Repository for managing filters.
        metric_repository: Repository for managing metrics.
        option_repository: Repository for managing options and risk segments.
        scalar_repository: Repository for managing loss rate scalars.
        iterations_repository: Repository for managing iterations.
        data_importer_view_model: View model for the data importer UI.
        data_explorer_view_model: View model for the data explorer UI.
        filter_editor_view_model: View model for the filters UI.
        metric_editor_view_model: View model for the metrics UI.
        variable_selector_view_model: View model for variable selection UI.
        config_view_model: View model for the configuration UI.
        iterations_view_model: View model for the iterations UI.
    """

    def __init__(self):
        """Initialize a new session with default repositories and view models."""
        self.reset()
        logger.info("Session initialized with Repositories and View Models")

    def reset(self):
        """Reset the session to its initial state.

        Creates new repositories and respective view models.
        """
        logger.debug("Resetting session: recreating all repositories and view models")

        # Repositories
        self.data_repository = DataRepository()
        self.filter_repository = FilterRepository(self.data_repository)
        self.metric_repository = MetricRepository(self.data_repository)
        self.option_repository = OptionRepository()
        self.scalar_repository = ScalarRepository()
        self.iterations_repository = IterationsRepository(
            self.data_repository,
            self.filter_repository,
            self.metric_repository,
            self.option_repository,
            self.scalar_repository,
        )

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
        self.variable_selector_view_model = VariableSelectorViewModel(
            self.data_repository,
            self.metric_repository,
        )
        self.config_view_model = ConfigViewModel(
            self.option_repository,
            self.scalar_repository,
            self.metric_repository,
        )
        self.iterations_view_model = IterationsViewModel(
            self.data_repository,
            self.iterations_repository,
            self.option_repository,
            self.filter_repository,
            self.metric_repository,
            self.scalar_repository,
        )
        self.summary_view_model = SummaryViewModel(
            self.data_repository,
            self.filter_repository,
            self.metric_repository,
            self.iterations_repository,
        )
        self.export_view_model = ExportViewModel(self.iterations_repository)
        self.home_view_model = HomeViewModel()

    def to_dict(self) -> SessionJSON:
        """Serialize the session state to a SessionJSON object.

        Returns:
            A SessionJSON object representing the current session state.
        """
        logger.debug("Serializing session to JSON")
        return SessionJSON(
            data_repository=self.data_repository.to_dict(),
            filter_repository=self.filter_repository.to_dict(),
            metric_repository=self.metric_repository.to_dict(),
            scalar_repository=self.scalar_repository.to_dict(),
            options_repository=self.option_repository.to_dict(),
            iterations_repository=self.iterations_repository.to_dict(),
            data_explorer_view_model=self.data_explorer_view_model.to_dict(),
            iterations_view_model=self.iterations_view_model.to_dict(),
            summary_view_model=self.summary_view_model.to_dict(),
        )

    def rebuild_from_json(self, json_obj: SessionJSON):
        """Rebuild the session state from a SessionJSON object.

        Args:
            json_obj: A SessionJSON object containing the serialized session state.
        """
        logger.debug("Rebuilding session from JSON")

        # Repositories
        self.data_repository = DataRepository.from_dict(json_obj.data_repository)
        self.filter_repository, _ = FilterRepository.from_dict(
            json_obj.filter_repository,
            self.data_repository,
            errors="ignore",
        )
        self.metric_repository, _ = MetricRepository.from_dict(
            json_obj.metric_repository,
            self.data_repository,
            "ignore",
        )
        self.scalar_repository = ScalarRepository.from_dict(json_obj.scalar_repository)
        self.option_repository = OptionRepository.from_dict(json_obj.options_repository)
        self.iterations_repository, _ = IterationsRepository.from_dict(
            json_obj.iterations_repository,
            self.data_repository,
            self.filter_repository,
            self.metric_repository,
            self.option_repository,
            self.scalar_repository,
            "ignore",
        )

        # View Models
        self.data_importer_view_model = DataImporterViewModel(self.data_repository)
        self.data_explorer_view_model = DataExplorerViewModel.from_dict(
            json_obj.data_explorer_view_model,
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
        self.variable_selector_view_model = VariableSelectorViewModel(
            self.data_repository,
            self.metric_repository,
        )
        self.config_view_model = ConfigViewModel(
            self.option_repository,
            self.scalar_repository,
            self.metric_repository,
        )
        self.iterations_view_model = IterationsViewModel.from_dict(
            json_obj.iterations_view_model,
            self.data_repository,
            self.iterations_repository,
            self.option_repository,
            self.filter_repository,
            self.metric_repository,
            self.scalar_repository,
        )
        self.summary_view_model = SummaryViewModel.from_dict(
            json_obj.summary_view_model,
            self.data_repository,
            self.filter_repository,
            self.metric_repository,
            self.iterations_repository,
        )
        self.export_view_model = ExportViewModel(self.iterations_repository)
        # self.home_view_model = HomeViewModel()
