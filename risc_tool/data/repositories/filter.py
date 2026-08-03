"""Repository for managing filters and outlier rules with change notification.

Provides CRUD operations for Filter and OutlierRule objects, validates
queries against the current data schema, and notifies subscribers of changes.
"""

import typing as t

import polars as pl

from risc_tool.data.models.enums import (
    ComparisonOperation,
    PercentileOptions,
    Signature,
)
from risc_tool.data.models.exceptions import InvalidFilterError
from risc_tool.data.models.filter import Filter
from risc_tool.data.models.json_models import FilterJSON, FilterRepositoryJSON
from risc_tool.data.models.outlier import OutlierRule
from risc_tool.data.models.types import ChangeIDs, FilterID
from risc_tool.data.repositories.base import BaseRepository
from risc_tool.data.repositories.data import DataRepository
from risc_tool.utils.duplicate_name import create_duplicate_name


class FilterRepository(BaseRepository):
    """Repository for managing filters and outlier rules using Polars.

    Provides methods for validating, creating, modifying, removing, and
    duplicating filters. Also manages outlier rules derived from data
    statistics. Automatically re-validates filters when the data schema
    changes via the dependency on DataRepository.

    Attributes:
        filters: Dictionary mapping FilterID to Filter objects.
    """

    @property
    def signature(self) -> Signature:
        """Get the component signature for change tracking.

        Returns:
            Signature.FILTER_REPOSITORY
        """
        return Signature.FILTER_REPOSITORY

    def __init__(self, data_repository: DataRepository) -> None:
        """Initialize the FilterRepository with a dependency on DataRepository.

        Args:
            data_repository: The DataRepository to use for schema lookups
                and lazyframe access.
        """
        super().__init__(dependencies=[data_repository])
        self.filters: dict[FilterID, Filter] = {}
        self.__verified_filters: dict[str, Filter] = {}
        self.__data_repository: DataRepository = data_repository

    def __update_user_defined_filters(self) -> None:
        """Update and recompile expressions when the schema or data repository changes."""
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
                    # Recalculate mode, threshold, and count
                    filter_obj.recalculate_thresholds(lf)
                else:
                    filter_obj.validate_query(available_columns=all_column_names)
            except InvalidFilterError:
                filter_ids_to_remove.append(filter_id)

        self.logger.info("Removed %d invalid filters", len(filter_ids_to_remove))
        for filter_id in filter_ids_to_remove:
            del self.filters[filter_id]

    def __clear_cache(self) -> None:
        """Clear the verified filter cache so filters are re-validated on next access."""
        self.__verified_filters.clear()

    def on_dependency_update(self, change_ids: ChangeIDs) -> None:
        """Handle dependency updates by re-validating filters and clearing cache.

        Args:
            change_ids: Set of change IDs from the dependency.
        """
        self.logger.info("DataRepository updated, updating filters")

        # Re-validate user-defined filters and outlier rules
        self.__update_user_defined_filters()

        # Clear verified filter cache since schema may have changed
        self.__clear_cache()

    def validate_filter(self, name: str, query: str) -> Filter:
        """Validate filter syntax and column presence, returning verified Filter."""
        if query in self.__verified_filters:
            self.logger.debug(
                "Returning cached validated filter for query: '%s'", query
            )
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

    def create_filter(self, name: str, query: str) -> None:
        """Validate and create a new filter, then notify subscribers.

        Args:
            name: Human-readable name for the filter.
            query: The filter expression string.
        """
        self.logger.info("Creating new filter '%s'", name)
        new_filter = self.validate_filter(name, query)
        new_filter.uid = FilterID(self._get_new_id(current_ids=self.filters.keys()))
        self.filters[new_filter.uid] = new_filter
        self.notify_subscribers()

    def modify_filter(self, filter_id: FilterID, name: str, query: str) -> None:
        """Modify an existing filter's name and/or query, then notify subscribers.

        Args:
            filter_id: The ID of the filter to modify.
            name: New human-readable name for the filter.
            query: New filter expression string.

        Raises:
            ValueError: If the filter_id is not found in the repository.
        """
        if filter_id not in self.filters:
            self.logger.warning(
                "Attempted to modify non-existent filter ID %s", filter_id
            )
            raise ValueError(f"Filter '{filter_id}' not found.")

        self.logger.info("Modifying filter ID %s to name='%s'", filter_id, name)
        modified_filter = self.validate_filter(name, query)
        modified_filter.uid = filter_id
        self.filters[filter_id] = modified_filter
        self.notify_subscribers()

    def remove_filter(self, filter_id: FilterID) -> None:
        """Remove a filter from the repository and notify subscribers.

        Args:
            filter_id: The ID of the filter to remove.
        """
        self.logger.warning("Removing filter ID %s", filter_id)
        if filter_id in self.filters:
            del self.filters[filter_id]
        self.notify_subscribers()

    def duplicate_filter(self, filter_id: FilterID) -> None:
        """Create a copy of a filter with a unique name and notify subscribers.

        Args:
            filter_id: The ID of the filter to duplicate.
        """
        self.logger.info("Duplicating filter ID %s", filter_id)
        if filter_id not in self.filters:
            self.logger.warning(
                "Attempted to duplicate non-existent filter ID %s", filter_id
            )
            return
        filter_name = self.filters[filter_id].name
        existing_names = {m.name for m in self.filters.values()}
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
        """Get the IDs of all OutlierRule instances in the repository.

        Returns:
            A list of FilterIDs belonging to OutlierRule objects.
        """
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
            self.logger.warning("Column '%s' not found for outlier rule", variable_name)
            raise ValueError(f"Column '{variable_name}' is not found in the data.")

        # Outliers are only supported for numerical columns
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
        """Create and store a new outlier rule.

        Args:
            variable_name: The column name the rule applies to.
            comparison_op: The comparison operator (>, >=, <, <=).
            comparison_base: The percentile option or fixed threshold value.
        """
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
        """Modify an existing outlier rule's parameters and notify subscribers.

        Args:
            filter_id: The ID of the outlier rule to modify.
            variable_name: The column name the rule applies to.
            comparison_op: The comparison operator (>, >=, <, <=).
            comparison_base: The percentile option or fixed threshold value.

        Raises:
            ValueError: If the filter_id is not found in the repository.
        """
        if filter_id not in self.filters:
            self.logger.warning(
                "Attempted to modify non-existent outlier rule ID %s", filter_id
            )
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
    ) -> pl.Expr:
        """Combine all selected filter and outlier expressions into a single pl.Expr.

        Optionally includes outlier rule expressions. All expressions are
        combined with logical AND.

        Args:
            filter_ids: Iterable of FilterIDs for the filters to include.
            remove_outliers: If True, also include all outlier rule expressions.

        Returns:
            A single Polars expression combining all selected filters with AND,
            or None if no filters are selected.
        """
        active_ids = list(filter_ids)
        if remove_outliers:
            active_ids.extend(self.outlier_rule_ids)

        if not active_ids:
            self.logger.debug("No active filters to combine; returning True expression")
            return pl.lit(True)  # No filters, so return a literal True expression

        combined_expr: pl.Expr = pl.lit(True)  # Start with a literal True expression
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
        """Retrieve filters dict, filtered optionally by ID list and/or outlier status.

        Args:
            filter_ids: Optional list of specific FilterIDs to retrieve.
                If None, all filters are considered.
            outliers: If False, outlier rules are excluded; if True, only
                outlier rules are returned.

        Returns:
            A dictionary mapping FilterID to Filter matching the criteria.
        """
        outliers_list = self.outlier_rule_ids
        if filter_ids is None:
            filter_ids = list(self.filters.keys())

        return {
            fid: self.filters[fid]
            for fid in filter_ids
            if fid in self.filters and (fid in outliers_list) == outliers
        }

    def to_dict(self) -> FilterRepositoryJSON:
        """Serialize FilterRepository state to FilterRepositoryJSON Pydantic model."""
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
        """Reconstruct FilterRepository from FilterRepositoryJSON Pydantic model or dict."""
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
        """Return variables referenced in the JSON that are missing from the data schema."""
        available_columns = {col for col, _ in data_repository.common_columns()}
        invalid_filters: dict[FilterID, FilterJSON] = {}

        for filter_json in data.filters.values():
            if set(filter_json.used_columns) - available_columns:
                invalid_filters[filter_json.uid] = filter_json

        return invalid_filters


__all__ = ["FilterRepository"]
