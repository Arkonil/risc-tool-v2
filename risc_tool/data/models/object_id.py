from risc_tool.data.models.sentinel_int import SentinelInt
from risc_tool.data.models.uid import DataSourceID

__all__ = [
    "DataSourceID",
    "FilterID",
    "GroupID",
    "IterationID",
    "MetricID",
    "MutableObjectID",
    "RiskSegmentID",
    "SimulationID",
]


class MutableObjectID(SentinelInt):
    pass


class FilterID(MutableObjectID):
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


class MetricID(MutableObjectID):
    """Sentinel integer type for metric identifiers.

    Provides sentinel values for temporary, empty, and default (built-in)
    metrics while behaving like a regular integer for normal IDs.

    Attributes:
        TEMPORARY: Sentinel value (-1) for a temporary/unsaved metric.
        DEV_VOLUME: Default development volume metric.
        DEV_UNT_BAD_RATE: Default development unit bad rate metric.
        DEV_DLR_BAD_RATE: Default development dollar bad rate metric.
        TST_VOLUME: Default test volume metric.
        TST_UNT_BAD_RATE: Default test unit bad rate metric.
        TST_DLR_BAD_RATE: Default test dollar bad rate metric.
        EMPTY: Sentinel value (-5) for an empty/placeholder metric.
    """

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
        """Validate and convert an integer to a MetricID, handling sentinels.

        Args:
            v: The integer value to validate.

        Returns:
            The corresponding MetricID sentinel or a new MetricID instance.
        """
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
        """Check if this metric ID refers to one of the built-in default metrics.

        Returns:
            True if the metric ID is one of the six default metrics
            (DEV_VOLUME, DEV_UNT_BAD_RATE, DEV_DLR_BAD_RATE, TST_VOLUME,
            TST_UNT_BAD_RATE, TST_DLR_BAD_RATE), False otherwise.
        """
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


class SimulationID(MutableObjectID):
    pass


class IterationID(MutableObjectID):
    pass


class RiskSegmentID(MutableObjectID):
    pass


class GroupID(MutableObjectID):
    pass


"""
SimulationConfigGenerator
SimulationConfig
SimulationOutput
"""
