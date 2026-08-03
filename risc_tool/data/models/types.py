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


class IterationID(SentinelInt):
    """Sentinel integer type for iteration identifiers.

    Attributes:
        INVALID: Sentinel value (-1) representing an invalid/missing iteration.
    """

    INVALID: "IterationID"

    @classmethod
    def validate_sentinel(cls, v: int) -> "IterationID":
        """Validate and convert an integer to an IterationID, handling sentinels.

        Args:
            v: The integer value to validate.

        Returns:
            The INVALID sentinel or a new IterationID instance.
        """
        if v == int(cls.INVALID):
            return cls.INVALID

        return super().validate_sentinel(v)


IterationID.INVALID = IterationID(-1, name="INVALID")


class RiskSegmentID(SentinelInt):
    """Sentinel integer type for risk segment identifiers.

    Attributes:
        INVALID: Sentinel value (-1) representing an invalid/missing segment.
    """

    INVALID: "RiskSegmentID"

    @classmethod
    def validate_sentinel(cls, v: int) -> "RiskSegmentID":
        """Validate and convert an integer to a RiskSegmentID, handling sentinels.

        Args:
            v: The integer value to validate.

        Returns:
            The INVALID sentinel or a new RiskSegmentID instance.
        """
        if v == int(cls.INVALID):
            return cls.INVALID

        return super().validate_sentinel(v)


RiskSegmentID.INVALID = RiskSegmentID(-1, name="INVALID")


class GroupID(SentinelInt):
    """Sentinel integer type for iteration group identifiers.

    Attributes:
        INVALID: Sentinel value (-1) representing an invalid/missing group.
    """

    INVALID: "GroupID"

    @classmethod
    def validate_sentinel(cls, v: int) -> "GroupID":
        """Validate and convert an integer to a GroupID, handling sentinels.

        Args:
            v: The integer value to validate.

        Returns:
            The INVALID sentinel or a new GroupID instance.
        """
        if v == int(cls.INVALID):
            return cls.INVALID

        return super().validate_sentinel(v)


GroupID.INVALID = GroupID(-1, name="INVALID")


DataSourceType = typing.Literal["dev", "tst"]
ColumnUsage = typing.Literal["unt_bad", "dlr_bad", "avg_bal"]

IterationView = typing.Literal["graph", "view", "create"]
ColorTheme = typing.Literal["light", "dark"]


class GridMetricSummary(typing.TypedDict):
    """Typed dictionary describing the summarized metric grid for an iteration.

    Attributes:
        metric_grid: The computed metric grid data structure.
        metric_name: Display name of the metric.
        data_source_names: Names of the data sources used for the grid.
    """

    metric_grid: typing.Any
    metric_name: str
    data_source_names: list[str]


class GridMetricView(typing.TypedDict):
    """Typed dictionary describing the styled metric grid view for an iteration.

    Attributes:
        metric_styler: The pandas Styler used to render the grid.
        metric_name: Display name of the metric.
        data_source_names: Names of the data sources used for the grid.
    """

    metric_styler: typing.Any
    metric_name: str
    data_source_names: list[str]


class GridEditorViewComponents(typing.TypedDict):
    """Typed dictionary of components for rendering the editable grid widget.

    Attributes:
        styler: The pandas Styler for the grid table.
        lower_bound_pos: Column position of the lower bound column, if any.
        upper_bound_pos: Column position of the upper bound column, if any.
        categories_pos: Column position of the categories column, if any.
        risk_segment_grid_col_pos: Column positions of risk segment grid columns.
        grid_options: Available grid option labels.
        show_prev_iter_details: Whether to show previous iteration details.
    """

    styler: typing.Any
    lower_bound_pos: int | None
    upper_bound_pos: int | None
    categories_pos: int | None
    risk_segment_grid_col_pos: list[int]
    grid_options: list[str]
    show_prev_iter_details: bool


__all__ = [
    "Callback",
    "CallbackID",
    "ChangeID",
    "ChangeIDs",
    "ColorTheme",
    "ColumnUsage",
    "DataSourceID",
    "DataSourceType",
    "FilterID",
    "GridEditorViewComponents",
    "GridMetricSummary",
    "GridMetricView",
    "GroupID",
    "IterationID",
    "IterationView",
    "MetricID",
    "RiskSegmentID",
]
