"""JSON serialization models for DataRepository and DataExplorerViewModel."""

from typing import TYPE_CHECKING

from pydantic import BaseModel, ConfigDict

from risc_tool_v2.data.core.uid import DataSourceID, FilterID

if TYPE_CHECKING:
    from risc_tool_v2.data.data_source.models.data_source import DataSource
    from risc_tool_v2.data.data_source.repositories.data_repository import (
        DataRepository,
    )


class DataRepositoryJSON(BaseModel):
    model_config = ConfigDict(serialize_by_alias=True, validate_by_alias=True)

    data_sources: dict[DataSourceID, "DataSource"]

    @classmethod
    def from_repository(cls, repo: "DataRepository") -> "DataRepositoryJSON":
        return cls(data_sources={ds.uid: ds for ds in repo.data_sources.values()})

    def to_repository(self) -> "DataRepository":
        from risc_tool_v2.data.data_source.repositories.data_repository import (
            DataRepository,
        )

        repo = DataRepository()
        for ds in self.data_sources.values():
            repo.data_sources[ds.uid] = ds
        repo.data_config.update_schema(repo.data_sources.values())
        return repo


class DataExplorerViewModelJSON(BaseModel):
    model_config = ConfigDict(serialize_by_alias=True, validate_by_alias=True)

    iv_data_sources: list[DataSourceID]
    iv_current_target: str | None
    iv_current_variables: list[str]
    iv_current_filter_ids: list[FilterID]
    iv_remove_outliers: bool


__all__ = ["DataExplorerViewModelJSON", "DataRepositoryJSON"]
