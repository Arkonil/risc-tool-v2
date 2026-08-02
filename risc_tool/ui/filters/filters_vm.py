"""View model for the Filter Editor page.

Manages UI state for filter creation/editing, including verification,
validation errors, and persistence via the FilterRepository.
"""

import typing as t

from risc_tool.data.models.changes import ChangeTracker
from risc_tool.data.models.completion import Completion
from risc_tool.data.models.enums import Signature
from risc_tool.data.models.exceptions import InvalidFilterError, format_error
from risc_tool.data.models.filter import Filter
from risc_tool.data.models.types import ChangeIDs, FilterID
from risc_tool.data.repositories.data import DataRepository
from risc_tool.data.repositories.filter import FilterRepository


class FilterViewModel(ChangeTracker):
    """View Model for the Filter Editor page, managing UI state and validation.

    Tracks the current view/edit mode, maintains a filter cache for the
    currently-edited filter, handles verification errors, and delegates
    persistence operations to FilterRepository.

    Attributes:
        is_verified: Whether the current filter cache has passed validation.
        latest_editor_id: The ID of the latest code editor session.
    """

    @property
    def signature(self) -> Signature:
        """Get the component signature for change tracking.

        Returns:
            Signature.FILTER_VIEW_MODEL
        """
        return Signature.FILTER_VIEW_MODEL

    def __init__(
        self, data_repository: DataRepository, filter_repository: FilterRepository
    ) -> None:
        """Initialize the FilterViewModel with repository dependencies.

        Args:
            data_repository: The DataRepository for schema lookups.
            filter_repository: The FilterRepository for CRUD operations.
        """
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
        """Handle dependency updates by resetting the filter cache and errors.

        Args:
            change_ids: Set of change IDs from the dependency.
        """
        self.__filter_cache = self.__empty_filter
        self.is_verified = False
        self.__errors = []

    @property
    def __empty_filter(self) -> Filter:
        """Create an empty placeholder filter with EMPTY ID.

        Returns:
            A Filter with uid=FilterID.EMPTY, empty name, and empty query.
        """
        return Filter(uid=FilterID.EMPTY, name="", query="")

    @property
    def mode(self) -> t.Literal["view", "edit"]:
        """Get the current UI mode.

        Returns:
            "view" for the filter list, "edit" for the filter editor.
        """
        return self.__view_mode

    def set_mode(
        self, mode: t.Literal["view", "edit"], filter_id: FilterID = FilterID.EMPTY
    ) -> None:
        """Switch between view and edit modes, optionally loading a filter for editing.

        Args:
            mode: The desired UI mode ("view" or "edit").
            filter_id: When mode is "edit", the ID of the filter to edit.
                Use FilterID.EMPTY to create a new filter.
        """
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
        """Check if any data sources are loaded and valid.

        Returns:
            True if at least one valid data source exists.
        """
        return self.__data_repository.has_valid_sources

    @property
    def filter_cache(self) -> Filter:
        """Get the current filter being edited in the cache.

        Returns:
            The Filter object currently in the edit cache.
        """
        return self.__filter_cache

    def set_filter_property(
        self,
        *,
        name: str | None = None,
        query: str | None = None,
    ) -> None:
        """Update one or more properties of the cached filter and mark as unverified.

        Args:
            name: New filter name, or None to keep current.
            query: New filter query string, or None to keep current.
        """
        if name is not None:
            self.__filter_cache.name = name
            self.is_verified = False

        if query is not None:
            self.__filter_cache.query = query
            self.is_verified = False

    def get_column_completions(self) -> list[Completion]:
        """Get column name completions for streamlit-code-editor auto-complete."""
        completions = self.__data_repository.get_completions_for_columns()
        return completions

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
            self.__filter_cache.uid = current_id
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
        """Persist the verified filter cache to the repository.

        Creates a new filter via the repository if the cache has FilterID.EMPTY,
        otherwise updates the existing filter. Resets the UI mode to "view"
        on success.

        Raises:
            RuntimeError: If the filter is not verified or has errors,
                or if the filter ID is TEMPORARY.
        """
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
        """Get all filters from the repository.

        Returns:
            Dictionary of FilterID to Filter.
        """
        return self.__filter_repository.filters

    def get_filters(
        self, filter_ids: list[FilterID] | None = None, outliers: bool = False
    ) -> dict[FilterID, Filter]:
        """Get filters from the repository with optional filtering.

        Args:
            filter_ids: Optional list of specific FilterIDs to retrieve.
            outliers: If False, exclude outlier rules; if True, only outliers.

        Returns:
            A dictionary of FilterID to Filter matching the criteria.
        """
        return self.__filter_repository.get_filters(filter_ids, outliers)

    def duplicate_filter(self, filter_id: FilterID) -> None:
        """Create a duplicate of a filter.

        Args:
            filter_id: The ID of the filter to duplicate.
        """
        self.__filter_repository.duplicate_filter(filter_id)

    def remove_filter(self, filter_id: FilterID) -> None:
        """Remove a filter from the repository.

        Args:
            filter_id: The ID of the filter to remove.
        """
        self.__filter_repository.remove_filter(filter_id)

    @property
    def lazyframe(self):
        """Get a combined LazyFrame of all valid data sources.

        Returns:
            A Polars LazyFrame with data from all valid sources.
        """
        return self.__data_repository.get_lazyframe()


__all__ = ["FilterViewModel"]
