"""View model for the Data Importer UI component."""

import typing as t
from collections import OrderedDict
from pathlib import Path

from risc_tool_v2.data.core.changes import ChangeTracker
from risc_tool_v2.data.core.enums import Signature
from risc_tool_v2.data.core.exceptions import DataImportError
from risc_tool_v2.data.core.id_remap import Remaps, get_remap, remap_value
from risc_tool_v2.data.core.types import ChangeIDs
from risc_tool_v2.data.core.uid import DataSourceID
from risc_tool_v2.data.data_source.models.data_source import DataSource, ReadConfig
from risc_tool_v2.data.data_source.repositories.data_repository import DataRepository


class ImportStatus(t.TypedDict):
    status: t.Literal["success", "error", "loading", "unset"]
    message: str


class DataSourceViewModel:
    def __init__(
        self,
        data_source: DataSource | None = None,
        import_status: ImportStatus | None = None,
    ):
        if data_source is None:
            data_source = DataSource.empty()

        if import_status is None:
            import_status = {"status": "unset", "message": ""}

        self.data_source: DataSource = data_source
        self.import_status: ImportStatus = import_status


class DataImporterViewModel(ChangeTracker):
    @property
    def signature(self) -> Signature:
        return Signature.DATA_IMPORTER_VIEW_MODEL

    def __init__(self, data_repository: DataRepository) -> None:
        super().__init__(dependencies=[data_repository])
        self.__data_repository = data_repository

        self.showing_empty_data_source = True
        self.empty_data_source_view = DataSourceViewModel()
        self.data_source_views: OrderedDict[DataSourceID, DataSourceViewModel] = (
            OrderedDict()
        )
        for ds_uid, ds in self.__data_repository.data_sources.items():
            self.data_source_views[ds_uid] = DataSourceViewModel(
                data_source=ds,
                import_status={
                    "status": "success",
                    "message": f"File imported successfully: {ds.filepath}",
                },
            )

        self._current_ds_id: DataSourceID | None = None

    def on_dependency_update(self, change_ids: ChangeIDs) -> None:
        changed_dependencies = {sig for sig, _ in change_ids}

        if Signature.DATA_REPOSITORY in changed_dependencies:
            repo_sources = self.__data_repository.data_sources
            removed_ds_ids = set(self.data_source_views.keys()) - set(
                repo_sources.keys()
            )
            self.logger.debug(
                "Syncing data source views: %d existing, %d removed",
                len(repo_sources),
                len(removed_ds_ids),
            )

            for ds_id, ds in repo_sources.items():
                view = self.data_source_views.get(ds_id)
                if view is not None and view.data_source is ds:
                    continue

                self.data_source_views[ds_id] = DataSourceViewModel(
                    data_source=ds,
                    import_status={
                        "status": "success",
                        "message": f"File imported successfully: {ds.filepath}",
                    },
                )

            for ds_id in removed_ds_ids:
                del self.data_source_views[ds_id]

    def on_dependency_remap(self, remaps: Remaps) -> None:
        remap = get_remap(remaps, DataSourceID)
        if not remap:
            return

        self.logger.debug("Remapping data source view IDs: %s", remap)

        self.data_source_views = OrderedDict(
            (remap_value(remap, uid), view)
            for uid, view in self.data_source_views.items()
        )

        repo_sources = self.__data_repository.data_sources
        for new_id in remap.values():
            view = self.data_source_views.get(new_id)
            if view is None or new_id not in repo_sources:
                continue

            ds = repo_sources[new_id]
            view.data_source = ds
            view.import_status = {
                "status": "success",
                "message": f"File imported successfully: {ds.filepath}",
            }

        if self._current_ds_id is not None:
            self._current_ds_id = remap_value(remap, self._current_ds_id)

    @property
    def is_empty(self) -> bool:
        return len(self.data_source_views) == 0

    @property
    def current_ds_id(self) -> DataSourceID | None:
        if self._current_ds_id is not None:
            return self._current_ds_id

        for ds_uid, ds_vm in self.data_source_views.items():
            if ds_vm.import_status["status"] == "success":
                self._current_ds_id = ds_uid
                return ds_uid

        return None

    @current_ds_id.setter
    def current_ds_id(self, ds_uid: DataSourceID | None) -> None:
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
                self.logger.info(
                    "New data source '%s' created with ID %s",
                    label,
                    new_data_source.uid,
                )
            except DataImportError as e:
                self.logger.error("Import error adding new data source: %s", e)
                self.empty_data_source_view.data_source = DataSource(
                    uid=DataSourceID.EMPTY,
                    label=label,
                    filepath=filepath or Path(""),
                    read_config=read_config,
                )

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
                self.logger.info(
                    "Data source ID %s updated successfully", data_source_id
                )
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
            self._current_ds_id = None

    def show_empty_data_source(self):
        self.logger.debug("Showing empty data source form")
        self.showing_empty_data_source = True
        self.empty_data_source_view = DataSourceViewModel()


__all__ = ["DataImporterViewModel", "DataSourceViewModel", "ImportStatus"]
