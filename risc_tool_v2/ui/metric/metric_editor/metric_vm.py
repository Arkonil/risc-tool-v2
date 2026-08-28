"""View model for the Metrics Editor page."""

import typing as t
from collections import OrderedDict

import polars as pl

from risc_tool_v2.data.core.changes import ChangeTracker
from risc_tool_v2.data.core.enums import Signature
from risc_tool_v2.data.core.exceptions import format_error
from risc_tool_v2.data.core.id_remap import Remaps, get_remap, remap_value
from risc_tool_v2.data.core.types import ChangeIDs
from risc_tool_v2.data.core.uid import DataSourceID, MetricID
from risc_tool_v2.data.core.utils.logging import get_logger
from risc_tool_v2.data.data_source.models.completion import Completion
from risc_tool_v2.data.data_source.repositories.data_repository import DataRepository
from risc_tool_v2.data.metric.models.metric import Metric
from risc_tool_v2.data.metric.repositories.metric_repository import MetricRepository

logger = get_logger(__name__)


class MetricViewModel(ChangeTracker):
    @property
    def signature(self) -> Signature:
        return Signature.METRIC_VIEW_MODEL

    def __init__(
        self, data_repository: DataRepository, metric_repository: MetricRepository
    ) -> None:
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
        current_uid = self.__metric_cache.uid
        if current_uid != MetricID.EMPTY and current_uid in (
            self.__metric_repository.metrics
        ):
            return

        self.__metric_cache = self.__empty_metric
        self.is_verified = False
        self.__errors = []

    def on_dependency_remap(self, remaps: Remaps) -> None:
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

        self.__metric_cache = repo_metric.duplicate()
        self.is_verified = True

    @property
    def __empty_metric(self) -> Metric:
        return Metric(
            uid=MetricID.EMPTY,
            name="",
            query="",
            data_source_ids=[],
            is_cumulative=False,
        )

    @property
    def mode(self) -> t.Literal["view", "edit"]:
        return self.__view_mode

    def set_mode(
        self, mode: t.Literal["view", "edit"], metric_id: MetricID = MetricID.EMPTY
    ) -> None:
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
        return self.__data_repository.has_valid_sources

    @property
    def metric_cache(self) -> Metric:
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
        if name is not None and name != self.__metric_cache.name:
            self.__metric_cache = self.__metric_cache.model_copy(update={"name": name})
            self.is_verified = False

        if query is not None and query != self.__metric_cache.query:
            self.__metric_cache = self.__metric_cache.model_copy(
                update={"query": query}
            )
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
            self.__metric_cache = self.__metric_cache.model_copy(update=updates)

    @property
    def all_data_source_ids(self) -> list[DataSourceID]:
        return [ds_id for ds_id in self.__data_repository.data_sources]

    @property
    def selected_data_source_ids(self) -> list[DataSourceID]:
        return self.__metric_cache.data_source_ids

    @selected_data_source_ids.setter
    def selected_data_source_ids(self, value: list[DataSourceID]) -> None:
        self.__metric_cache = self.__metric_cache.model_copy(
            update={"data_source_ids": value}
        )
        self.is_verified = False

    def get_data_source_label(self, data_source_id: DataSourceID) -> str:
        return self.__data_repository.data_sources[data_source_id].label

    def get_column_completions(self) -> list[Completion]:
        return self.__data_repository.get_completions_for_columns(
            self.selected_data_source_ids
        )

    def get_unique_values(self, column_name: str) -> list[str]:
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
        if not self.__errors:
            return ""

        messages: list[str] = []
        for error in self.__errors:
            messages.append(format_error(error))

        return "\n\n".join(messages)

    def save_metric(self) -> None:
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
        return self.__metric_repository.metrics

    def duplicate_metric(self, metric_id: MetricID) -> None:
        self.__metric_repository.duplicate_metric(metric_id)

    def remove_metric(self, metric_id: MetricID) -> None:
        self.__metric_repository.remove_metric(metric_id)


__all__ = ["MetricViewModel"]
