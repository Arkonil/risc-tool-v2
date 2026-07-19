"""Session management for the RISC Tool application.

This module provides the Session class which holds the application state
including repositories and view models.
"""

from risc_tool.data.repositories.data import DataRepository
from risc_tool.ui.data_importer.data_importer_vm import DataImporterViewModel


class Session:
    """Container for the application's session state.

    Holds references to the data repository and view models, allowing
    them to persist across Streamlit reruns via session state.

    Attributes:
        data_repository: Repository for managing data sources.
        data_importer_view_model: View model for the data importer UI.
    """

    def __init__(self):
        """Initialize a new session with default repositories and view models."""
        self.reset()

    def reset(self):
        """Reset the session to its initial state.

        Creates a new DataRepository and DataImporterViewModel.
        """
        self.data_repository = DataRepository()
        self.data_importer_view_model = DataImporterViewModel(self.data_repository)
