"""UUID-based identifier types with content-addressed identities.

This module provides ``BaseUID``, a :class:`uuid.UUID` subclass that is
recognized by pydantic for validation and JSON serialization, and
``DataSourceID``, a content-addressed identifier derived from a
:class:`~risc_tool_v2.data.data_source.models.data_source.DataSource`'s content.

Sentinels (``TEMPORARY``, ``EMPTY``, ``UNSET``) are value-encoded: they occupy
reserved UUID integer values that a content hash is astronomically unlikely to
produce. A parsed value that matches a reserved integer is returned as the
corresponding singleton sentinel.
"""

import numbers
import typing as t
from uuid import UUID

from pydantic import GetCoreSchemaHandler
from pydantic_core import core_schema

# Reserved integer values for the UUID-based sentinels. They occupy the top
# values in the 128-bit space so they won't collide with real UUIDv5 content
# hashes in practice.
_TEMPORARY_INT = 2**128 - 1
_EMPTY_INT = 2**128 - 2
_FILTER_TEMPORARY_INT = 2**128 - 3
_FILTER_EMPTY_INT = 2**128 - 4
_UNSET_INT = 2**128 - 5
_FILTER_UNSET_INT = 2**128 - 6
_METRIC_TEMPORARY_INT = 2**128 - 7
_METRIC_EMPTY_INT = 2**128 - 8
_METRIC_UNSET_INT = 2**128 - 9
_SIM_GEN_TEMPORARY_INT = 2**128 - 10
_SIM_GEN_EMPTY_INT = 2**128 - 11
_SIM_GEN_UNSET_INT = 2**128 - 12
_SIM_CFG_TEMPORARY_INT = 2**128 - 13
_SIM_CFG_EMPTY_INT = 2**128 - 14
_SIM_CFG_UNSET_INT = 2**128 - 15
_SIM_OUT_TEMPORARY_INT = 2**128 - 16
_SIM_OUT_EMPTY_INT = 2**128 - 17
_SIM_OUT_UNSET_INT = 2**128 - 18
_ITER_TEMPORARY_INT = 2**128 - 19
_ITER_EMPTY_INT = 2**128 - 20
_ITER_UNSET_INT = 2**128 - 21
_RISK_SEG_TEMPORARY_INT = 2**128 - 22
_RISK_SEG_EMPTY_INT = 2**128 - 23
_RISK_SEG_UNSET_INT = 2**128 - 24
_SIM_TEMPORARY_INT = 2**128 - 25
_SIM_EMPTY_INT = 2**128 - 26
_SIM_UNSET_INT = 2**128 - 27
_METRIC_DEV_UNT_INT = 2**128 - 28
_METRIC_DEV_DLR_INT = 2**128 - 29
_METRIC_TST_UNT_INT = 2**128 - 30
_METRIC_TST_DLR_INT = 2**128 - 31


class BaseUID(UUID):
    """A UUID subclass understood by pydantic and supporting sentinels.

    Behaves exactly like a regular :class:`uuid.UUID` for equality, hashing,
    ordering, and formatting, but carries pydantic validation/serialization
    schemas so fields typed with a ``BaseUID`` subclass validate UUID-like
    input and serialize to UUID strings in JSON.

    Attributes:
        _sentinels: Mapping of reserved integer values to sentinel singletons.
        _sentinel_names: Mapping of reserved integer values to sentinel names.
    """

    _sentinels: t.ClassVar[dict[int, t.Self]] = {}
    _sentinel_names: t.ClassVar[dict[int, str]] = {}

    def __init__(
        self, value: str | UUID | float | None = None, **kwargs: t.Any
    ) -> None:
        """Create a new BaseUID from a UUID-like value.

        Args:
            value: A UUID string, :class:`uuid.UUID`, integer-like value, or None
                (for the nil UUID). ``UUID`` instances are normalized to their
                string form before delegation.
            **kwargs: Additional keyword arguments forwarded to
                :class:`uuid.UUID` (e.g. ``int=``, ``hex=``, ``version=``).
        """
        if isinstance(value, UUID):
            value = str(value)

        if isinstance(value, numbers.Integral):
            kwargs["int"] = int(value)
            super().__init__(**kwargs)
            return

        if isinstance(value, numbers.Real):
            numeric_value = int(value)
            if float(numeric_value) != float(value):
                raise ValueError(
                    f"Expected integral value for {self.__class__.__name__}, got {value!r}"
                )
            kwargs["int"] = numeric_value
            super().__init__(**kwargs)
            return

        if value is None:
            super().__init__(**kwargs)
            return

        if isinstance(value, str):
            super().__init__(value, **kwargs)
            return

        raise TypeError(
            f"Expected a UUID-like value for {self.__class__.__name__}, got {type(value).__name__}"
        )

    @classmethod
    def register_sentinel(cls, name: str, int_value: int) -> t.Self:
        """Create and register a named sentinel singleton for this class.

        Args:
            name: The sentinel's name (used for repr and equality).
            int_value: The reserved UUID integer value backing the sentinel.

        Returns:
            The newly created sentinel singleton.
        """
        obj = cls(int=int_value)
        cls._sentinels[int_value] = obj
        cls._sentinel_names[int_value] = name
        return obj

    @classmethod
    def validate(cls, v: t.Any) -> t.Self:
        """Validate a value into this ID class, mapping sentinel values.

        Args:
            v: A UUID string, :class:`uuid.UUID`, integer value, or an
                existing instance of this class.

        Returns:
            The corresponding sentinel singleton if ``v`` matches a reserved
            value, otherwise a new instance of this class.

        Raises:
            TypeError: If ``v`` is not a UUID, string, or integer.
        """
        if isinstance(v, cls):
            return v

        if not isinstance(v, (str, UUID, int)):
            raise TypeError(f"Expected str, UUID, or int, got {type(v).__name__}")

        parsed = (
            v if isinstance(v, UUID) else UUID(int=v) if isinstance(v, int) else UUID(v)
        )

        if parsed.int in cls._sentinel_names:
            return cls._sentinels[parsed.int]

        return cls(str(parsed))

    @classmethod
    def __get_pydantic_core_schema__(
        cls, source_type: t.Any, handler: GetCoreSchemaHandler
    ) -> core_schema.CoreSchema:
        """Define how pydantic validates and serializes this ID type.

        Args:
            source_type: The type being validated.
            handler: Pydantic's schema handler.

        Returns:
            A pydantic CoreSchema validating UUID-like input through
            :meth:`validate` and serializing to UUID strings in JSON.
        """
        return core_schema.no_info_after_validator_function(
            function=cls.validate,
            schema=core_schema.uuid_schema(),
            serialization=core_schema.to_string_ser_schema(when_used="json"),
        )

    @property
    def value(self) -> int:
        """Compatibility alias for the numeric UUID value used by legacy code."""
        return self.int

    def __int__(self) -> int:
        """Allow integer coercion for UUID-backed IDs used by legacy code."""
        return self.int

    def __index__(self) -> int:
        """Allow these IDs to be used in integer-indexing contexts."""
        return self.int

    def __repr__(self) -> str:
        """Return ``<NAME>`` for sentinels, otherwise the standard UUID repr."""
        name = self.__class__._sentinel_names.get(self.int)
        return f"<{name}>" if name else super().__repr__()


def short_id(value: BaseUID | int) -> str:
    """Return a compact, collision-free identifier string for code templates.

    Values below 2**32 render as plain decimal (matching legacy output);
    larger values render as ``h``-prefixed hexadecimal so UUID-valued IDs
    stay readable instead of producing ~39-digit decimal blobs.
    """
    n = value.int if isinstance(value, BaseUID) else int(value)
    return str(n) if n < 2**32 else f"h{n:x}"


class DataSourceID(BaseUID):
    """Content-addressed identifier for data sources.

    The identity is derived from the data source's content, so two data
    sources with identical content share an ID. Also provides the
    ``TEMPORARY`` and ``EMPTY`` sentinels.
    """

    TEMPORARY: "DataSourceID"
    """Sentinel value representing a temporary/unsaved data source."""

    EMPTY: "DataSourceID"
    """Sentinel value representing an empty/placeholder data source."""

    UNSET: "DataSourceID"
    """Sentinel value marking a uid as not yet derived from content."""


DataSourceID.TEMPORARY = DataSourceID.register_sentinel("TEMPORARY", _TEMPORARY_INT)
DataSourceID.EMPTY = DataSourceID.register_sentinel("EMPTY", _EMPTY_INT)
DataSourceID.UNSET = DataSourceID.register_sentinel("UNSET", _UNSET_INT)


class FilterID(BaseUID):
    """Content-addressed identifier for filters.

    The identity is derived from the filter's content, so two filters with
    identical content share an ID. Also provides the ``TEMPORARY``,
    ``EMPTY``, and ``UNSET`` sentinels.
    """

    TEMPORARY: "FilterID"
    """Sentinel value representing a temporary/unsaved filter."""

    EMPTY: "FilterID"
    """Sentinel value representing an empty/placeholder filter."""

    UNSET: "FilterID"
    """Sentinel value marking a uid as not yet derived from content."""


FilterID.TEMPORARY = FilterID.register_sentinel("TEMPORARY", _FILTER_TEMPORARY_INT)
FilterID.EMPTY = FilterID.register_sentinel("EMPTY", _FILTER_EMPTY_INT)
FilterID.UNSET = FilterID.register_sentinel("UNSET", _FILTER_UNSET_INT)


class MetricID(BaseUID):
    """Content-addressed identifier for metrics.

    The identity is derived from the metric's content, so two metrics with
    identical content share an ID. Also provides the ``TEMPORARY``,
    ``EMPTY``, and ``UNSET`` sentinels plus reserved ids for the four
    built-in bad rate metrics (dev/test x unit/dollar) that an iteration
    can include alongside user-defined metrics.
    """

    TEMPORARY: "MetricID"
    """Sentinel value representing a temporary/unsaved metric."""

    EMPTY: "MetricID"
    """Sentinel value representing an empty/placeholder metric."""

    UNSET: "MetricID"
    """Sentinel value marking a uid as not yet derived from content."""

    DEV_UNT_BAD_RATE: "MetricID"
    """Reserved id for the dev unit (annualized) bad rate metric."""

    DEV_DLR_BAD_RATE: "MetricID"
    """Reserved id for the dev dollar (annualized) bad rate metric."""

    TST_UNT_BAD_RATE: "MetricID"
    """Reserved id for the test unit (early) bad rate metric."""

    TST_DLR_BAD_RATE: "MetricID"
    """Reserved id for the test dollar (early) bad rate metric."""


MetricID.TEMPORARY = MetricID.register_sentinel("TEMPORARY", _METRIC_TEMPORARY_INT)
MetricID.EMPTY = MetricID.register_sentinel("EMPTY", _METRIC_EMPTY_INT)
MetricID.UNSET = MetricID.register_sentinel("UNSET", _METRIC_UNSET_INT)
MetricID.DEV_UNT_BAD_RATE = MetricID.register_sentinel(
    "DEV_UNT_BAD_RATE", _METRIC_DEV_UNT_INT
)
MetricID.DEV_DLR_BAD_RATE = MetricID.register_sentinel(
    "DEV_DLR_BAD_RATE", _METRIC_DEV_DLR_INT
)
MetricID.TST_UNT_BAD_RATE = MetricID.register_sentinel(
    "TST_UNT_BAD_RATE", _METRIC_TST_UNT_INT
)
MetricID.TST_DLR_BAD_RATE = MetricID.register_sentinel(
    "TST_DLR_BAD_RATE", _METRIC_TST_DLR_INT
)


class SimulationConfigGeneratorID(BaseUID):
    TEMPORARY: "SimulationConfigGeneratorID"
    EMPTY: "SimulationConfigGeneratorID"
    UNSET: "SimulationConfigGeneratorID"


SimulationConfigGeneratorID.TEMPORARY = SimulationConfigGeneratorID.register_sentinel(
    "TEMPORARY", _SIM_GEN_TEMPORARY_INT
)
SimulationConfigGeneratorID.EMPTY = SimulationConfigGeneratorID.register_sentinel(
    "EMPTY", _SIM_GEN_EMPTY_INT
)
SimulationConfigGeneratorID.UNSET = SimulationConfigGeneratorID.register_sentinel(
    "UNSET", _SIM_GEN_UNSET_INT
)


class SimulationConfigID(BaseUID):
    TEMPORARY: "SimulationConfigID"
    EMPTY: "SimulationConfigID"
    UNSET: "SimulationConfigID"


SimulationConfigID.TEMPORARY = SimulationConfigID.register_sentinel(
    "TEMPORARY", _SIM_CFG_TEMPORARY_INT
)
SimulationConfigID.EMPTY = SimulationConfigID.register_sentinel(
    "EMPTY", _SIM_CFG_EMPTY_INT
)
SimulationConfigID.UNSET = SimulationConfigID.register_sentinel(
    "UNSET", _SIM_CFG_UNSET_INT
)


class SimulationOutputID(BaseUID):
    TEMPORARY: "SimulationOutputID"
    EMPTY: "SimulationOutputID"
    UNSET: "SimulationOutputID"


SimulationOutputID.TEMPORARY = SimulationOutputID.register_sentinel(
    "TEMPORARY", _SIM_OUT_TEMPORARY_INT
)
SimulationOutputID.EMPTY = SimulationOutputID.register_sentinel(
    "EMPTY", _SIM_OUT_EMPTY_INT
)
SimulationOutputID.UNSET = SimulationOutputID.register_sentinel(
    "UNSET", _SIM_OUT_UNSET_INT
)


class IterationID(BaseUID):
    """Identifier for a single-variable simulation iteration.

    Identity is a simple unique integer (1, 2, 3, ...) assigned sequentially
    by the simulation repository, mirroring v1's iteration ids. Also provides
    the ``TEMPORARY``, ``EMPTY``, and ``UNSET`` sentinels.
    """

    TEMPORARY: "IterationID"
    """Sentinel value representing a temporary/unsaved iteration."""

    EMPTY: "IterationID"
    """Sentinel value representing an empty/placeholder iteration."""

    UNSET: "IterationID"
    """Sentinel value marking a uid as not yet assigned."""


IterationID.TEMPORARY = IterationID.register_sentinel("TEMPORARY", _ITER_TEMPORARY_INT)
IterationID.EMPTY = IterationID.register_sentinel("EMPTY", _ITER_EMPTY_INT)
IterationID.UNSET = IterationID.register_sentinel("UNSET", _ITER_UNSET_INT)


class RiskSegmentID(BaseUID):
    TEMPORARY: "RiskSegmentID"
    EMPTY: "RiskSegmentID"
    UNSET: "RiskSegmentID"


RiskSegmentID.TEMPORARY = RiskSegmentID.register_sentinel(
    "TEMPORARY", _RISK_SEG_TEMPORARY_INT
)
RiskSegmentID.EMPTY = RiskSegmentID.register_sentinel("EMPTY", _RISK_SEG_EMPTY_INT)
RiskSegmentID.UNSET = RiskSegmentID.register_sentinel("UNSET", _RISK_SEG_UNSET_INT)


class SimulationID(BaseUID):
    """Identifier for a simulation top-level object (unique per creation event).

    Unlike content-addressed IDs, a Simulation's identity is unique per
    creation event: two simulations with identical SCGs are still distinct
    objects. Also provides the ``TEMPORARY``, ``EMPTY``, and ``UNSET``
    sentinels.
    """

    TEMPORARY: "SimulationID"
    EMPTY: "SimulationID"
    UNSET: "SimulationID"


SimulationID.TEMPORARY = SimulationID.register_sentinel("TEMPORARY", _SIM_TEMPORARY_INT)
SimulationID.EMPTY = SimulationID.register_sentinel("EMPTY", _SIM_EMPTY_INT)
SimulationID.UNSET = SimulationID.register_sentinel("UNSET", _SIM_UNSET_INT)


__all__ = [
    "BaseUID",
    "DataSourceID",
    "FilterID",
    "IterationID",
    "MetricID",
    "RiskSegmentID",
    "SimulationConfigGeneratorID",
    "SimulationConfigID",
    "SimulationID",
    "SimulationOutputID",
    "short_id",
]
