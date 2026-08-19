"""Type definitions for the change tracking and data source identification system."""

import typing
from uuid import UUID

from risc_tool.data.models.enums import Signature

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
    "DataSourceType",
    "GridEditorViewComponents",
    "GridMetricSummary",
    "GridMetricView",
    "IterationView",
]
