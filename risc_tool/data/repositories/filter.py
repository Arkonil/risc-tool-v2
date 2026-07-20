import typing as t

import polars as pl

from risc_tool.data.models.enums import (
    ComparisonOperation,
    PercentileOptions,
    Signature,
)
from risc_tool.data.models.exceptions import InvalidFilterError
from risc_tool.data.models.filter import Filter
from risc_tool.data.models.outlier import OutlierRule
from risc_tool.data.models.types import ChangeIDs, FilterID
from risc_tool.data.repositories.base import BaseRepository
from risc_tool.data.repositories.data import DataRepository
from risc_tool.utils.duplicate_name import create_duplicate_name


class FilterRepository(BaseRepository):
    """Repository for managing filters and outlier rules using Polars."""

    @property
    def signature(self) -> Signature:
        return Signature.FILTER_REPOSITORY

    def __init__(self, data_repository: DataRepository) -> None:
        super().__init__(dependencies=[data_repository])
        self.filters: dict[FilterID, Filter] = {}
        self.__verified_filters: dict[str, Filter] = {}
        self.__data_repository: DataRepository = data_repository

    def __update_user_defined_filters(self) -> None:
        """Update and recompile expressions when the schema or data repository changes."""
        if not self.__data_repository.has_valid_sources:
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
                    # Recalculate mode, threshold, and count
                    filter_obj.recalculate_thresholds(lf)
                else:
                    filter_obj.validate_query(available_columns=all_column_names)
            except InvalidFilterError:
                filter_ids_to_remove.append(filter_id)

        for filter_id in filter_ids_to_remove:
            del self.filters[filter_id]

    def __clear_cache(self) -> None:
        self.__verified_filters.clear()

    def on_dependency_update(self, change_ids: ChangeIDs) -> None:
        self.logger.info("DataRepository updated, updating filters")

        # Re-validate user-defined filters and outlier rules
        self.__update_user_defined_filters()

        # Clear verified filter cache since schema may have changed
        self.__clear_cache()

    def validate_filter(self, name: str, query: str) -> Filter:
        """Validate filter syntax and column presence, returning verified Filter."""
        if query in self.__verified_filters:
            return self.__verified_filters[query].duplicate(name=name)

        new_filter = Filter(uid=FilterID.TEMPORARY, name=name, query=query)
        all_columns = self.__data_repository.common_columns()
        all_column_names = [col for col, _ in all_columns]
        new_filter.validate_query(available_columns=all_column_names)

        # Execution check
        if new_filter.filter_expr is not None:
            try:
                self.__data_repository.get_lazyframe(limit_per_source=10).filter(
                    new_filter.filter_expr
                ).collect()
            except Exception as e:
                raise InvalidFilterError(
                    query, f"Filter expression is valid but failed execution check: {e}"
                )

        self.__verified_filters[query] = new_filter
        return new_filter

    def create_filter(self, name: str, query: str) -> None:
        self.logger.info("Creating new filter '%s'", name)
        new_filter = self.validate_filter(name, query)
        new_filter.uid = FilterID(self._get_new_id(current_ids=self.filters.keys()))
        self.filters[new_filter.uid] = new_filter
        self.notify_subscribers()

    def modify_filter(self, filter_id: FilterID, name: str, query: str) -> None:
        if filter_id not in self.filters:
            raise ValueError(f"Filter '{filter_id}' not found.")

        self.logger.info("Modifying filter ID %s to name='%s'", filter_id, name)
        modified_filter = self.validate_filter(name, query)
        modified_filter.uid = filter_id
        self.filters[filter_id] = modified_filter
        self.notify_subscribers()

    def remove_filter(self, filter_id: FilterID) -> None:
        self.logger.warning("Removing filter ID %s", filter_id)
        if filter_id in self.filters:
            del self.filters[filter_id]
        self.notify_subscribers()

    def duplicate_filter(self, filter_id: FilterID) -> None:
        self.logger.info("Duplicating filter ID %s", filter_id)
        filter_name = self.filters[filter_id].name
        existing_names = set(m.name for m in self.filters.values())
        new_name = create_duplicate_name(filter_name, existing_names)

        filter_obj = self.filters[filter_id].duplicate(
            uid=FilterID(self._get_new_id(current_ids=self.filters.keys())),
            name=new_name,
        )
        self.filters[filter_obj.uid] = filter_obj
        self.notify_subscribers()

    # Outliers
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
        """Validate outlier rule, calculating mode/quantile thresholds using Polars."""
        all_columns = self.__data_repository.common_columns()
        all_column_names = [col for col, _ in all_columns]

        if variable_name not in all_column_names:
            raise ValueError(f"Column '{variable_name}' is not found in the data.")

        # Outliers are only supported for numerical columns
        dtype = self.__data_repository.data_config.schema[variable_name]
        if not dtype.is_numeric():
            raise ValueError(
                f"Only numeric variables are supported for outliers. Column '{variable_name}' is of type {dtype}."
            )

        new_outlier = OutlierRule(
            uid=FilterID.TEMPORARY,
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
        new_outlier.uid = FilterID(self._get_new_id(current_ids=self.filters.keys()))
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
            raise ValueError(f"Filter '{filter_id}' not found.")

        self.logger.info("Modifying outlier rule ID %s", filter_id)
        modified_outlier = self.validate_outlier_rule(
            variable_name, comparison_op, comparison_base
        )
        modified_outlier.uid = filter_id
        self.filters[filter_id] = modified_outlier
        self.notify_subscribers()

    # Query Helper
    def get_combined_expression(
        self, filter_ids: t.Iterable[FilterID], remove_outliers: bool = False
    ) -> pl.Expr | None:
        """Combine all selected filter and outlier expressions into a single pl.Expr."""
        active_ids = list(filter_ids)
        if remove_outliers:
            active_ids.extend(self.outlier_rule_ids)

        if not active_ids:
            return None

        combined_expr: pl.Expr | None = None
        for fid in active_ids:
            if fid not in self.filters:
                continue
            f_obj = self.filters[fid]
            if f_obj.filter_expr is not None:
                if combined_expr is None:
                    combined_expr = f_obj.filter_expr
                else:
                    combined_expr = combined_expr & f_obj.filter_expr

        return combined_expr

    def get_filters(
        self, filter_ids: list[FilterID] | None = None, outliers: bool = False
    ) -> dict[FilterID, Filter]:
        """Retrieve filters dict, filtered optionally by ID list and/or outlier status."""
        outliers_list = self.outlier_rule_ids
        if filter_ids is None:
            filter_ids = list(self.filters.keys())

        return {
            fid: self.filters[fid]
            for fid in filter_ids
            if fid in self.filters and (fid in outliers_list) == outliers
        }


__all__ = ["FilterRepository"]
