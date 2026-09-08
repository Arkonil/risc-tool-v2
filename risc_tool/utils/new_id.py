"""Unique ID generation utilities.

This module provides a simple generator for unique integer IDs and a function
to generate new IDs that don't conflict with an existing collection.
"""

import typing as t
from uuid import UUID


def _normalize_existing_id(value: object) -> int | object:
    """Return a comparable integer for UUID-based ID objects.

    Legacy code and tests still reason about IDs as integer values even though the
    concrete ID classes now subclass :class:`uuid.UUID`. When a collection holds a
    UUID-valued ID, the integer representation is the real collision key.
    """
    if isinstance(value, UUID):
        return int(value)
    return value


def id_generator() -> t.Generator[int, None, None]:
    """A simple generator that yields unique integer IDs starting from 1.

    Yields:
        Incrementing integers starting from 1.
    """
    current_id = 1
    while True:
        yield current_id
        current_id += 1


def new_id(
    gen: t.Generator[int, None, None],
    current_ids: t.Iterable[int | UUID] | None = None,
) -> int:
    """Generate a new unique ID that is not in the current_ids collection.

    Args:
        gen: A generator that yields unique integer IDs.
        current_ids: An optional collection of IDs to avoid. If None, an empty
            set is used.

    Returns:
        A new unique integer ID not present in current_ids.
    """
    if current_ids is None:
        current_ids = set()

    normalized = {_normalize_existing_id(v) for v in current_ids}
    while True:
        new_id_val = next(gen)
        if new_id_val not in normalized:
            return new_id_val


__all__ = ["id_generator", "new_id"]
