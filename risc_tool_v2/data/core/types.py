"""Type definitions for the change tracking and data source identification system."""

import typing
from uuid import UUID

from risc_tool_v2.data.core.enums import Signature
from risc_tool_v2.data.core.id_remap import Remap, Remaps

ChangeID = tuple[Signature, UUID]
"""A unique identifier for a change event, combining the component signature and a UUID."""

ChangeIDs = set[ChangeID]
"""A set of change IDs representing a batch of changes."""

CallbackID = UUID
"""Unique identifier for a callback subscription."""

Callback = typing.Callable[[ChangeIDs, Remaps | None], bool]
"""Callback function type for change notifications.

Args:
    change_ids: A set of ChangeID tuples representing the changes.
    remaps: Optional identity remappings (``{id_class: {old_id: new_id}}``).

Returns:
    True if the callback handled the changes, False otherwise.
"""

__all__ = [
    "Callback",
    "CallbackID",
    "ChangeID",
    "ChangeIDs",
    "Remap",
    "Remaps",
]
