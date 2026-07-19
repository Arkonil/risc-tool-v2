import typing as t
from collections import OrderedDict

K = t.TypeVar("K")
V = t.TypeVar("V")


class WriteOnceOrderedDict(OrderedDict[K, V]):
    """
    An OrderedDict that allows adding new keys but forbids
    modifying existing values, deleting keys, or reordering.
    """

    def __setitem__(self, key: K, value: V):
        if key in self:
            raise ValueError(f"Key '{key}' already exists. Modification is forbidden.")
        super().__setitem__(key, value)

    def __delitem__(self, key: K):
        raise ValueError("Deletion is forbidden.")

    # --- Blocking other mutation methods ---

    def pop(self, key: K, *args: t.Any, **kwargs: t.Any):
        raise ValueError("Deletion (pop) is forbidden.")

    def popitem(self, last: bool = True):
        raise ValueError("Deletion (popitem) is forbidden.")

    def clear(self):
        raise ValueError("Deletion (clear) is forbidden.")

    def move_to_end(self, key: K, last: bool = True):
        raise ValueError("Reordering (move_to_end) is forbidden.")

    def update(self, *args: t.Any, **kwargs: t.Any):
        # Check args (dictionary or iterable)
        if len(args) == 1:
            other = dict(args[0])
            for key in other:
                if key in self:
                    raise ValueError(f"Key '{key}' already exists. Update forbidden.")
        elif len(args) > 1:
            raise TypeError(f"update expected at most 1 arguments, got {len(args)}")

        # Check kwargs
        for key in kwargs:
            if key in self:
                raise ValueError(f"Key '{key}' already exists. Update forbidden.")

        super().update(*args, **kwargs)
