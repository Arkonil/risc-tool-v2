"""Repository for managing user-defined metrics with change notification.

Provides CRUD operations for frozen, content-addressed Metric objects,
validates queries against the current data schema, and notifies subscribers
of changes. When a data source's content-derived ID changes, stored metrics
referencing it are rewritten and the resulting metric identity changes are
published as chained MetricID remaps.
"""

import typing as t
from collections import OrderedDict

import polars as pl

from risc_tool.data.models.enums import Signature, VariableType
from risc_tool.data.models.exceptions import (
    MissingColumnError,
    SampleDataNotLoadedError,
    VariableNotNumericError,
)
from risc_tool.data.models.id_remap import Remaps, get_remap, remap_list
from risc_tool.data.models.json_models import MetricJSON, MetricRepositoryJSON
from risc_tool.data.models.metric import Metric
from risc_tool.data.models.types import ChangeIDs
from risc_tool.data.models.uid import DataSourceID, MetricID
from risc_tool.data.repositories.base import BaseRepository
from risc_tool.data.repositories.data import DataRepository
from risc_tool.utils.duplicate_name import create_duplicate_name


class MetricRepository(BaseRepository):
    """Repository for managing user-defined metrics.

    Attributes:
        metrics: Ordered mapping of MetricID to user-defined metrics.
    """

    @property
    def signature(self) -> Signature:
        """Get the component signature for change tracking.

        Returns:
            Signature.METRIC_REPOSITORY
        """
        return Signature.METRIC_REPOSITORY

    def __init__(self, data_repository: DataRepository) -> None:
        """Initialize the MetricRepository with its data dependency.

        Args:
            data_repository: Repository for data sources and lazyframes.
        """
        super().__init__(dependencies=[data_repository])

        # User defined metrics
        self.metrics: OrderedDict[MetricID, Metric] = OrderedDict()

        # Cache
        self.__verified_metrics: dict[tuple[str, tuple[DataSourceID, ...]], Metric] = {}

        # Dependencies
        self.__data_repository: DataRepository = data_repository

    def _replace_metric(self, old_id: MetricID, new_metric: Metric) -> None:
        """Replace a metric in place, preserving its position.

        If the new metric has a different content-derived ID, the old ID is
        removed and the new ID takes its place in the ordering.

        Args:
            old_id: The ID of the metric being replaced.
            new_metric: The replacement metric.
        """
        new_id = new_metric.uid
        if new_id == old_id:
            self.metrics[old_id] = new_metric
            return

        items = [
            (new_id, new_metric) if mid == old_id else (mid, m)
            for mid, m in self.metrics.items()
        ]
        self.metrics.clear()
        self.metrics.update(items)

    def _update_user_defined_metrics(self):
        """Validate user-defined metrics against the data schema.

        Metrics are re-scoped to the data sources that still validate; those
        whose queries fail validation for all their data sources are removed.
        Identity changes are stashed so they are published as chained remaps.
        """
        metric_ids_to_remove: list[MetricID] = []

        for metric_id, metric in list(self.metrics.items()):
            valid_data_source_ids: list[DataSourceID] = []

            for ds_id in self.__data_repository.data_sources:
                if ds_id not in metric.data_source_ids:
                    continue

                try:
                    all_columns = self.__data_repository.common_columns([ds_id])
                    all_column_names = [col for col, _ in all_columns]
                    metric.validate_query(all_column_names)
                except (SyntaxError, ValueError):
                    pass
                else:
                    valid_data_source_ids.append(ds_id)

            if not valid_data_source_ids:
                metric_ids_to_remove.append(metric_id)
                continue

            if valid_data_source_ids != metric.data_source_ids:
                rewritten = metric.with_updates(data_source_ids=valid_data_source_ids)
                self._replace_metric(metric_id, rewritten)
                if rewritten.uid != metric_id:
                    self._stash_remap(metric_id, rewritten.uid)

        for metric_id in metric_ids_to_remove:
            del self.metrics[metric_id]
            self._stash_removal(metric_id)

    def _clear_cache(self):
        """Clear the verified metric cache."""
        self.__verified_metrics.clear()

    def on_dependency_remap(self, remaps: Remaps) -> None:
        """Rewrite stored metrics when a data source's ID changes.

        Content changes to a data source re-derive its ID; because metric
        identities hash their data source IDs, every affected metric is
        re-keyed and its old-to-new MetricID change is published as a
        chained remap once dependency processing completes.

        Args:
            remaps: Identity remappings keyed by ID class.
        """
        ds_remap = get_remap(remaps, DataSourceID)
        if not ds_remap:
            return

        self.logger.debug("Remapping metric data source references: %s", ds_remap)

        for metric_id, metric in list(self.metrics.items()):
            if not any(ds_id in ds_remap for ds_id in metric.data_source_ids):
                continue

            rewritten = metric.with_updates(
                data_source_ids=remap_list(ds_remap, metric.data_source_ids)
            )
            self._replace_metric(metric_id, rewritten)
            if rewritten.uid != metric_id:
                self.logger.debug(
                    "Metric '%s' remapped %s -> %s",
                    metric.name,
                    metric_id,
                    rewritten.uid,
                )
                self._stash_remap(metric_id, rewritten.uid)

    def on_dependency_update(self, change_ids: ChangeIDs):
        """Handle data schema updates by revalidating stored metrics.

        Args:
            change_ids: The change IDs of the updated dependencies.
        """
        self.logger.info("DataRepository updated, revalidating user-defined metrics")
        self._update_user_defined_metrics()
        self._clear_cache()

    def validate_metric_input_column(
        self, column_name: str, data_source_ids: list[DataSourceID]
    ):
        """Validate that a column is numeric and available in the given data sources.

        Args:
            column_name: The column to validate.
            data_source_ids: The data sources to check the column against.

        Raises:
            VariableNotNumericError: If the column is categorical.
            MissingColumnError: If the column is not numeric nor present.
        """
        available_columns = self.__data_repository.common_columns(data_source_ids)

        if (column_name, VariableType.CATEGORICAL) in available_columns:
            raise VariableNotNumericError(column_name, "Categorical")

        if (column_name, VariableType.NUMERICAL) not in available_columns:
            raise MissingColumnError(column_name)

    def validate_metric(
        self, name: str, query: str, data_source_ids: list[DataSourceID]
    ) -> Metric:
        """Validate and build a user-defined metric without storing it.

        Args:
            name: The metric name.
            query: The metric expression.
            data_source_ids: The data sources the metric applies to.

        Returns:
            A validated Metric model.

        Raises:
            ValueError: If the expression fails to execute.
            SampleDataNotLoadedError: If no valid data sources are loaded.
        """
        key = (query, tuple(sorted(data_source_ids)))

        if key in self.__verified_metrics:
            self.logger.debug(
                "Returning cached validated metric for query: '%s'", query
            )
            return self.__verified_metrics[key].duplicate(name=name)

        if not self.__data_repository.has_valid_sources:
            raise SampleDataNotLoadedError()

        new_metric = Metric(
            name=name,
            query=query,
            data_source_ids=data_source_ids,
            is_cumulative=False,
        )

        all_columns = self.__data_repository.common_columns(data_source_ids)
        all_column_names = [col for col, _ in all_columns]
        new_metric.validate_query(available_columns=all_column_names)

        # Execution check
        if new_metric.metric_expr is not None:
            try:
                lf = self.__data_repository.get_lazyframe(
                    data_source_ids, limit_per_source=10
                )
                total_size = lf.select(pl.len()).collect().item(0, 0)
                lf = lf.with_columns(pl.lit(total_size).alias("__TOTAL_SIZE__"))
                lf.select(new_metric.metric_expr).collect()
            except (KeyError, ValueError, TypeError) as e:
                raise ValueError(f"Failed to execute metric expression: {e}")

        self.__verified_metrics[key] = new_metric
        return new_metric

    def create_metric(
        self,
        name: str,
        query: str,
        is_cumulative: bool,
        use_thousand_sep: bool,
        is_percentage: bool,
        decimal_places: int,
        data_source_ids: list[DataSourceID],
    ) -> None:
        """Create and store a new user-defined metric.

        The stored metric's identity is derived from its content, so two
        identical metrics cannot coexist.

        Args:
            name: The metric name.
            query: The metric expression.
            is_cumulative: Whether the metric is cumulative.
            use_thousand_sep: Whether to format with thousand separators.
            is_percentage: Whether to format as a percentage.
            decimal_places: Number of decimal places for formatting.
            data_source_ids: The data sources the metric applies to.

        Raises:
            ValueError: If an identical metric already exists.
        """
        self.logger.info(
            "Creating user-defined metric '%s' with query '%s'", name, query
        )
        validated = self.validate_metric(name, query, data_source_ids)
        new_metric = validated.with_updates(
            is_cumulative=is_cumulative,
            use_thousand_sep=use_thousand_sep,
            is_percentage=is_percentage,
            decimal_places=decimal_places,
        )

        if new_metric.uid in self.metrics:
            raise ValueError(f"Metric '{name}' already exists.")

        self.metrics[new_metric.uid] = new_metric
        self.notify_subscribers()

    def modify_metric(
        self,
        metric_id: MetricID,
        name: str,
        query: str,
        is_cumulative: bool,
        use_thousand_sep: bool,
        is_percentage: bool,
        decimal_places: int,
        data_source_ids: list[DataSourceID],
    ) -> None:
        """Replace an existing user-defined metric with a new configuration.

        The modified metric re-derives its content-addressed ID; when it
        changes, the repository republishes an old-to-new MetricID remap so
        stale references held by subscribers can be rewritten.

        Args:
            metric_id: The ID of the metric to modify.
            name: The new metric name.
            query: The new metric expression.
            is_cumulative: Whether the metric is cumulative.
            use_thousand_sep: Whether to format with thousand separators.
            is_percentage: Whether to format as a percentage.
            decimal_places: Number of decimal places for formatting.
            data_source_ids: The data sources the metric applies to.

        Raises:
            ValueError: If the metric ID does not exist or the new content
                collides with another existing metric.
        """
        if metric_id not in self.metrics:
            raise ValueError(f"Metric '{metric_id}' not found.")

        self.logger.info("Modifying metric ID %s to name='%s'", metric_id, name)
        validated = self.validate_metric(name, query, data_source_ids)
        modified_metric = validated.with_updates(
            is_cumulative=is_cumulative,
            use_thousand_sep=use_thousand_sep,
            is_percentage=is_percentage,
            decimal_places=decimal_places,
        )

        old_id = metric_id
        new_id = modified_metric.uid
        if new_id != old_id and new_id in self.metrics:
            raise ValueError(f"Metric '{name}' already exists.")

        # Store the new metric, preserving its position in the ordering
        self._replace_metric(old_id, modified_metric)

        # Notify subscribers, publishing the identity remap if the content
        # change produced a new ID so stale references are rewritten.
        if new_id != old_id:
            self.logger.info("Metric changed: ID remapped %s -> %s", old_id, new_id)
            self.notify_subscribers(remaps={MetricID: {old_id: new_id}})
        else:
            self.notify_subscribers()

    def remove_metric(self, metric_id: MetricID) -> None:
        """Delete a user-defined metric.

        Args:
            metric_id: The ID of the metric to remove.
        """
        self.logger.warning("Removing metric ID %s", metric_id)
        if metric_id in self.metrics:
            del self.metrics[metric_id]
            self._stash_removal(metric_id)
        self.notify_subscribers()

    def duplicate_metric(self, metric_id: MetricID) -> None:
        """Create a copy of a user-defined metric with a unique name.

        The copy's unique name yields a distinct content-derived ID; no
        remap is published since nothing referenced the new ID beforehand.

        Args:
            metric_id: The ID of the metric to duplicate.
        """
        self.logger.info("Duplicating metric ID %s", metric_id)
        if metric_id not in self.metrics:
            return
        metric_name = self.metrics[metric_id].name
        existing_names = {m.name for m in self.metrics.values()}
        new_name = create_duplicate_name(metric_name, existing_names)

        metric_obj = self.metrics[metric_id].duplicate(name=new_name)

        if metric_obj.uid in self.metrics:
            raise ValueError(f"Metric '{new_name}' already exists.")

        self.metrics[metric_obj.uid] = metric_obj
        self.notify_subscribers()

    def to_dict(self):
        """Serialize MetricRepository state to MetricRepositoryJSON Pydantic model."""

        return MetricRepositoryJSON(
            metrics={m.uid: m.to_dict() for m in self.metrics.values()},
        )

    @classmethod
    def from_dict(
        cls,
        data: MetricRepositoryJSON,
        data_repository: DataRepository,
        errors: t.Literal["ignore", "raise"],
    ):
        """Reconstruct MetricRepository from MetricRepositoryJSON Pydantic model or dict."""
        repo = cls(data_repository=data_repository)
        invalid_metrics: list[tuple[Metric, Exception]] = []

        for metric_json in data.metrics.values():
            metric_obj = Metric.from_dict(metric_json)
            try:
                if data_repository.has_valid_sources:
                    all_columns = data_repository.common_columns(
                        metric_obj.data_source_ids
                    )
                    all_column_names = [col for col, _ in all_columns]
                    if all_column_names:
                        metric_obj.validate_query(all_column_names)
            except ValueError as error:
                if errors == "raise":
                    invalid_metrics.append((metric_obj, error))

                continue

            repo.metrics[metric_obj.uid] = metric_obj

        return repo, invalid_metrics

    @classmethod
    def validate_json(cls, data_repository: DataRepository, data: MetricRepositoryJSON):
        """Return variables referenced in the JSON that are missing from the data schema."""

        invalid_metrics: dict[MetricID, MetricJSON] = {}

        for metric_json in data.metrics.values():
            available_columns = {
                col
                for col, _ in data_repository.common_columns(
                    metric_json.data_source_ids
                )
            }
            if set(metric_json.used_columns) - available_columns:
                invalid_metrics[metric_json.uid] = metric_json

        return invalid_metrics
