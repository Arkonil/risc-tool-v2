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


class FilterID(SentinelInt):
    """Sentinel integer type for filter identifiers.

    Provides special sentinel values for temporary and empty filters
    while behaving like a regular integer for normal IDs.
    """

    TEMPORARY: "FilterID"
    """Sentinel value (-1) representing a temporary/unsaved filter."""

    EMPTY: "FilterID"
    """Sentinel value (-2) representing an empty/placeholder filter."""

    @classmethod
    def validate_sentinel(cls, v: int) -> "FilterID":
        """Validate and convert an integer to a FilterID, handling sentinels.

        Args:
            v: The integer value to validate.

        Returns:
            The corresponding FilterID sentinel or a new FilterID instance.
        """
        if v == int(cls.TEMPORARY):
            return cls.TEMPORARY
        if v == int(cls.EMPTY):
            return cls.EMPTY

        return super().validate_sentinel(v)


FilterID.TEMPORARY = FilterID(-1, name="TEMPORARY")
FilterID.EMPTY = FilterID(-2, name="EMPTY")


class MetricID(SentinelInt):
    """Sentinel integer type for metric identifiers."""

    TEMPORARY: "MetricID"
    DEV_VOLUME: "MetricID"
    DEV_UNT_BAD_RATE: "MetricID"
    DEV_DLR_BAD_RATE: "MetricID"
    TST_VOLUME: "MetricID"
    TST_UNT_BAD_RATE: "MetricID"
    TST_DLR_BAD_RATE: "MetricID"
    EMPTY: "MetricID"

    @classmethod
    def validate_sentinel(cls, v: int) -> "MetricID":
        if v == int(cls.TEMPORARY):
            return cls.TEMPORARY
        if v == int(cls.DEV_VOLUME):
            return cls.DEV_VOLUME
        if v == int(cls.DEV_UNT_BAD_RATE):
            return cls.DEV_UNT_BAD_RATE
        if v == int(cls.DEV_DLR_BAD_RATE):
            return cls.DEV_DLR_BAD_RATE
        if v == int(cls.TST_VOLUME):
            return cls.TST_VOLUME
        if v == int(cls.TST_UNT_BAD_RATE):
            return cls.TST_UNT_BAD_RATE
        if v == int(cls.TST_DLR_BAD_RATE):
            return cls.TST_DLR_BAD_RATE
        if v == int(cls.EMPTY):
            return cls.EMPTY

        return super().validate_sentinel(v)

    @property
    def is_default(self) -> bool:
        return self in (
            MetricID.DEV_VOLUME,
            MetricID.DEV_UNT_BAD_RATE,
            MetricID.DEV_DLR_BAD_RATE,
            MetricID.TST_VOLUME,
            MetricID.TST_UNT_BAD_RATE,
            MetricID.TST_DLR_BAD_RATE,
        )


MetricID.TEMPORARY = MetricID(-1, name="TEMPORARY")
MetricID.DEV_VOLUME = MetricID(-2, name="DEV_VOLUME")
MetricID.DEV_UNT_BAD_RATE = MetricID(-3, name="DEV_UNT_BAD_RATE")
MetricID.DEV_DLR_BAD_RATE = MetricID(-4, name="DEV_DLR_BAD_RATE")
MetricID.TST_VOLUME = MetricID(-6, name="TST_VOLUME")
MetricID.TST_UNT_BAD_RATE = MetricID(-7, name="TST_UNT_BAD_RATE")
MetricID.TST_DLR_BAD_RATE = MetricID(-8, name="TST_DLR_BAD_RATE")
MetricID.EMPTY = MetricID(-5, name="EMPTY")


class IterationID(SentinelInt):
    """Sentinel integer type for iteration identifiers."""

    INVALID: "IterationID"

    @classmethod
    def validate_sentinel(cls, v: int) -> "IterationID":
        if v == int(cls.INVALID):
            return cls.INVALID

        return super().validate_sentinel(v)


IterationID.INVALID = IterationID(-1, name="INVALID")
