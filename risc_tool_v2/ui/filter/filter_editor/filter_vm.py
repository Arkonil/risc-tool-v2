"""View model for the Filter Editor page."""

import typing as t

from risc_tool_v2.data.core.changes import ChangeTracker
from risc_tool_v2.data.core.enums import Signature
from risc_tool_v2.data.core.exceptions import InvalidFilterError, format_error
from risc_tool_v2.data.core.id_remap import Remaps, get_remap, remap_value
from risc_tool_v2.data.core.types import ChangeIDs
from risc_tool_v2.data.core.uid import DataSourceID, FilterID
from risc_tool_v2.data.data_source.models.completion import Completion
from risc_tool_v2.data.data_source.repositories.data_repository import DataRepository
from risc_tool_v2.data.filter.models.filter import Filter
from risc_tool_v2.data.filter.repositories.filter_repository import FilterRepository


class FilterViewModel(ChangeTracker):
    @property
    def signature(self) -> Signature:
        return Signature.FILTER_VIEW_MODEL

    def __init__(
        self, data_repository: DataRepository, filter_repository: FilterRepository
    ) -> None:
        super().__init__(dependencies=[data_repository, filter_repository])
        self.__data_repository = data_repository
        self.__filter_repository = filter_repository

        # UI States
        self.__view_mode: t.Literal["view", "edit"] = "view"
        self.__filter_cache = self.__empty_filter
        self.is_verified = False
        self.latest_editor_id = ""
        self.__errors: list[InvalidFilterError | ValueError | SyntaxError] = []

    def on_dependency_update(self, change_ids: ChangeIDs) -> None:
        current_uid = self.__filter_cache.uid
        if current_uid != FilterID.EMPTY and (
            current_uid in self.__filter_repository.filters
        ):
            return

        self.__filter_cache = self.__empty_filter
        self.is_verified = False
        self.__errors = []

    def on_dependency_remap(self, remaps: Remaps) -> None:
        ds_remap = get_remap(remaps, DataSourceID)
        if ds_remap:
            self.logger.debug(
                "Data source IDs remapped; the editor cache holds no "
                "source references: %s",
                ds_remap,
            )

        filter_remap = get_remap(remaps, FilterID)
        if not filter_remap:
            return

        current_uid = self.__filter_cache.uid
        new_uid = remap_value(filter_remap, current_uid)
        if new_uid == current_uid:
            return

        self.logger.debug(
            "Remapping editor cache for filter ID %s -> %s", current_uid, new_uid
        )
        repo_filter = self.__filter_repository.filters.get(new_uid)
        if repo_filter is None:
            return

        self.__filter_cache = repo_filter.duplicate()
        self.is_verified = True

    @property
    def __empty_filter(self) -> Filter:
        return Filter(uid=FilterID.EMPTY, name="", query="")

    @property
    def mode(self) -> t.Literal["view", "edit"]:
        return self.__view_mode

    def set_mode(
        self, mode: t.Literal["view", "edit"], filter_id: FilterID = FilterID.EMPTY
    ) -> None:
        self.__view_mode = mode
        self.__errors.clear()
        self.is_verified = False
        self.logger.debug("Setting UI mode to '%s' (filter_id=%s)", mode, filter_id)

        if mode == "edit":
            if filter_id == FilterID.EMPTY:
                self.__filter_cache = self.__empty_filter
            else:
                self.__filter_cache = self.__filter_repository.filters.get(
                    filter_id, self.__empty_filter
                ).duplicate()
                self.is_verified = True

    @property
    def data_loaded(self) -> bool:
        return self.__data_repository.has_valid_sources

    @property
    def filter_cache(self) -> Filter:
        return self.__filter_cache

    def set_filter_property(
        self,
        *,
        name: str | None = None,
        query: str | None = None,
    ) -> None:
        if name is not None:
            self.__filter_cache = self.__filter_cache.model_copy(update={"name": name})
            self.is_verified = False

        if query is not None:
            self.__filter_cache = self.__filter_cache.model_copy(
                update={"query": query}
            )
            self.is_verified = False

    def get_column_completions(self) -> list[Completion]:
        return self.__data_repository.get_completions_for_columns()

    def validate_filter(self, name: str, query: str, latest_editor_id: str) -> None:
        self.logger.info("Request to validate filter '%s'", name)
        if not query.strip():
            self.__errors.append(ValueError("Filter query cannot be empty"))
            self.is_verified = False
            return

        if not name.strip():
            self.__errors.append(ValueError("Filter name cannot be empty"))
            self.is_verified = False
            return

        self.__errors.clear()

        try:
            current_id = self.filter_cache.uid

            for filter_obj in self.__filter_repository.filters.values():
                if name == filter_obj.name and current_id != filter_obj.uid:
                    raise ValueError("Filter name already exists")

            self.__filter_cache = self.__filter_repository.validate_filter(
                name=name,
                query=query,
            )
            self.__filter_cache = self.__filter_cache.model_copy(
                update={"uid": current_id}
            )
            self.is_verified = True
            self.latest_editor_id = latest_editor_id
            self.logger.info("Filter '%s' validated successfully", name)
        except (InvalidFilterError, SyntaxError, ValueError) as e:
            self.logger.warning("Validation failed for filter '%s': %s", name, e)
            self.__errors.append(e)
            self.is_verified = False

    def error_message(self) -> str:
        if not self.__errors:
            return ""

        messages: list[str] = []
        for error in self.__errors:
            messages.append(format_error(error))

        return "\n\n".join(messages)

    def save_filter(self) -> None:
        self.logger.info(
            "Request to save filter ID %s (name: %s)",
            self.__filter_cache.uid,
            self.__filter_cache.name,
        )
        if not self.is_verified or self.__errors:
            self.logger.warning(
                "Save rejected: filter not verified (is_verified=%s, errors=%d)",
                self.is_verified,
                len(self.__errors),
            )
            raise RuntimeError("Filter is not verified")

        if self.__filter_cache.uid == FilterID.TEMPORARY:
            self.logger.error("Save rejected: filter has TEMPORARY ID")
            raise RuntimeError("FilterID should not be TEMPORARY.")

        if self.__filter_cache.uid == FilterID.EMPTY:
            self.__filter_repository.create_filter(
                name=self.__filter_cache.name,
                query=self.__filter_cache.query,
            )
        else:
            self.__filter_repository.modify_filter(
                filter_id=self.__filter_cache.uid,
                name=self.__filter_cache.name,
                query=self.__filter_cache.query,
            )

        self.logger.info("Filter '%s' saved successfully", self.__filter_cache.name)
        self.set_mode("view")

    @property
    def filters(self) -> dict[FilterID, Filter]:
        return self.__filter_repository.filters

    def get_filters(
        self, filter_ids: list[FilterID] | None = None, outliers: bool = False
    ) -> dict[FilterID, Filter]:
        return self.__filter_repository.get_filters(filter_ids, outliers)

    def duplicate_filter(self, filter_id: FilterID) -> None:
        self.__filter_repository.duplicate_filter(filter_id)

    def remove_filter(self, filter_id: FilterID) -> None:
        self.__filter_repository.remove_filter(filter_id)

    @property
    def lazyframe(self):
        return self.__data_repository.get_lazyframe()


__all__ = ["FilterViewModel"]
