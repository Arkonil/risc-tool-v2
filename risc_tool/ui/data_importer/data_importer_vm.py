"""View model for the Data Importer UI component.

This module provides the view model layer for managing data source import
state, including adding, updating, and deleting data sources, as well as
tracking the currently selected data source for preview.
"""

import typing as t
from collections import OrderedDict
from pathlib import Path

from risc_tool.data.models.changes import ChangeTracker
from risc_tool.data.models.data_source import DataSource, ReadConfig
from risc_tool.data.models.enums import Signature
from risc_tool.data.models.exceptions import DataImportError
from risc_tool.data.models.types import ChangeIDs, DataSourceID
from risc_tool.data.repositories.data import DataRepository


class ImportStatus(t.TypedDict):
    """Status of a data source import operation.

    Attributes:
        status: One of "success", "error", "loading", or "unset".
        message: Human-readable message describing the status.
    """

    status: t.Literal["success", "error", "loading", "unset"]
    message: str


class DataSourceViewModel:
    """View model for a single data source in the importer UI.

    Holds the data source model and its import status for display in the UI.

    Attributes:
        data_source: The DataSource model being represented.
        import_status: Current import status (success, error, loading, unset).
    """

    def __init__(
        self,
        data_source: DataSource | None = None,
        import_status: ImportStatus | None = None,
    ):
        """Initialize the DataSourceViewModel.

        Args:
            data_source: The DataSource to wrap. Defaults to an empty DataSource.
            import_status: The initial import status. Defaults to "unset".
        """
        if data_source is None:
            data_source = DataSource.empty()

        if import_status is None:
            import_status = {"status": "unset", "message": ""}

        self.data_source: DataSource = data_source
        self.import_status: ImportStatus = import_status


class DataImporterViewModel(ChangeTracker):
    """View model for the Data Importer UI.

    Manages the collection of data source view models, handles user actions
    (add, update, delete), and tracks the currently selected data source
    for preview. Subscribes to DataRepository changes to stay in sync.

    Attributes:
        showing_empty_data_source: Whether the empty "new source" form is shown.
        empty_data_source_view: View model for the empty/new data source form.
        data_source_views: Ordered dict of data source view models by ID.
        current_ds_id: The currently selected data source ID for preview.
    """

    @property
    def signature(self) -> Signature:
        """Get the component signature for change tracking.

        Returns:
            Signature.DATA_IMPORTER_VIEW_MODEL
        """
        return Signature.DATA_IMPORTER_VIEW_MODEL

    def __init__(self, data_repository: DataRepository) -> None:
        """Initialize the DataImporterViewModel.

        Args:
            data_repository: The DataRepository to sync with.
        """
        super().__init__(dependencies=[data_repository])

        # Dependencies
        self.__data_repository = data_repository

        # File Importer States
        self.showing_empty_data_source = True
        self.empty_data_source_view = DataSourceViewModel()
        self.data_source_views: OrderedDict[DataSourceID, DataSourceViewModel] = (
            OrderedDict()
        )
        for ds_uid, ds in self.__data_repository.data_sources.items():
            self.data_source_views[ds_uid] = DataSourceViewModel(data_source=ds)

        # Data Preview
        self._current_ds_id: DataSourceID | None = None

    def on_dependency_update(self, change_ids: ChangeIDs) -> None:
        """Handle updates from the DataRepository dependency.

        Syncs the view models with the repository's current data sources,
        adding new ones and removing deleted ones.

        Args:
            change_ids: Set of change IDs from the dependency.
        """
        changed_dependencies = {sig for sig, _ in change_ids}

        if Signature.DATA_REPOSITORY in changed_dependencies:
            existing_ds_ids = set(self.__data_repository.data_sources.keys())
            removed_ds_ids = set(self.data_source_views.keys()) - existing_ds_ids
            self.logger.debug(
                "Syncing data source views: %d existing, %d removed",
                len(existing_ds_ids),
                len(removed_ds_ids),
            )

            for ds_id in existing_ds_ids:
                self.data_source_views[ds_id] = DataSourceViewModel(
                    data_source=self.__data_repository.data_sources[ds_id],
                    import_status={
                        "status": "success",
                        "message": f"File imported successfully: {self.__data_repository.data_sources[ds_id].filepath}",
                    },
                )

            for ds_id in removed_ds_ids:
                del self.data_source_views[ds_id]

    @property
    def is_empty(self) -> bool:
        """Check if there are no data sources configured.

        Returns:
            True if no data sources exist, False otherwise.
        """
        return len(self.data_source_views) == 0

    @property
    def current_ds_id(self) -> DataSourceID | None:
        """Get the currently selected data source ID for preview.

        If no explicit selection is made, returns the first successfully
        imported data source.

        Returns:
            The selected DataSourceID, or None if no sources exist.
        """
        if self._current_ds_id is not None:
            return self._current_ds_id

        for ds_uid, ds_vm in self.data_source_views.items():
            if ds_vm.import_status["status"] == "success":
                self._current_ds_id = ds_uid
                return ds_uid

        return None

    @current_ds_id.setter
    def current_ds_id(self, ds_uid: DataSourceID | None) -> None:
        """Set the currently selected data source ID.

        Args:
            ds_uid: The DataSourceID to select, or None to clear selection.
        """
        if ds_uid is None:
            self._current_ds_id = None
            return

        if ds_uid not in self.data_source_views:
            return

        self._current_ds_id = ds_uid

    def update_data_source(
        self,
        data_source_id: DataSourceID,
        filepath: Path | None,
        label: str,
        read_config: ReadConfig,
    ):
        """Add a new data source or update an existing one.

        For EMPTY ID, creates a new data source via the repository.
        For existing IDs, updates the data source in the repository.
        Handles validation errors by updating the view model's import status.

        Args:
            data_source_id: The ID of the data source to update, or EMPTY for new.
            filepath: Path to the data file.
            label: Human-readable label for the data source.
            read_config: Configuration for reading the file.
        """
        self.logger.info(
            "Request to update/add data source ID %s. Filepath: %s, Label: %s",
            data_source_id,
            filepath,
            label,
        )

        if (
            data_source_id not in self.data_source_views
            and data_source_id != DataSourceID.EMPTY
        ):
            self.logger.warning("Data source ID %s not found in views.", data_source_id)
            return

        if data_source_id == DataSourceID.EMPTY:
            try:
                if filepath is None:
                    raise DataImportError("Filepath is required")

                new_data_source = self.__data_repository.add_data_source(
                    label=label,
                    filepath=filepath,
                    read_config=read_config,
                )
                self.showing_empty_data_source = False
                self.empty_data_source_view = DataSourceViewModel()
                self.logger.info("New data source '%s' created with ID %s", label, new_data_source.uid)
            except DataImportError as e:
                self.logger.error("Import error adding new data source: %s", e)
                eds = self.empty_data_source_view.data_source

                eds.filepath = filepath or Path("")
                eds.label = label
                eds.read_config = read_config

                self.empty_data_source_view.import_status = {
                    "status": "error",
                    "message": str(e),
                }

        else:
            try:
                new_data_source = self.__data_repository.update_data_source(
                    data_source_id=data_source_id,
                    filepath=filepath,
                    label=label,
                    read_config=read_config,
                )
                self.logger.info("Data source ID %s updated successfully", data_source_id)
                self._current_ds_id = new_data_source.uid
            except DataImportError as e:
                self.logger.error(
                    "Import error updating data source ID %s: %s", data_source_id, e
                )
                self.data_source_views[data_source_id].import_status = {
                    "status": "error",
                    "message": str(e),
                }
                self._current_ds_id = None

    def delete_data_source(self, data_source_id: DataSourceID):
        """Delete a data source.

        Args:
            data_source_id: The ID of the data source to delete.
        """
        self.logger.warning("Request to delete data source ID %s", data_source_id)
        if data_source_id == DataSourceID.EMPTY:
            self.logger.debug("Hiding empty data source form (user cancelled)")
            self.showing_empty_data_source = False
            self.empty_data_source_view = DataSourceViewModel()
            return

        if data_source_id not in self.data_source_views:
            self.logger.warning(
                "Data source ID %s not found in views for deletion", data_source_id
            )
            return

        self.__data_repository.delete_data_source(data_source_id)

        if self._current_ds_id == data_source_id:
            self._current_ds_id = None

        if len(self.data_source_views) == 0:
            self.show_empty_data_source()
            self._current_ds_uid = None

    def show_empty_data_source(self):
        """Show the empty data source form for adding a new source."""
        self.logger.debug("Showing empty data source form")
        self.showing_empty_data_source = True
        self.empty_data_source_view = DataSourceViewModel()
