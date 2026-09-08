"""Group models for numerical and categorical simulation splits.

This module defines GroupBase and its concrete numerical and categorical
implementations used to describe per-risk-segment bands.
"""

import math
import typing as t
from abc import abstractmethod

import polars as pl
from pydantic import BaseModel, ConfigDict, Field, field_validator

TTargetGroup = t.TypeVar("TTargetGroup", bound="GroupBase")


class GroupBase(BaseModel, frozen=True):
    """Base Pydantic model for a single group, either numerical or categorical.

    Attributes:
        lower_bound: Lower bound for numerical groups.
        upper_bound: Upper bound for numerical groups.
        categories: Category set for categorical groups.
    """

    model_config = ConfigDict(extra="forbid")

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

    model_config = ConfigDict(extra="forbid")

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

    model_config = ConfigDict(extra="forbid")

    categories: frozenset[str] = Field(default_factory=frozenset)

    @field_validator("categories", mode="before")
    @classmethod
    def parse_categories(cls, v: object) -> frozenset[str]:
        """Coerce list/tuple/set input into a frozenset of strings.

        Args:
            v: The raw categories value.

        Returns:
            A frozenset of string categories (empty if input is not a collection).
        """
        if isinstance(v, (list, tuple, set, frozenset)):
            return frozenset(str(item) for item in t.cast(t.Iterable[object], v))
        return frozenset()

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


__all__ = [
    "CategoricalGroup",
    "GroupBase",
    "NumericalGroup",
]
