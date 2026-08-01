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
    @property
    def signature(self) -> Signature:
        return Signature.VARIABLE_SELECTOR_VIEW_MODEL

    def __init__(
        self, data_repository: DataRepository, metric_repository: MetricRepository
    ):
        super().__init__(dependencies=[data_repository, metric_repository])

        self.__data_repository = data_repository
        self.__metric_repository = metric_repository

    def on_dependency_update(self, change_ids: ChangeIDs):
        pass

    @property
    def all_data_source_ids(self) -> list[DataSourceID]:
        return [ds_id for ds_id in self.__data_repository.data_sources]

    def get_data_source_label(self, data_source_id: DataSourceID):
        return self.__data_repository.data_sources[data_source_id].label

    def selected_data_source_ids(self, ds_type: DataSourceType) -> list[DataSourceID]:
        if ds_type == "dev":
            return self.__metric_repository.dev_data_source_ids
        elif ds_type == "tst":
            return self.__metric_repository.tst_data_source_ids
        else:
            raise ValueError(f"Invalid data source type: {ds_type}")

    def set_data_source_ids(self, ds_type: DataSourceType, value: list[DataSourceID]):
        if ds_type == "dev":
            self.__metric_repository.dev_data_source_ids = value
        elif ds_type == "tst":
            self.__metric_repository.tst_data_source_ids = value
        else:
            raise ValueError(f"Invalid data source type: {ds_type}")

    def get_available_columns(self, ds_type: DataSourceType) -> list[str | None]:
        if ds_type == "dev":
            ds_ids = self.__metric_repository.dev_data_source_ids
        elif ds_type == "tst":
            ds_ids = self.__metric_repository.tst_data_source_ids
        else:
            raise ValueError(f"Invalid data source type: {ds_type}")

        column_types = self.__data_repository.common_columns(ds_ids)
        return [None] + sorted(
            [
                c_name
                for (c_name, c_type) in column_types
                if c_type == VariableType.NUMERICAL
            ]
        )

    def get_variable(
        self,
        ds_type: DataSourceType,
        usage: ColumnUsage,
    ):
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
        if mob_type == "current":
            return self.__metric_repository.current_rate_mob
        elif mob_type == "lifetime":
            return self.__metric_repository.lifetime_rate_mob
        else:
            return None

    def set_mob(self, mob_type: t.Literal["current", "lifetime"], value: int):
        if mob_type == "current":
            self.__metric_repository.current_rate_mob = value
        elif mob_type == "lifetime":
            self.__metric_repository.lifetime_rate_mob = value


__all__ = ["VariableSelectorViewModel"]
