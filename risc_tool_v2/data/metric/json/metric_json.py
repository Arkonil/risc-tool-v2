"""JSON serialization models for Metric."""

from pydantic import BaseModel, ConfigDict

from risc_tool_v2.data.core.uid import DataSourceID, MetricID


class MetricJSON(BaseModel):
    model_config = ConfigDict(serialize_by_alias=True, validate_by_alias=True)

    uid: MetricID
    name: str
    query: str
    data_source_ids: list[DataSourceID]
    used_columns: list[str] = []
    is_cumulative: bool = False
    use_thousand_sep: bool = True
    is_percentage: bool = False
    decimal_places: int = 2
    processed_query: str = ""
    placeholder_map: dict[str, str] = {}


class MetricRepositoryJSON(BaseModel):
    model_config = ConfigDict(serialize_by_alias=True, validate_by_alias=True)

    metrics: dict[MetricID, MetricJSON]


__all__ = ["MetricJSON", "MetricRepositoryJSON"]
