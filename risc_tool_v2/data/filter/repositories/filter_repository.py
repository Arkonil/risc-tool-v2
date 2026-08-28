"""Repository for managing filters and outlier rules with change notification."""

import typing as t

import polars as pl

from risc_tool_v2.data.core.changes import BaseRepository
from risc_tool_v2.data.core.enums import (
    ComparisonOperation,
    PercentileOptions,
    Signature,
)
from risc_tool_v2.data.core.exceptions import InvalidFilterError
from risc_tool_v2.data.core.id_remap import Remaps, get_remap
from risc_tool_v2.data.core.types import ChangeIDs
from risc_tool_v2.data.core.uid import DataSourceID, FilterID
from risc_tool_v2.data.core.utils.duplicate_name import create_duplicate_name
from risc_tool_v2.data.data_source.repositories.data_repository import DataRepository
from risc_tool_v2.data.filter.json.filter_json import FilterJSON, FilterRepositoryJSON
from risc_tool_v2.data.filter.models.filter import Filter
from risc_tool_v2.data.filter.models.outlier import OutlierRule


class FilterRepository(BaseRepository):
    @property
    def signature(self) -> Signature:
        return Signature.FILTER_REPOSITORY

    def __init__(self, data_repository: DataRepository) -> None:
        super().__init__(dependencies=[data_repository])
        self.filters: dict[FilterID, Filter] = {}
        self.__verified_filters: dict[str, Filter] = {}
        self.__data_repository: DataRepository = data_repository

    def __update_user_defined_filters(self) -> None:
        if not self.__data_repository.has_valid_sources:
            self.logger.debug("Clearing all filters: no valid data sources")
            self.filters.clear()
            return

        all_columns = self.__data_repository.common_columns()
        all_column_names = [col for col, _ in all_columns]
        lf = self.__data_repository.get_lazyframe(limit_per_source=5)
        filter_ids_to_remove: list[FilterID] = []

        for filter_id, filter_obj in list(self.filters.items()):
            try:
                if isinstance(filter_obj, OutlierRule):
                    if filter_obj.variable_name not in all_column_names:
                        raise InvalidFilterError(
                            filter_obj.query,
                            f"Column '{filter_obj.variable_name}' was removed.",
                        )
                    filter_obj.recalculate_thresholds(lf)
                else:
                    filter_obj.validate_query(available_columns=all_column_names)
            except InvalidFilterError:
                filter_ids_to_remove.append(filter_id)

        self.logger.info("Removed %d invalid filters", len(filter_ids_to_remove))
        for filter_id in filter_ids_to_remove:
            del self.filters[filter_id]

    def __clear_cache(self) -> None:
        self.__verified_filters.clear()

    def on_dependency_remap(self, remaps: Remaps) -> None:
        filter_remap = get_remap(remaps, FilterID)
        if filter_remap:
            for old_id, new_id in filter_remap.items():
                self._stash_remap(old_id, new_id)

        remap = get_remap(remaps, DataSourceID)
        if remap:
            self.logger.debug(
                "Data source IDs remapped; filters reference columns by "
                "name and are unaffected: %s",
                remap,
            )

    def on_dependency_update(self, change_ids: ChangeIDs) -> None:
        self.logger.info("DataRepository updated, updating filters")
        self.__update_user_defined_filters()
        self.__clear_cache()

    def validate_filter(self, name: str, query: str) -> Filter:
        if query in self.__verified_filters:
            self.logger.debug(
                "Returning cached validated filter for query: '%s'", query
            )
            return self.__verified_filters[query].duplicate(name=name)

        new_filter = Filter(name=name, query=query)
        all_columns = self.__data_repository.common_columns()
        all_column_names = [col for col, _ in all_columns]
        new_filter.validate_query(available_columns=all_column_names)

        if new_filter.filter_expr is not None:
            try:
                self.__data_repository.get_lazyframe(limit_per_source=10).filter(
                    new_filter.filter_expr
                ).collect()
            except Exception as e:
                self.logger.warning(
                    "Filter execution check failed for '%s': %s",
                    query,
                    e,
                    exc_info=True,
                )
                raise InvalidFilterError(
                    query, f"Filter expression is valid but failed execution check: {e}"
                )

        self.__verified_filters[query] = new_filter
        return new_filter

    def _remove_filter(self, filter_id: FilterID) -> None:
        del self.filters[filter_id]

    def _replace_filter(self, old_id: FilterID, new_filter: Filter) -> None:
        new_id = new_filter.uid
        if new_id == old_id:
            self.filters[old_id] = new_filter
            return

        items = [
            (new_id, new_filter) if fid == old_id else (fid, f)
            for fid, f in self.filters.items()
        ]
        self.filters.clear()
        self.filters.update(items)

    def create_filter(self, name: str, query: str) -> None:
        self.logger.info("Creating new filter '%s'", name)
        new_filter = self.validate_filter(name, query)
        # Check for duplicate content (same query)
        for existing_filter in self.filters.values():
            if existing_filter.query == query:
                raise ValueError(f"Filter with query '{query}' already exists.")
        if new_filter.uid in self.filters:
            raise ValueError(f"Filter '{name}' already exists.")
        self.filters[new_filter.uid] = new_filter
        self.notify_subscribers()

    def modify_filter(self, filter_id: FilterID, name: str, query: str) -> None:
        if filter_id not in self.filters:
            self.logger.warning(
                "Attempted to modify non-existent filter ID %s", filter_id
            )
            raise ValueError(f"Filter '{filter_id}' not found.")

        self.logger.info("Modifying filter ID %s to name='%s'", filter_id, name)
        modified_filter = self.validate_filter(name, query)

        old_id = filter_id
        new_id = modified_filter.uid
        if new_id != old_id and new_id in self.filters:
            raise ValueError(f"Filter '{name}' already exists.")

        self._replace_filter(old_id, modified_filter)

        if new_id != old_id:
            self.logger.info(
                "Filter content changed: ID remapped %s -> %s", old_id, new_id
            )
            self._stash_remap(old_id, new_id)

        self.notify_subscribers()

    def remove_filter(self, filter_id: FilterID) -> None:
        self.logger.warning("Removing filter ID %s", filter_id)
        if filter_id in self.filters:
            self._remove_filter(filter_id)
        self.notify_subscribers()

    def duplicate_filter(self, filter_id: FilterID) -> None:
        self.logger.info("Duplicating filter ID %s", filter_id)
        if filter_id not in self.filters:
            self.logger.warning(
                "Attempted to duplicate non-existent filter ID %s", filter_id
            )
            return
        filter_name = self.filters[filter_id].name
        existing_names = {m.name for m in self.filters.values()}
        new_name = create_duplicate_name(filter_name, existing_names)

        filter_obj = self.filters[filter_id].duplicate(name=new_name)
        self.filters[filter_obj.uid] = filter_obj
        self.notify_subscribers()

    @property
    def outlier_rule_ids(self) -> list[FilterID]:
        return [
            filter_id
            for filter_id, filter_obj in self.filters.items()
            if isinstance(filter_obj, OutlierRule)
        ]

    def validate_outlier_rule(
        self,
        variable_name: str,
        comparison_op: ComparisonOperation,
        comparison_base: PercentileOptions | float,
    ) -> OutlierRule:
        all_columns = self.__data_repository.common_columns()
        all_column_names = [col for col, _ in all_columns]

        if variable_name not in all_column_names:
            self.logger.warning("Column '%s' not found for outlier rule", variable_name)
            raise ValueError(f"Column '{variable_name}' is not found in the data.")

        dtype = self.__data_repository.data_config.schema[variable_name]
        if not dtype.is_numeric():
            self.logger.warning(
                "Non-numeric column '%s' (type=%s) cannot be used for outlier rules",
                variable_name,
                dtype,
            )
            raise ValueError(
                f"Only numeric variables are supported for outliers. Column '{variable_name}' is of type {dtype}."
            )

        new_outlier = OutlierRule(
            variable_name=variable_name,
            comparison_op=comparison_op,
            comparison_base=comparison_base,
        )

        lf = self.__data_repository.get_lazyframe()
        new_outlier.recalculate_thresholds(lf)
        return new_outlier

    def create_outlier_rule(
        self,
        variable_name: str,
        comparison_op: ComparisonOperation,
        comparison_base: PercentileOptions | float,
    ) -> None:
        self.logger.info("Creating new outlier rule for '%s'", variable_name)
        new_outlier = self.validate_outlier_rule(
            variable_name, comparison_op, comparison_base
        )
        if new_outlier.uid in self.filters:
            raise ValueError(f"Outlier rule for '{variable_name}' already exists.")
        self.filters[new_outlier.uid] = new_outlier
        self.notify_subscribers()

    def modify_outlier_rule(
        self,
        filter_id: FilterID,
        variable_name: str,
        comparison_op: ComparisonOperation,
        comparison_base: PercentileOptions | float,
    ) -> None:
        if filter_id not in self.filters:
            self.logger.warning(
                "Attempted to modify non-existent outlier rule ID %s", filter_id
            )
            raise ValueError(f"Filter '{filter_id}' not found.")

        self.logger.info("Modifying outlier rule ID %s", filter_id)
        modified_outlier = self.validate_outlier_rule(
            variable_name, comparison_op, comparison_base
        )

        old_id = filter_id
        new_id = modified_outlier.uid
        if new_id != old_id and new_id in self.filters:
            raise ValueError(f"Outlier rule for '{variable_name}' already exists.")

        self._replace_filter(old_id, modified_outlier)

        if new_id != old_id:
            self.logger.info(
                "Outlier rule changed: ID remapped %s -> %s", old_id, new_id
            )
            self._stash_remap(old_id, new_id)

        self.notify_subscribers()

    def get_combined_expression(
        self, filter_ids: t.Iterable[FilterID], remove_outliers: bool = False
    ) -> pl.Expr:
        active_ids = list(filter_ids)
        if remove_outliers:
            active_ids.extend(self.outlier_rule_ids)

        if not active_ids:
            self.logger.debug("No active filters to combine; returning True expression")
            return pl.lit(True)

        combined_expr: pl.Expr = pl.lit(True)
        for fid in active_ids:
            if fid not in self.filters:
                continue
            f_obj = self.filters[fid]
            if f_obj.filter_expr is not None:
                combined_expr = combined_expr & f_obj.filter_expr

        return combined_expr

    def get_filters(
        self, filter_ids: list[FilterID] | None = None, outliers: bool = False
    ) -> dict[FilterID, Filter]:
        outliers_list = self.outlier_rule_ids
        if filter_ids is None:
            filter_ids = list(self.filters.keys())

        return {
            fid: self.filters[fid]
            for fid in filter_ids
            if fid in self.filters and (fid in outliers_list) == outliers
        }

    def to_dict(self) -> FilterRepositoryJSON:
        return FilterRepositoryJSON(
            filters={f.uid: f.to_dict() for f in self.filters.values()}
        )

    @classmethod
    def from_dict(
        cls,
        data: FilterRepositoryJSON,
        data_repository: DataRepository,
        errors: t.Literal["ignore", "raise"],
    ) -> tuple["FilterRepository", list[tuple[Filter, Exception]]]:
        repo = cls(data_repository=data_repository)
        invalid_filters: list[tuple[Filter, Exception]] = []

        common_cols = [c[0] for c in data_repository.common_columns()]

        for filter_json in data.filters.values():
            if filter_json.is_outlier:
                filter_obj = OutlierRule.from_dict(filter_json)
            else:
                filter_obj = Filter.from_dict(filter_json)

            try:
                filter_obj.validate_query(available_columns=common_cols)
            except InvalidFilterError as error:
                if errors == "raise":
                    invalid_filters.append((filter_obj, error))
                continue

            repo.filters[filter_obj.uid] = filter_obj

        return repo, invalid_filters

    @classmethod
    def validate_json(cls, data_repository: DataRepository, data: FilterRepositoryJSON):
        available_columns = {col for col, _ in data_repository.common_columns()}
        invalid_filters: dict[FilterID, FilterJSON] = {}

        for filter_json in data.filters.values():
            if set(filter_json.used_columns) - available_columns:
                invalid_filters[filter_json.uid] = filter_json

        return invalid_filters


__all__ = ["FilterRepository"]
