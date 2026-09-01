"""Generic old-to-new identity remapping for ID classes.

This module provides helpers for rewriting stored ID references when an
entity's identity changes (e.g. a content-addressed DataSourceID is
re-derived after an edit). The helpers are type-agnostic so they can be
reused for any ID class (DataSourceID, FilterID, MetricID, ...).

A ``Remap`` maps an old identity to its new identity for a single ID
class. A ``Remaps`` dictionary groups those mappings by ID class so a
single change notification can carry remappings for several ID types.
"""

import typing as t

from risc_tool.data.models.uid import BaseUID

type Remap = dict[BaseUID, BaseUID]
"""Mapping of ``{old_id: new_id}`` for a single ID class.

Values are ``BaseUID`` instances; the specific subclass (e.g. ``DataSourceID``)
is determined by the key in the enclosing ``Remaps`` dictionary.
"""

type Remaps = dict[type[BaseUID], Remap]
"""Heterogeneous mapping of ``{id_class: {old_id: new_id}}`` for a batch of changes.

Contains remaps for multiple ID classes simultaneously, e.g.
``{DataSourceID: {DataSourceID(1): DataSourceID(2)}, FilterID: {...}}``.
"""


def get_remap[R: BaseUID](remaps: Remaps, id_class: type[R]) -> dict[R, R] | None:
    """Extract the typed remap for a specific ID class from a heterogeneous batch.

    Args:
        remaps: The heterogeneous remaps dictionary.
        id_class: The ID class to extract (e.g. ``DataSourceID``).

    Returns:
        A homogeneous ``dict[R, R]`` if present, otherwise ``None``.
    """
    remap = remaps.get(id_class)

    if remap is None:
        return None

    return t.cast(dict[R, R], remap)


def remap_value[R: BaseUID](remap: dict[R, R], value: R) -> R:
    """Return ``value`` rewritten to its new identity if remapped.

    Args:
        remap: The old-to-new identity mapping to apply.
        value: The value to rewrite.

    Returns:
        The new identity if ``value`` is a key in ``remap``, otherwise ``value``.
    """
    return remap.get(value, value)


def remap_list[R: BaseUID](remap: dict[R, R], values: t.Sequence[R]) -> list[R]:
    """Return a new list with each element rewritten via ``remap_value``.

    Args:
        remap: The old-to-new identity mapping to apply.
        values: The sequence of values to rewrite.

    Returns:
        A new list containing the remapped values.
    """
    return [remap_value(remap, value) for value in values]


def remap_set[R: BaseUID](remap: dict[R, R], values: t.Iterable[R]) -> set[R]:
    """Return a new set with each element rewritten via ``remap_value``.

    Args:
        remap: The old-to-new identity mapping to apply.
        values: The iterable of values to rewrite.

    Returns:
        A new set containing the remapped values.
    """
    return {remap_value(remap, value) for value in values}


def remap_keys[R: BaseUID, V](
    remap: dict[R, R], mapping: t.Mapping[R, V]
) -> dict[R, V]:
    """Return a new dictionary with its keys rewritten via ``remap_value``.

    Args:
        remap: The old-to-new identity mapping to apply.
        mapping: The mapping whose keys should be rewritten.

    Returns:
        A new dictionary with the remapped keys (values unchanged).
    """
    return {remap_value(remap, key): value for key, value in mapping.items()}


__all__ = [
    "Remap",
    "Remaps",
    "get_remap",
    "remap_keys",
    "remap_list",
    "remap_set",
    "remap_value",
]
