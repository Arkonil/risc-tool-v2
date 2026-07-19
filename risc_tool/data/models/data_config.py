import typing as t

import polars as pl
from polars._typing import PolarsDataType

from risc_tool.data.models.data_source import DataSource
from risc_tool.data.models.types import DataSourceID

# INT_PROPERTIES defines (bit_width, is_signed) for integer types
INT_PROPERTIES: dict[type[pl.DataType], tuple[int, bool]] = {
    pl.Int8: (8, True),
    pl.Int16: (16, True),
    pl.Int32: (32, True),
    pl.Int64: (64, True),
    pl.UInt8: (8, False),
    pl.UInt16: (16, False),
    pl.UInt32: (32, False),
    pl.UInt64: (64, False),
}


def normalize_type(dtype: PolarsDataType) -> pl.DataType:
    """Normalize a Polars data type to its instance form.

    Args:
        dtype: A Polars data type (either a class like pl.Int64 or an instance like pl.Int64()).

    Returns:
        An instance of the Polars data type. For pl.Enum, returns pl.String().
    """
    if isinstance(dtype, type):
        if dtype == pl.Enum:
            return pl.String()
        return dtype()
    return dtype


def get_int_properties(dtype: PolarsDataType) -> tuple[int, bool]:
    """Get the bit width and signedness of an integer data type.

    Args:
        dtype: A Polars integer data type (class or instance).

    Returns:
        A tuple of (bit_width, is_signed).

    Raises:
        TypeError: If the dtype is not a supported integer type.
    """
    normalized_dtype = normalize_type(dtype)
    properties = INT_PROPERTIES.get(type(normalized_dtype))
    if properties is None:
        raise TypeError(f"Unsupported integer dtype: {normalized_dtype}")

    return properties


def resolve_broader_type(
    t1: PolarsDataType,
    t2: PolarsDataType,
) -> pl.DataType:
    """Resolve the broader (supertype) of two Polars data types.

    This function determines a common type that can represent values from both
    input types without loss of information where possible.

    Args:
        t1: First Polars data type.
        t2: Second Polars data type.

    Returns:
        A Polars data type that can accommodate both input types.
    """
    t1 = normalize_type(t1)
    t2 = normalize_type(t2)

    if t1 == t2:
        return t1

    if isinstance(t1, pl.Null):
        return t2
    if isinstance(t2, pl.Null):
        return t1

    if isinstance(t1, (pl.String, pl.Utf8)) or isinstance(t2, (pl.String, pl.Utf8)):
        return pl.String()

    # Boolean logic
    if isinstance(t1, pl.Boolean):
        if isinstance(t2, pl.Boolean):
            return pl.Boolean()
        if t2.is_numeric():
            return t2
        return pl.String()
    if isinstance(t2, pl.Boolean):
        if t1.is_numeric():
            return t1
        return pl.String()

    # Numeric logic
    if t1.is_numeric() and t2.is_numeric():
        if t1.is_integer() and t2.is_integer():
            w1, s1 = get_int_properties(t1)
            w2, s2 = get_int_properties(t2)
            if s1 == s2:
                return t1 if w1 >= w2 else t2

            # Different signedness
            t_signed, w_signed = (t1, w1) if s1 else (t2, w2)
            _, w_unsigned = (t2, w2) if s1 else (t1, w1)

            if w_signed > w_unsigned:
                return t_signed
            else:
                if w_unsigned == 8:
                    return pl.Int16()
                elif w_unsigned == 16:
                    return pl.Int32()
                elif w_unsigned == 32:
                    return pl.Int64()
                else:
                    return pl.Float64()

        if t1.is_float() and t2.is_float():
            return (
                pl.Float64()
                if (isinstance(t1, pl.Float64) or isinstance(t2, pl.Float64))
                else pl.Float32()
            )

        # One is float, one is integer
        tf = t1 if t1.is_float() else t2
        ti = t2 if t1.is_float() else t1

        if isinstance(tf, pl.Float64):
            return pl.Float64()

        # tf is Float32
        w, _ = get_int_properties(ti)
        if w <= 16:
            return pl.Float32()
        else:
            return pl.Float64()

    # Temporal logic
    if t1.is_temporal() and t2.is_temporal():
        if isinstance(t1, pl.Datetime) and isinstance(t2, pl.Datetime):
            u1 = t1.time_unit or "us"
            u2 = t2.time_unit or "us"
            max_unit = (
                "ns"
                if (u1 == "ns" or u2 == "ns")
                else ("us" if (u1 == "us" or u2 == "us") else "ms")
            )
            tz = t1.time_zone or t2.time_zone
            return pl.Datetime(time_unit=max_unit, time_zone=tz)

        if isinstance(t1, pl.Duration) and isinstance(t2, pl.Duration):
            u1 = t1.time_unit or "us"
            u2 = t2.time_unit or "us"
            max_unit = (
                "ns"
                if (u1 == "ns" or u2 == "ns")
                else ("us" if (u1 == "us" or u2 == "us") else "ms")
            )
            return pl.Duration(time_unit=max_unit)

        if (isinstance(t1, pl.Date) and isinstance(t2, pl.Datetime)) or (
            isinstance(t1, pl.Datetime) and isinstance(t2, pl.Date)
        ):
            dt = t1 if isinstance(t1, pl.Datetime) else t2
            return dt

        return pl.String()

    # Nested type logic (List, Array)
    is_list1 = isinstance(t1, (pl.List, pl.Array))
    is_list2 = isinstance(t2, (pl.List, pl.Array))
    if is_list1 and is_list2:
        return pl.List(resolve_broader_type(t1.inner, t2.inner))

    # Struct logic
    if isinstance(t1, pl.Struct) and isinstance(t2, pl.Struct):
        fields1: dict[str, PolarsDataType] = {f.name: f.dtype for f in t1.fields}
        fields2: dict[str, PolarsDataType] = {f.name: f.dtype for f in t2.fields}
        merged_fields: dict[str, pl.DataType] = {}
        for name in fields1:
            if name in fields2:
                merged_fields[name] = resolve_broader_type(fields1[name], fields2[name])
            else:
                merged_fields[name] = normalize_type(fields1[name])
        for name in fields2:
            if name not in merged_fields:
                merged_fields[name] = normalize_type(fields2[name])
        return pl.Struct([
            pl.Field(name, dtype) for name, dtype in merged_fields.items()
        ])

    # Categorical/Enum logic
    is_cat1 = isinstance(t1, (pl.Categorical, pl.Enum))
    is_cat2 = isinstance(t2, (pl.Categorical, pl.Enum))
    if is_cat1 and is_cat2:
        if isinstance(t1, pl.Enum) and isinstance(t2, pl.Enum):
            if t1.categories.equals(t2.categories):
                return t1
            return pl.String()
        return pl.Categorical()

    return pl.String()


class DataConfig:
    """Stores data schemas of data sources and computes the unified superset schema.

    This class manages per-source schemas and maintains a merged schema that
    represents the union of all valid data sources, with compatible types
    resolved to their broadest common type.

    Attributes:
        _schemas: Dictionary mapping data source IDs to their individual schemas.
        _schema: The unified superset schema computed from all valid sources.
    """

    def __init__(self) -> None:
        """Initialize an empty DataConfig with no stored schemas."""
        self._schemas: dict[DataSourceID, pl.Schema] = {}
        self._schema: pl.Schema = pl.Schema()

    @property
    def schemas(self) -> dict[DataSourceID, pl.Schema]:
        """Return the stored per-source schemas keyed by data source ID.

        Returns:
            A dictionary mapping DataSourceID to their Polars Schema.
        """
        return dict(self._schemas)

    @property
    def schema(self) -> pl.Schema:
        """Return the unified superset schema of all valid registered data sources.

        Returns:
            A Polars Schema representing the merged schema of all valid sources.
        """
        return self._schema

    def update_source(self, source: DataSource, rebuild: bool = True) -> None:
        """Refresh the stored schema for a single source.

        Args:
            source: The DataSource to update.
            rebuild: Whether to rebuild the merged schema after updating.
        """
        schema = self._read_source_schema(source)

        if schema is None:
            self._schemas.pop(source.uid, None)
        else:
            self._schemas[source.uid] = schema

        if rebuild:
            self._rebuild_schema()

    def remove_source(self, uid: DataSourceID) -> None:
        """Remove a single stored source schema and refresh the merged schema.

        Args:
            uid: The DataSourceID of the source to remove.
        """
        if uid in self._schemas:
            del self._schemas[uid]
            self._rebuild_schema()

    def _read_source_schema(self, source: DataSource) -> pl.Schema | None:
        """Read the schema from a data source if it is valid.

        Args:
            source: The DataSource to read the schema from.

        Returns:
            The Polars Schema if successful, None if the source is invalid
            or schema reading fails.
        """
        if not source.is_valid:
            return None

        try:
            return source.get_schema()
        except Exception:
            # If reading schema fails (e.g. file deleted or unreadable), ignore this source.
            return None

    def _rebuild_schema(self) -> None:
        """Rebuild the unified schema from all stored source schemas."""
        self._schema = self._merge_schemas(self._schemas.values())

    def _merge_schemas(self, schemas: t.Iterable[pl.Schema]) -> pl.Schema:
        """Merge multiple schemas into a single unified schema.

        For each column name present in any schema, the merged type is the
        broader type resolved by resolve_broader_type.

        Args:
            schemas: An iterable of Polars Schema objects to merge.

        Returns:
            A merged Polars Schema containing all columns with resolved types.
        """
        merged_fields: dict[str, pl.DataType] = {}

        for schema in schemas:
            for name, dtype in schema.items():
                if name in merged_fields:
                    merged_fields[name] = resolve_broader_type(
                        merged_fields[name], dtype
                    )
                else:
                    merged_fields[name] = normalize_type(dtype)
        return pl.Schema(merged_fields)
