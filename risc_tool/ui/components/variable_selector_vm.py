"""View Model for the reusable variable selector components."""

import typing as t

from risc_tool.data.models.changes import ChangeTracker
from risc_tool.data.models.enums import Signature, VariableType
from risc_tool.data.models.types import (
    ChangeIDs,
    ColumnUsage,
    DataSourceID,
    DataSourceType,
)
from risc_tool.data.repositories.data import DataRepository
from risc_tool.data.repositories.metric import MetricRepository


class VariableSelectorViewModel(ChangeTracker):
    """View model bridging variable selector widgets to the metric repository."""

    @property
    def signature(self) -> Signature:
        """Get the component signature for change tracking.

        Returns:
            Signature.VARIABLE_SELECTOR_VIEW_MODEL
        """
        return Signature.VARIABLE_SELECTOR_VIEW_MODEL

    def __init__(
        self, data_repository: DataRepository, metric_repository: MetricRepository
    ):
        """Initialize the VariableSelectorViewModel.

        Args:
            data_repository: Repository for data sources and common columns.
            metric_repository: Repository for metric variable and MOB settings.
        """
        super().__init__(dependencies=[data_repository, metric_repository])

        self.__data_repository = data_repository
        self.__metric_repository = metric_repository

    def on_dependency_update(self, change_ids: ChangeIDs):
        """Handle changes in dependencies (no-op as widgets read fresh state)."""

    @property
    def all_data_source_ids(self) -> list[DataSourceID]:
        """All available data source IDs.

        Returns:
            A list of DataSourceIDs.
        """
        return [ds_id for ds_id in self.__data_repository.data_sources]

    def get_data_source_label(self, data_source_id: DataSourceID):
        """Get the label for a data source.

        Args:
            data_source_id: The ID of the data source.

        Returns:
            The data source label string.
        """
        return self.__data_repository.data_sources[data_source_id].label

    def selected_data_source_ids(self, ds_type: DataSourceType) -> list[DataSourceID]:
        """Get the currently selected data source IDs for a development/test type.

        Args:
            ds_type: Either "dev" or "tst".

        Returns:
            The selected DataSourceIDs.

        Raises:
            ValueError: If ds_type is not "dev" or "tst".
        """
        if ds_type == "dev":
            return self.__metric_repository.dev_data_source_ids
        elif ds_type == "tst":
            return self.__metric_repository.tst_data_source_ids
        else:
            raise ValueError(f"Invalid data source type: {ds_type}")

    def set_data_source_ids(self, ds_type: DataSourceType, value: list[DataSourceID]):
        """Set the selected data source IDs for a development/test type.

        Args:
            ds_type: Either "dev" or "tst".
            value: The new DataSourceIDs.

        Raises:
            ValueError: If ds_type is not "dev" or "tst".
        """
        if ds_type == "dev":
            self.__metric_repository.dev_data_source_ids = value
        elif ds_type == "tst":
            self.__metric_repository.tst_data_source_ids = value
        else:
            raise ValueError(f"Invalid data source type: {ds_type}")

    def get_available_columns(self, ds_type: DataSourceType) -> list[str | None]:
        """Get sortable numeric columns available to a development/test type.

        Args:
            ds_type: Either "dev" or "tst".

        Returns:
            A list with None first, then sorted numeric column names.

        Raises:
            ValueError: If ds_type is not "dev" or "tst".
        """
        if ds_type == "dev":
            ds_ids = self.__metric_repository.dev_data_source_ids
        elif ds_type == "tst":
            ds_ids = self.__metric_repository.tst_data_source_ids
        else:
            raise ValueError(f"Invalid data source type: {ds_type}")

        column_types = self.__data_repository.common_columns(ds_ids)
        return [None] + sorted([
            c_name
            for (c_name, c_type) in column_types
            if c_type == VariableType.NUMERICAL
        ])

    def get_variable(
        self,
        ds_type: DataSourceType,
        usage: ColumnUsage,
    ):
        """Get the variable name configured for a data source type and usage.

        Args:
            ds_type: Either "dev" or "tst".
            usage: The variable role (e.g. "unt_bad", "dlr_bad", "avg_bal").

        Returns:
            The configured variable name, or None.

        Raises:
            ValueError: For an unsupported (ds_type, usage) combination.
        """
        match (ds_type, usage):
            case ("dev", "unt_bad"):
                return self.__metric_repository.var_dev_unt_bad
            case ("dev", "dlr_bad"):
                return self.__metric_repository.var_dev_dlr_bad
            case ("dev", "avg_bal"):
                return self.__metric_repository.var_dev_avg_bal
            case ("tst", "unt_bad"):
                return self.__metric_repository.var_tst_unt_bad
            case ("tst", "dlr_bad"):
                return self.__metric_repository.var_tst_dlr_bad
            case ("tst", "avg_bal"):
                return self.__metric_repository.var_tst_avg_bal
            case _:
                raise ValueError(
                    f"Invalid data source type or usage: {ds_type}, {usage}"
                )

    def set_variable(
        self,
        ds_type: DataSourceType,
        usage: ColumnUsage,
        value: str | None,
    ):
        """Set the variable name for a data source type and usage.

        Args:
            ds_type: Either "dev" or "tst".
            usage: The variable role (e.g. "unt_bad", "dlr_bad", "avg_bal").
            value: The new variable name, or None to clear it.

        Raises:
            ValueError: For an unsupported (ds_type, usage) combination.
        """
        match (ds_type, usage):
            case ("dev", "unt_bad"):
                self.__metric_repository.var_dev_unt_bad = value
            case ("dev", "dlr_bad"):
                self.__metric_repository.var_dev_dlr_bad = value
            case ("dev", "avg_bal"):
                self.__metric_repository.var_dev_avg_bal = value
            case ("tst", "unt_bad"):
                self.__metric_repository.var_tst_unt_bad = value
            case ("tst", "dlr_bad"):
                self.__metric_repository.var_tst_dlr_bad = value
            case ("tst", "avg_bal"):
                self.__metric_repository.var_tst_avg_bal = value
            case _:
                raise ValueError(
                    f"Invalid data source type or usage: {ds_type}, {usage}"
                )

    def get_mob(self, mob_type: t.Literal["current", "lifetime"]):
        """Get the current or lifetime month-on-book value.

        Args:
            mob_type: Either "current" or "lifetime".

        Returns:
            The MOB integer, or None if mob_type is invalid.
        """
        if mob_type == "current":
            return self.__metric_repository.current_rate_mob
        elif mob_type == "lifetime":
            return self.__metric_repository.lifetime_rate_mob
        else:
            return None

    def set_mob(self, mob_type: t.Literal["current", "lifetime"], value: int):
        """Set the current or lifetime month-on-book value.

        Args:
            mob_type: Either "current" or "lifetime".
            value: The new MOB integer.
        """
        if mob_type == "current":
            self.__metric_repository.current_rate_mob = value
        elif mob_type == "lifetime":
            self.__metric_repository.lifetime_rate_mob = value


__all__ = ["VariableSelectorViewModel"]
