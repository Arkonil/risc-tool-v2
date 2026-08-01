"""Pydantic model for iteration mapping and validation outputs."""

from pydantic import BaseModel, ConfigDict

from risc_tool.data.models.types import GroupID


class IterationOutput(BaseModel):
    """Encapsulates validation and mapping warnings/errors for an iteration."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    errors: list[str] = []
    warnings: list[str] = []
    invalid_groups: list[GroupID] = []


__all__ = ["IterationOutput"]
