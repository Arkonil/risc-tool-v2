"""Group models for numerical and categorical iteration splits.

This module defines the GroupBase protocol and its concrete numerical and
categorical implementations, along with helpers to rebuild typed group
dictionaries safely.
"""

import math
import typing as t
from abc import abstractmethod
from collections import OrderedDict

import polars as pl
from pydantic import BaseModel, Field, field_validator

from risc_tool.data.models.object_id import GroupID

TGroup = t.TypeVar("TGroup", bound="GroupBase")


class SupportsGroups(t.Protocol[TGroup]):
    """Protocol for iteration models that own typed groups/default_groups.

    Attributes:
        groups: Mapping of GroupID to group models.
    """

    groups: OrderedDict[GroupID, TGroup]

    def set_default_groups(self, groups: OrderedDict[GroupID, TGroup]) -> None:
        """Set the default groups on the iteration model.

        Args:
            groups: The ordered mapping of GroupID to group models to store
                as the iteration's default groups.
        """
        ...


def rebuild_group_dict[TTargetGroup: "GroupBase"](
    items: t.Iterable[tuple[GroupID, "GroupBase"]],
    group_cls: type[TTargetGroup],
) -> OrderedDict[GroupID, TTargetGroup]:
    """Rebuild group dict with a concrete group class for static typing safety."""
    rebuilt = OrderedDict[GroupID, TTargetGroup]()

    for gid, group in items:
        if isinstance(group, group_cls):
            rebuilt[gid] = group.model_copy(deep=True)
        else:
            rebuilt[gid] = group_cls.model_validate(group.model_dump())

    return rebuilt


class GroupBase(BaseModel, frozen=True):
    """Base Pydantic model for a single group, either numerical or categorical.

    Attributes:
        lower_bound: Lower bound for numerical groups.
        upper_bound: Upper bound for numerical groups.
        categories: Category set for categorical groups.
    """

    @abstractmethod
    def is_valid(self) -> bool:
        """Check whether the group definition is valid.

        Returns:
            True if the group is valid, False otherwise.
        """
        raise NotImplementedError()

    @abstractmethod
    def predicate(self, variable_name: str) -> pl.Expr:
        """Return a Polars expression selecting rows in this group.

        Args:
            variable_name: The column name the group applies to.

        Returns:
            A Polars boolean expression.
        """
        raise NotImplementedError()

    @abstractmethod
    def sas_code_template(self, variable_name: str) -> str:
        """Return a SAS code template for this group, using the variable name.

        Args:
            variable_name: The SAS variable name to reference.

        Returns:
            A SAS conditional expression string.
        """
        raise NotImplementedError()


class NumericalGroup(GroupBase, frozen=True):
    """Single numerical group defined by lower and upper numeric bounds."""

    lower_bound: float = float("-inf")
    upper_bound: float = float("inf")

    @field_validator("lower_bound", mode="before")
    @classmethod
    def parse_nan_or_none_lower(cls, v: object) -> float:
        """Coerce None or NaN lower bounds to negative infinity.

        Args:
            v: The raw value to coerce.

        Returns:
            A float lower bound.

        Raises:
            TypeError: If the value cannot be coerced to a float.
        """
        if v is None:
            return float("-inf")
        if isinstance(v, (int, float, str)) and not isinstance(v, bool):
            if isinstance(v, float) and math.isnan(v):
                return float("-inf")
            return float(v)
        raise TypeError(f"Expected numeric value or None, got {type(v).__name__}")

    @field_validator("upper_bound", mode="before")
    @classmethod
    def parse_nan_or_none_upper(cls, v: object) -> float:
        """Coerce None or NaN upper bounds to positive infinity.

        Args:
            v: The raw value to coerce.

        Returns:
            A float upper bound.

        Raises:
            TypeError: If the value cannot be coerced to a float.
        """
        if v is None:
            return float("inf")
        if isinstance(v, (int, float, str)) and not isinstance(v, bool):
            if isinstance(v, float) and math.isnan(v):
                return float("inf")
            return float(v)
        raise TypeError(f"Expected numeric value or None, got {type(v).__name__}")

    def is_valid(self) -> bool:
        """Check if bounds are present and lower < upper."""
        if self.lower_bound is None or self.upper_bound is None:
            return False
        return self.lower_bound < self.upper_bound

    def predicate(self, variable_name: str) -> pl.Expr:
        """Return a Polars expression for this group's bounds."""
        return pl.col(variable_name).is_between(
            self.lower_bound, self.upper_bound, closed="right"
        )

    def sas_code_template(self, variable_name: str) -> str:
        """Return a SAS code template for this group's bounds.

        Args:
            variable_name: The SAS variable name to reference.

        Returns:
            A SAS conditional expression string.
        """
        return f"({self.lower_bound} < {variable_name} <= {self.upper_bound})"


class CategoricalGroup(GroupBase, frozen=True):
    """Single categorical group defined by a set of category strings."""

    categories: set[str] = Field(default_factory=set)

    @field_validator("categories", mode="before")
    @classmethod
    def parse_categories(cls, v: object) -> set[str]:
        """Coerce list/tuple/set input into a set of strings.

        Args:
            v: The raw categories value.

        Returns:
            A set of string categories (empty set if input is not a collection).
        """
        if isinstance(v, (list, tuple, set)):
            return {str(item) for item in t.cast(t.Iterable[object], v)}
        return set()

    def is_valid(self) -> bool:
        """Check if group contains at least one category."""
        return len(self.categories) > 0

    def predicate(self, variable_name: str) -> pl.Expr:
        """Return a Polars expression for this group's categories."""
        return pl.col(variable_name).is_in(self.categories)

    def sas_code_template(self, variable_name: str) -> str:
        """Return a SAS code template for this group's categories.

        Args:
            variable_name: The SAS variable name to reference.

        Returns:
            A SAS conditional expression string.
        """
        categories_str = ", ".join(f'"{cat}"' for cat in sorted(self.categories))
        return f"({variable_name} in ({categories_str}))"
