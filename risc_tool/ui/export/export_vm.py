"""View Model for the Export page."""

from risc_tool.data.models.changes import ChangeTracker
from risc_tool.data.models.enums import ExportTabName, Signature
from risc_tool.data.models.types import ChangeIDs, IterationID
from risc_tool.data.repositories.iterations import IterationsRepository


class ExportViewModel(ChangeTracker):
    """View model managing Export page tabs and state."""

    @property
    def signature(self) -> Signature:
        """Get the component signature for change tracking.

        Returns:
            Signature.EXPORT_VIEW_MODEL
        """
        return Signature.EXPORT_VIEW_MODEL

    def __init__(self, iterations_repository: IterationsRepository) -> None:
        """Initialize the ExportViewModel.

        Args:
            iterations_repository: Repository providing iterations and generated code.
        """
        super().__init__(dependencies=[iterations_repository])

        self.__iterations_repository = iterations_repository
        self.current_tab_name: ExportTabName = ExportTabName.SESSION_ARCHIVE

    def on_dependency_update(self, change_ids: ChangeIDs) -> None:
        """Handle changes in dependencies."""

    @property
    def tab_names(self) -> list[ExportTabName]:
        """Available tabs in Export page."""
        return [
            ExportTabName.SESSION_ARCHIVE,
            ExportTabName.PYTHON_CODE,
            ExportTabName.SAS_CODE,
        ]

    @property
    def no_iteration(self) -> bool:
        """Check if iterations repository contains no iterations."""
        return len(self.__iterations_repository.iterations) == 0

    def get_python_code(self, iteration_id: IterationID, default: bool) -> str:
        """Get generated Python code for the specified iteration."""
        return self.__iterations_repository.get_python_code(
            iteration_id=iteration_id, default=default
        )

    def get_sas_code(
        self, iteration_id: IterationID, default: bool, use_macro: bool
    ) -> str:
        """Get generated SAS code for the specified iteration."""
        return self.__iterations_repository.get_sas_code(
            iteration_id=iteration_id, default=default, use_macro=use_macro
        )


__all__ = ["ExportViewModel"]
