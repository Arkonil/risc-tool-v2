"""Write-once ordered dictionary implementation.

This module provides an OrderedDict variant that allows adding new keys but
forbids modifying existing values, deleting keys, or reordering. This is
useful for maintaining ordered collections of dependencies where the order
and immutability of entries are important.
"""

import typing as t
from collections import OrderedDict

from risc_tool.utils.logging import get_logger

logger = get_logger(__name__)

K = t.TypeVar("K")
V = t.TypeVar("V")


class WriteOnceOrderedDict(OrderedDict[K, V]):
    """An OrderedDict that allows adding new keys but forbids modifications.

    This class prevents:
    - Modifying existing values
    - Deleting keys (via del, pop, popitem, clear)
    - Reordering keys (via move_to_end)
    - Updating existing keys (via update)

    New keys can be added using __setitem__ or update with only new keys.
    """

    def __setitem__(self, key: K, value: V):
        """Set a value for a key, only if the key doesn't already exist.

        Args:
            key: The key to set.
            value: The value to associate with the key.

        Raises:
            ValueError: If the key already exists in the dictionary.
        """
        if key in self:
            logger.warning("Attempted to overwrite existing key '%s'", key)
            raise ValueError(f"Key '{key}' already exists. Modification is forbidden.")
        super().__setitem__(key, value)

    def __delitem__(self, key: K):
        """Prevent deletion of keys.

        Args:
            key: The key to delete.

        Raises:
            ValueError: Always raised as deletion is forbidden.
        """
        logger.warning("Attempted to delete key '%s' (forbidden)", key)
        raise ValueError("Deletion is forbidden.")

    # --- Blocking other mutation methods ---

    def pop(self, key: K, *args: t.Any, **kwargs: t.Any):
        """Prevent popping keys.

        Raises:
            ValueError: Always raised as deletion is forbidden.
        """
        logger.warning("Attempted to pop key '%s' (forbidden)", key)
        raise ValueError("Deletion (pop) is forbidden.")

    def popitem(self, last: bool = True):
        """Prevent popping items.

        Args:
            last: Ignored.

        Raises:
            ValueError: Always raised as deletion is forbidden.
        """
        logger.warning("Attempted to popitem (forbidden)")
        raise ValueError("Deletion (popitem) is forbidden.")

    def clear(self):
        """Prevent clearing the dictionary.

        Raises:
            ValueError: Always raised as deletion is forbidden.
        """
        logger.warning("Attempted to clear dictionary (forbidden)")
        raise ValueError("Deletion (clear) is forbidden.")

    def move_to_end(self, key: K, last: bool = True):
        """Prevent reordering keys.

        Args:
            key: The key to move.
            last: Ignored.

        Raises:
            ValueError: Always raised as reordering is forbidden.
        """
        logger.warning("Attempted to move_to_end key '%s' (forbidden)", key)
        raise ValueError("Reordering (move_to_end) is forbidden.")

    def update(self, *args: t.Any, **kwargs: t.Any):
        """Update the dictionary, only allowing new keys.

        Args:
            *args: A single dictionary or iterable of key-value pairs.
            **kwargs: Additional key-value pairs.

        Raises:
            ValueError: If any key already exists.
            TypeError: If more than one positional argument is provided.
        """
        # Check args (dictionary or iterable)
        if len(args) == 1:
            other = dict(args[0])
            for key in other:
                if key in self:
                    logger.warning(
                        "Attempted to update existing key '%s' (forbidden)", key
                    )
                    raise ValueError(f"Key '{key}' already exists. Update forbidden.")
        elif len(args) > 1:
            logger.warning("update expected at most 1 argument, got %d", len(args))
            raise TypeError(f"update expected at most 1 arguments, got {len(args)}")

        # Check kwargs
        for key in kwargs:
            if key in self:
                logger.warning(
                    "Attempted to update existing key '%s' via kwargs (forbidden)", key
                )
                raise ValueError(f"Key '{key}' already exists. Update forbidden.")

        super().update(*args, **kwargs)
