"""Type definitions for the change tracking and data source identification system."""

import typing
from uuid import UUID

from risc_tool.data.models.enums import Signature
from risc_tool.data.models.sentinel_int import SentinelInt

ChangeID = tuple[Signature, UUID]
"""A unique identifier for a change event, combining the component signature and a UUID."""

ChangeIDs = set[ChangeID]
"""A set of change IDs representing a batch of changes."""

CallbackID = UUID
"""Unique identifier for a callback subscription."""

Callback = typing.Callable[[ChangeIDs], bool]
"""Callback function type for change notifications.

Args:
    change_ids: A set of ChangeID tuples representing the changes.

Returns:
    True if the callback handled the changes, False otherwise.
"""


class DataSourceID(SentinelInt):
    """Sentinel integer type for data source identifiers.

    Provides special sentinel values for temporary and empty data sources
    while behaving like a regular integer for normal IDs.
    """

    TEMPORARY: "DataSourceID"
    """Sentinel value (-1) representing a temporary/unsaved data source."""

    EMPTY: "DataSourceID"
    """Sentinel value (-2) representing an empty/placeholder data source."""

    @classmethod
    def validate_sentinel(cls, v: int) -> "DataSourceID":
        """Validate and convert an integer to a DataSourceID, handling sentinels.

        Args:
            v: The integer value to validate.

        Returns:
            The corresponding DataSourceID sentinel or a new DataSourceID instance.
        """
        if v == int(cls.TEMPORARY):
            return cls.TEMPORARY
        if v == int(cls.EMPTY):
            return cls.EMPTY

        return super().validate_sentinel(v)


DataSourceID.TEMPORARY = DataSourceID(-1, name="TEMPORARY")
DataSourceID.EMPTY = DataSourceID(-2, name="EMPTY")
