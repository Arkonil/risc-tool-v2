"""Repository for managing user-defined metrics with change notification."""

import typing as t
from collections import OrderedDict

import polars as pl

from risc_tool_v2.data.core.changes import BaseRepository
from risc_tool_v2.data.core.enums import Signature, VariableType
from risc_tool_v2.data.core.exceptions import (
    MissingColumnError,
    SampleDataNotLoadedError,
    VariableNotNumericError,
)
from risc_tool_v2.data.core.id_remap import Remaps, get_remap, remap_list
from risc_tool_v2.data.core.types import ChangeIDs
from risc_tool_v2.data.core.uid import DataSourceID, MetricID
from risc_tool_v2.data.core.utils.duplicate_name import create_duplicate_name
from risc_tool_v2.data.data_source.repositories.data_repository import DataRepository
from risc_tool_v2.data.metric.json.metric_json import MetricJSON, MetricRepositoryJSON
from risc_tool_v2.data.metric.models.metric import Metric


class MetricRepository(BaseRepository):
    @property
    def signature(self) -> Signature:
        return Signature.METRIC_REPOSITORY

    def __init__(self, data_repository: DataRepository) -> None:
        super().__init__(dependencies=[data_repository])
        self.metrics: OrderedDict[MetricID, Metric] = OrderedDict()
        self.__verified_metrics: dict[tuple[str, tuple[DataSourceID, ...]], Metric] = {}
        self.__data_repository: DataRepository = data_repository

    def _replace_metric(self, old_id: MetricID, new_metric: Metric) -> None:
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
        self.__verified_metrics.clear()

    def on_dependency_remap(self, remaps: Remaps) -> None:
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
        self.logger.info("DataRepository updated, revalidating user-defined metrics")
        self._update_user_defined_metrics()
        self._clear_cache()

    def validate_metric_input_column(
        self, column_name: str, data_source_ids: list[DataSourceID]
    ):
        available_columns = self.__data_repository.common_columns(data_source_ids)

        if (column_name, VariableType.CATEGORICAL) in available_columns:
            raise VariableNotNumericError(column_name, "Categorical")

        if (column_name, VariableType.NUMERICAL) not in available_columns:
            raise MissingColumnError(column_name)

    def validate_metric(
        self, name: str, query: str, data_source_ids: list[DataSourceID]
    ) -> Metric:
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

        # Check for duplicate content (same query and data_source_ids)
        for existing_metric in self.metrics.values():
            if (
                existing_metric.query == query
                and existing_metric.data_source_ids == data_source_ids
            ):
                raise ValueError(
                    f"Metric with query '{query}' and same data sources already exists."
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

        self._replace_metric(old_id, modified_metric)

        if new_id != old_id:
            self.logger.info("Metric changed: ID remapped %s -> %s", old_id, new_id)
            self._stash_remap(old_id, new_id)

        self.notify_subscribers()

    def remove_metric(self, metric_id: MetricID) -> None:
        self.logger.warning("Removing metric ID %s", metric_id)
        if metric_id in self.metrics:
            del self.metrics[metric_id]
            self._stash_removal(metric_id)
        self.notify_subscribers()

    def duplicate_metric(self, metric_id: MetricID) -> None:
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


__all__ = ["MetricRepository"]
