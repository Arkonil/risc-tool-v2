"""JSON serialization models for Filter and OutlierRule."""

from pydantic import BaseModel, ConfigDict

from risc_tool_v2.data.core.enums import ComparisonOperation, PercentileOptions
from risc_tool_v2.data.core.uid import FilterID


class FilterJSON(BaseModel):
    model_config = ConfigDict(serialize_by_alias=True, validate_by_alias=True)

    uid: FilterID
    name: str
    query: str
    used_columns: list[str]

    # Outlier specific fields
    is_outlier: bool = False
    variable_name: str | None = None
    comparison_op: ComparisonOperation | None = None
    comparison_base: PercentileOptions | float | None = None


class FilterRepositoryJSON(BaseModel):
    model_config = ConfigDict(serialize_by_alias=True, validate_by_alias=True)

    filters: dict[FilterID, FilterJSON]


__all__ = ["FilterJSON", "FilterRepositoryJSON"]
