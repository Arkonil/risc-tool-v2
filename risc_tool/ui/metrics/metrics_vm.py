"""View model for the Metrics Editor page.

Manages UI state for metric creation/editing, including verification,
validation errors, and persistence via the MetricRepository.
"""

import typing as t
from collections import OrderedDict

import polars as pl

from risc_tool.data.models.changes import ChangeTracker
from risc_tool.data.models.completion import Completion
from risc_tool.data.models.enums import Signature
from risc_tool.data.models.exceptions import format_error
from risc_tool.data.models.id_remap import Remaps, get_remap, remap_value
from risc_tool.data.models.metric import Metric
from risc_tool.data.models.types import ChangeIDs
from risc_tool.data.models.uid import DataSourceID, MetricID
from risc_tool.data.repositories.data import DataRepository
from risc_tool.data.repositories.metric import MetricRepository
from risc_tool.utils.logging import get_logger

logger = get_logger(__name__)


class MetricViewModel(ChangeTracker):
    """View Model for the Metrics Editor page, managing UI state and validation."""

    @property
    def signature(self) -> Signature:
        """Get the component signature for change tracking.

        Returns:
            Signature.METRIC_VIEW_MODEL
        """
        return Signature.METRIC_VIEW_MODEL

    def __init__(
        self, data_repository: DataRepository, metric_repository: MetricRepository
    ) -> None:
        """Initialize the MetricViewModel.

        Args:
            data_repository: Repository for data sources and lazyframes.
            metric_repository: Repository for metric persistence.
        """
        super().__init__(dependencies=[data_repository, metric_repository])
        self.__data_repository = data_repository
        self.__metric_repository = metric_repository

        # UI States
        self.__view_mode: t.Literal["view", "edit"] = "view"
        self.__metric_cache = self.__empty_metric
        self.is_verified = False
        self.latest_editor_id = ""
        self.__errors: list[Exception] = []

    def on_dependency_update(self, change_ids: ChangeIDs) -> None:
        """Handle dependency updates by dropping the editor cache when stale.

        An edit session survives when the metric under edit still exists in
        the repository (it was kept or freshly rewritten by the repository's
        own validation); otherwise — deleted/invalidated metrics and unsaved
        drafts — the cache resets to the empty placeholder.

        Args:
            change_ids: The change IDs of the updated dependencies.
        """
        current_uid = self.__metric_cache.uid
        if current_uid != MetricID.EMPTY and current_uid in (
            self.__metric_repository.metrics
        ):
            return

        self.__metric_cache = self.__empty_metric
        self.is_verified = False
        self.__errors = []

    def on_dependency_remap(self, remaps: Remaps) -> None:
        """Adopt rewritten repository state when metric identities change.

        Editing a data source chains into MetricID changes (identities hash
        their data source IDs); the repository republishes those chained
        remaps after rewriting its own state, and the editor cache adopts
        the repository's rewritten version. Unsaved drafts carry no derived
        identity and are reset by :meth:`on_dependency_update` instead.

        Args:
            remaps: Identity remappings keyed by ID class.
        """
        metric_remap = get_remap(remaps, MetricID)
        if not metric_remap:
            return

        current_uid = self.__metric_cache.uid
        new_uid = remap_value(metric_remap, current_uid)
        if new_uid == current_uid:
            return

        self.logger.debug(
            "Adopting remapped editor cache for metric ID %s -> %s",
            current_uid,
            new_uid,
        )
        repo_metric = self.__metric_repository.metrics.get(new_uid)
        if repo_metric is None:
            return

        # Repository metrics are validated by definition; adopting one keeps
        # the in-progress edit consistent with its persisted counterpart.
        self.__metric_cache = repo_metric.duplicate()
        self.is_verified = True

    @property
    def __empty_metric(self) -> Metric:
        """A blank Metric used as a default editor cache."""
        return Metric(
            uid=MetricID.EMPTY,
            name="",
            query="",
            data_source_ids=[],
            is_cumulative=False,
        )

    @property
    def mode(self) -> t.Literal["view", "edit"]:
        """Whether the editor is in view or edit mode."""
        return self.__view_mode

    def set_mode(
        self, mode: t.Literal["view", "edit"], metric_id: MetricID = MetricID.EMPTY
    ) -> None:
        """Switch between view and edit modes, loading the metric to edit.

        Args:
            mode: The target mode.
            metric_id: The metric to edit (ignored in view mode).
        """
        self.__view_mode = mode
        self.__errors.clear()
        self.is_verified = False

        if mode == "edit":
            if metric_id == MetricID.EMPTY:
                self.__metric_cache = self.__empty_metric
            else:
                self.__metric_cache = self.__metric_repository.metrics.get(
                    metric_id, self.__empty_metric
                ).duplicate()
                self.is_verified = True

    @property
    def data_loaded(self) -> bool:
        """Whether valid data sources are loaded."""
        return self.__data_repository.has_valid_sources

    @property
    def metric_cache(self) -> Metric:
        """The Metric currently being edited."""
        return self.__metric_cache

    def set_metric_property(
        self,
        *,
        name: str | None = None,
        query: str | None = None,
        is_cumulative: bool | None = None,
        use_thousand_sep: bool | None = None,
        is_percentage: bool | None = None,
        decimal_places: int | None = None,
    ) -> None:
        """Update editable properties of the metric cache.

        The cache is a frozen Metric, so edits replace it with an updated
        copy; only the uid is left untouched (re-pinned on validation). Name
        and query changes invalidate verification.

        Args:
            name: New metric name, or None to keep unchanged.
            query: New metric query, or None to keep unchanged.
            is_cumulative: New cumulative flag, or None to keep unchanged.
            use_thousand_sep: New thousand separator flag, or None to keep unchanged.
            is_percentage: New percentage flag, or None to keep unchanged.
            decimal_places: New decimal places, or None to keep unchanged.
        """
        if name is not None and name != self.__metric_cache.name:
            self.__metric_cache = self.__metric_cache.model_copy(update={"name": name})
            self.is_verified = False

        if query is not None and query != self.__metric_cache.query:
            self.__metric_cache = self.__metric_cache.model_copy(update={"query": query})
            self.is_verified = False

        updates: dict[str, t.Any] = {}
        if is_cumulative is not None:
            updates["is_cumulative"] = is_cumulative
        if use_thousand_sep is not None:
            updates["use_thousand_sep"] = use_thousand_sep
        if is_percentage is not None:
            updates["is_percentage"] = is_percentage
        if decimal_places is not None:
            updates["decimal_places"] = decimal_places

        if updates:
            # Identity-preserving edit: the uid stays as pinned by
            # validation and is routed through create/modify on save.
            self.__metric_cache = self.__metric_cache.model_copy(update=updates)

    @property
    def all_data_source_ids(self) -> list[DataSourceID]:
        """All available data source IDs.

        Returns:
            A list of DataSourceIDs.
        """
        return [ds_id for ds_id in self.__data_repository.data_sources]

    @property
    def selected_data_source_ids(self) -> list[DataSourceID]:
        """The data source IDs selected for the metric being edited."""
        return self.__metric_cache.data_source_ids

    @selected_data_source_ids.setter
    def selected_data_source_ids(self, value: list[DataSourceID]) -> None:
        """Set the metric's data source IDs and invalidate verification.

        Args:
            value: The new DataSourceIDs.
        """
        self.__metric_cache = self.__metric_cache.model_copy(
            update={"data_source_ids": value}
        )
        self.is_verified = False

    def get_data_source_label(self, data_source_id: DataSourceID) -> str:
        """Get the label for a data source.

        Args:
            data_source_id: The ID of the data source.

        Returns:
            The data source label string.
        """
        return self.__data_repository.data_sources[data_source_id].label

    def get_column_completions(self) -> list[Completion]:
        """Get column name completions for the selected data sources.

        Returns:
            A list of Completion objects.
        """
        return self.__data_repository.get_completions_for_columns(
            self.selected_data_source_ids
        )

    def get_unique_values(self, column_name: str) -> list[str]:
        """Get sorted unique values of a column from the selected data sources.

        Args:
            column_name: The column to query.

        Returns:
            A list of unique values, or an empty list on error.
        """
        try:
            return (
                self.__data_repository
                .get_lazyframe(self.selected_data_source_ids)
                .select(column_name)
                .unique()
                .collect()
                .to_series()
                .to_list()
            )
        except (
            FileNotFoundError,
            KeyError,
            TypeError,
            ValueError,
            pl.exceptions.PolarsError,
        ) as e:
            logger.error(
                "Error retrieving unique values for column '%s': %s", column_name, e
            )
            return []

    def validate_metric(self, name: str, query: str, latest_editor_id: str) -> None:
        """Validate the metric under edit and mark it verified on success.

        Args:
            name: The metric name to validate.
            query: The metric query to validate.
            latest_editor_id: The editor instance that last triggered validation.
        """
        if not query.strip():
            self.__errors.append(ValueError("Metric query cannot be empty"))
            self.is_verified = False
            return

        if not name.strip():
            self.__errors.append(ValueError("Metric name cannot be empty"))
            self.is_verified = False
            return

        self.__errors.clear()

        try:
            current_id = self.metric_cache.uid

            for metric in self.__metric_repository.metrics.values():
                if name == metric.name and current_id != metric.uid:
                    raise ValueError("Metric name already exists")

            is_cumulative = self.__metric_cache.is_cumulative
            use_thousand_sep = self.__metric_cache.use_thousand_sep
            is_percentage = self.__metric_cache.is_percentage
            decimal_places = self.__metric_cache.decimal_places

            self.__metric_cache = self.__metric_repository.validate_metric(
                name=name,
                query=query,
                data_source_ids=self.__metric_cache.data_source_ids,
            )
            # Pin the original ID (EMPTY for new metrics) and reapply the
            # cached display settings onto the freshly validated metric.
            # Frozen model: the copy deliberately skips re-validation.
            self.__metric_cache = self.__metric_cache.model_copy(
                update={
                    "uid": current_id,
                    "is_cumulative": is_cumulative,
                    "use_thousand_sep": use_thousand_sep,
                    "is_percentage": is_percentage,
                    "decimal_places": decimal_places,
                }
            )

            self.is_verified = True
            self.latest_editor_id = latest_editor_id
        except (ValueError, SyntaxError) as e:
            self.__errors.append(e)
            self.is_verified = False

    def error_message(self) -> str:
        """Format accumulated validation errors as a single message.

        Returns:
            An empty string if there are no errors, otherwise the joined messages.
        """
        if not self.__errors:
            return ""

        messages: list[str] = []
        for error in self.__errors:
            messages.append(format_error(error))

        return "\n\n".join(messages)

    def save_metric(self) -> None:
        """Persist the verified metric by creating or modifying it.

        Raises:
            RuntimeError: If the metric is not verified or has an invalid ID.
        """
        if not self.is_verified or self.__errors:
            raise RuntimeError("Metric is not verified")

        if self.__metric_cache.uid == MetricID.TEMPORARY:
            raise RuntimeError("MetricID should not be TEMPORARY.")

        if self.__metric_cache.uid == MetricID.EMPTY:
            self.__metric_repository.create_metric(
                name=self.__metric_cache.name,
                query=self.__metric_cache.query,
                is_cumulative=self.__metric_cache.is_cumulative,
                use_thousand_sep=self.__metric_cache.use_thousand_sep,
                is_percentage=self.__metric_cache.is_percentage,
                decimal_places=self.__metric_cache.decimal_places,
                data_source_ids=self.__metric_cache.data_source_ids,
            )
        else:
            self.__metric_repository.modify_metric(
                metric_id=self.__metric_cache.uid,
                name=self.__metric_cache.name,
                query=self.__metric_cache.query,
                is_cumulative=self.__metric_cache.is_cumulative,
                use_thousand_sep=self.__metric_cache.use_thousand_sep,
                is_percentage=self.__metric_cache.is_percentage,
                decimal_places=self.__metric_cache.decimal_places,
                data_source_ids=self.__metric_cache.data_source_ids,
            )

        self.set_mode("view")

    @property
    def metrics(self) -> OrderedDict[MetricID, Metric]:
        """All available metrics from the repository.

        Returns:
            An ordered mapping of MetricID to Metric.
        """
        return self.__metric_repository.metrics

    def duplicate_metric(self, metric_id: MetricID) -> None:
        """Duplicate a metric via the repository.

        Args:
            metric_id: The ID of the metric to duplicate.
        """
        self.__metric_repository.duplicate_metric(metric_id)

    def remove_metric(self, metric_id: MetricID) -> None:
        """Remove a metric via the repository.

        Args:
            metric_id: The ID of the metric to remove.
        """
        self.__metric_repository.remove_metric(metric_id)


__all__ = ["MetricViewModel"]
