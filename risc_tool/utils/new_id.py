"""Unique ID generation utilities.

This module provides a simple generator for unique integer IDs and a function
to generate new IDs that don't conflict with an existing collection.
"""

import typing as t


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
    gen: t.Generator[int, None, None], current_ids: t.Collection[int] | None = None
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

    while True:
        new_id_val = next(gen)
        if new_id_val not in current_ids:
            return new_id_val


__all__ = ["id_generator", "new_id"]
