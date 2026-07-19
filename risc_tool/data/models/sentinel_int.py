import typing as t

from pydantic import GetCoreSchemaHandler
from pydantic_core import core_schema


class SentinelInt(int):
    # 1. Declare the field here so Pylance knows it exists
    _name: str | None = None

    def __new__(cls, value: int = 0, name: str | None = None):
        # Create the int instance
        obj = super().__new__(cls, value)
        # Store the name directly on the object
        # If it has a name, we treat it as a sentinel
        obj._name = name
        return obj

    def __eq__(self, other: t.Any):
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

    def __ne__(self, other: t.Any):
        return not self == other

    def __repr__(self):
        # If it has a name, print the name
        name = getattr(self, "_name", None)
        if name:
            return f"<{name}>"
        return super().__repr__()

    def __hash__(self):
        # Allow these to be used in sets/dicts
        return super().__hash__()

    @classmethod
    def validate_sentinel(cls, v: int) -> t.Self:
        return cls(v)

    @classmethod
    def serialize_sentinel(cls, v: t.Self) -> int:
        return int(v)

    @classmethod
    def __get_pydantic_core_schema__(
        cls, source_type: t.Any, handler: GetCoreSchemaHandler
    ) -> core_schema.CoreSchema:
        """
        Defines how Pydantic validates and serializes this custom type.
        1. Validate: Input -> int -> Check Sentinels -> MetricID
        2. Serialize: MetricID -> int
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
