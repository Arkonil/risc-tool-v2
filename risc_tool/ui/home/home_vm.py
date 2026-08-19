"""View Model for the Home page and Session JSON import."""

import typing as t

from streamlit.runtime.uploaded_file_manager import UploadedFile

from risc_tool.data.models.changes import ChangeTracker
from risc_tool.data.models.data_source import DataSource
from risc_tool.data.models.enums import Signature
from risc_tool.data.models.json_models import SessionJSON
from risc_tool.data.models.object_id import DataSourceID
from risc_tool.data.models.types import ChangeIDs
from risc_tool.data.repositories.data import DataRepository
from risc_tool.data.repositories.filter import FilterRepository
from risc_tool.data.repositories.iterations import IterationsRepository
from risc_tool.data.repositories.metric import MetricRepository
from risc_tool.ui.data_explorer.data_explorer_vm import DataExplorerViewModel
from risc_tool.ui.summary.summary_vm import SummaryViewModel


class HomeViewModel(ChangeTracker):
    """View model managing Home page state and session JSON imports."""

    @property
    def signature(self) -> Signature:
        """Get the component signature for change tracking.

        Returns:
            Signature.HOME_VIEW_MODEL
        """
        return Signature.HOME_VIEW_MODEL

    def __init__(self) -> None:
        """Initialize the HomeViewModel with default state."""
        super().__init__(dependencies=[])

        self.home_page_view: t.Literal["welcome", "import-json"] = "welcome"
        self.uploaded_file: UploadedFile | None = None
        self.raw_session_json: SessionJSON | None = None
        self.validated_session_json: SessionJSON | None = None

    def on_dependency_update(self, change_ids: ChangeIDs) -> None:
        """Handle changes in dependencies (no-op for the Home page)."""

    def set_home_page_view(self, view: t.Literal["welcome", "import-json"]) -> None:
        """Switch between welcome and import-json sub-views."""
        self.home_page_view = view

    def clear_uploaded_file(self) -> None:
        """Clear uploaded file state."""
        self.uploaded_file = None
        self.raw_session_json = None
        self.validated_session_json = None

    def get_jsons(self) -> tuple[SessionJSON, SessionJSON]:
        """Validate and parse raw JSON string into SessionJSON schema."""
        if self.uploaded_file is None:
            raise ValueError("No uploaded file to process.")

        if self.raw_session_json is None:
            self.raw_session_json = SessionJSON.model_validate_json(
                self.uploaded_file.read().decode("utf-8")
            )

        if self.validated_session_json is None:
            self.validated_session_json = self.raw_session_json.model_copy(deep=True)

        return self.raw_session_json, self.validated_session_json

    def get_data_source_corrections(self) -> dict[DataSourceID, Exception | None]:
        """Return a dictionary of data source corrections."""

        if self.raw_session_json is None or self.validated_session_json is None:
            raise ValueError("Validated session JSON is not available.")

        current_errors: dict[DataSourceID, Exception | None] = {}

        for ds in self.validated_session_json.data_repository.data_sources.values():
            try:
                ds.validate_read_config()
            except Exception as error:  # ruff:ignore[blind-except]
                current_errors[ds.uid] = error

            if self.raw_session_json.data_repository.data_sources[ds.uid] != ds:
                current_errors[ds.uid] = None  # No error, but correction was made

        return current_errors

    def validate_data_source(self, updated_ds: DataSource) -> None:
        """Validate a specific data source and update the correction mapping."""
        if self.validated_session_json is None:
            raise ValueError("Validated session JSON is not available.")

        self.validated_session_json.data_repository.data_sources[updated_ds.uid] = (
            updated_ds
        )

    def validate_columns(self):
        """Validate the imported session JSON against the data schema.

        Returns:
            A tuple of validation results for filters, metrics, metric variables,
            iterations, data explorer variables, and summary variables.
        """
        if self.validated_session_json is None:
            raise ValueError("Validated session JSON is not available.")

        data_repository = DataRepository.from_dict(
            self.validated_session_json.data_repository
        )
        data_repository.data_config.update_schema(data_repository.data_sources.values())

        # Filters
        invalid_filters = FilterRepository.validate_json(
            data_repository, self.validated_session_json.filter_repository
        )

        # Metrics
        invalid_metrics, missing_metric_variables = MetricRepository.validate_json(
            data_repository=data_repository,
            data=self.validated_session_json.metric_repository,
        )

        # Iterations
        invalid_iterations = IterationsRepository.validate_json(
            data_repository, self.validated_session_json.iterations_repository
        )

        # Data Explorer ViewModel
        missing_data_explorer_variables = DataExplorerViewModel.validate_json(
            data_repository, self.validated_session_json.data_explorer_view_model
        )

        # Summary ViewModel
        missing_summary_variables = SummaryViewModel.validate_json(
            data_repository, self.validated_session_json.summary_view_model
        )

        return (
            invalid_filters,
            invalid_metrics,
            missing_metric_variables,
            invalid_iterations,
            missing_data_explorer_variables,
            missing_summary_variables,
        )


__all__ = ["HomeViewModel"]
