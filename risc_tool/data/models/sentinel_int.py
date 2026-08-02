"""Custom integer type that supports sentinel values with identity-based equality.

This module provides a SentinelInt class that extends Python's int to support
named sentinel values (like TEMPORARY, EMPTY) that compare by identity rather
than numeric value. This is useful for creating special marker values that
won't collide with regular integer IDs.
"""

import typing as t

from pydantic import GetCoreSchemaHandler
from pydantic_core import core_schema


class SentinelInt(int):
    """An integer subclass that supports named sentinel values.

    SentinelInt behaves like a regular integer but can be assigned a name.
    When a SentinelInt has a name (is a sentinel), equality comparison
    uses identity (same name) rather than numeric value. This allows creating
    special values like TEMPORARY = -1 that won't equal a regular -1.

    Attributes:
        _name: Optional name for the sentinel. If set, the instance is treated
            as a sentinel and uses identity-based equality.
    """

    # 1. Declare the field here so Pylance knows it exists
    _name: str | None = None

    def __new__(cls, value: int = 0, name: str | None = None):
        """Create a new SentinelInt instance.

        Args:
            value: The integer value.
            name: Optional name for the sentinel. If provided, this instance
                will use identity-based equality comparison.

        Returns:
            A new SentinelInt instance.
        """
        # Create the int instance
        obj = super().__new__(cls, value)
        # Store the name directly on the object
        # If it has a name, we treat it as a sentinel
        obj._name = name
        return obj

    def __eq__(self, other: object):
        """Compare two values with sentinel-aware equality.

        If either value is a sentinel (has a _name), comparison is done
        by identity (same name) rather than numeric value.

        Args:
            other: The value to compare against.

        Returns:
            True if equal (numeric equality for non-sentinels, name equality for sentinels).
        """
        # Check if 'self' is a sentinel by checking its _name attribute
        # getattr is safe and won't trigger recursion
        is_self_sentinel = getattr(self, "_name", None) is not None

        # Check if 'other' is a sentinel
        is_other_sentinel = getattr(other, "_name", None) is not None

        # If EITHER is a sentinel, we enforce Identity Comparison
        if is_self_sentinel or is_other_sentinel:
            # Returns True only if they are the exact same object in memory
            return getattr(self, "_name", None) == getattr(other, "_name", None)

        # Otherwise, perform standard integer comparison
        return super().__eq__(other)

    def __ne__(self, other: object):
        """Invert equality comparison."""
        return not self == other

    def __repr__(self):
        """Return a string representation.

        For sentinels, returns the name in angle brackets (e.g., <TEMPORARY>).
        For regular integers, returns the standard int representation.
        """
        # If it has a name, print the name
        name = getattr(self, "_name", None)
        if name:
            return f"<{name}>"
        return super().__repr__()

    def __hash__(self):
        """Allow use in sets and as dictionary keys."""
        return super().__hash__()

    @property
    def value(self) -> int:
        """Return the underlying integer value."""
        return int(self)

    @classmethod
    def validate_sentinel(cls, v: int) -> t.Self:
        """Validate a sentinel value during Pydantic validation.

        Args:
            v: The integer value to validate.

        Returns:
            A new SentinelInt instance with the given value.
        """
        return cls(v)

    @classmethod
    def serialize_sentinel(cls, v: t.Self) -> int:
        """Serialize a SentinelInt to an integer for JSON output.

        Args:
            v: The SentinelInt to serialize.

        Returns:
            The integer value.
        """
        return int(v)

    @classmethod
    def __get_pydantic_core_schema__(
        cls, source_type: t.Any, handler: GetCoreSchemaHandler
    ) -> core_schema.CoreSchema:
        """Define how Pydantic validates and serializes this custom type.

        The schema handles:
        1. Validation: Input -> int -> Check Sentinels -> SentinelInt
        2. Serialization: SentinelInt -> int

        Args:
            source_type: The type being validated.
            handler: Pydantic's schema handler.

        Returns:
            A Pydantic CoreSchema for this type.
        """
        # C. Construct the Schema
        return core_schema.no_info_after_validator_function(
            function=cls.validate_sentinel,
            # We start with int_schema, which handles parsing (e.g., "123" -> 123)
            schema=core_schema.int_schema(),
            serialization=core_schema.plain_serializer_function_ser_schema(
                cls.serialize_sentinel,
                return_schema=core_schema.int_schema(),  # Helps generate correct JSON Schema
                when_used="json",
            ),
        )


__all__ = ["SentinelInt"]
