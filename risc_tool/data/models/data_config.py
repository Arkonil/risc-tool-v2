import typing as t

import polars as pl

from risc_tool.data.models.data_source import DataSource
from risc_tool.data.models.enums import VariableType
from risc_tool.data.models.object_id import DataSourceID
from risc_tool.utils.logging import get_logger

logger = get_logger(__name__)


class DataConfig:
    """Stores data schemas of data sources and computes the unified superset schema.

    This class manages per-source schemas and maintains a merged schema that
    represents the union of all valid data sources, with compatible types
    resolved to their broadest common type.

    Attributes:
        _schema: The unified superset schema computed from all valid sources.
        _schemas: A dictionary mapping DataSourceID to their individual schemas.
    """

    def __init__(self) -> None:
        """Initialize an empty DataConfig with no stored schemas."""
        self._schema: pl.Schema = pl.Schema()
        self._schemas: dict[DataSourceID, pl.Schema] = {}

    @property
    def schema(self) -> pl.Schema:
        """Return the unified superset schema of all valid registered data sources.

        Returns:
            A Polars Schema representing the merged schema of all valid sources.
        """
        return self._schema

    def update_schema(self, data_sources: t.Iterable[DataSource]) -> None:
        """Update the unified schema based on the provided data sources.

        Args:
            data_sources: An iterable of DataSource objects to compute the unified schema from.
        """

        valid_data_sources = [ds for ds in data_sources if ds.is_valid]

        if not valid_data_sources:
            logger.debug("No valid data sources; schema cleared")
            self._schemas = {}
            self._schema = pl.Schema()
            return

        logger.info(
            "Updating unified schema from %d valid sources", len(valid_data_sources)
        )

        self._schemas = {
            ds.uid: ds.lazyframe.collect_schema() for ds in valid_data_sources
        }
        self._schema = pl.concat(
            [ds.lazyframe for ds in valid_data_sources], how="diagonal_relaxed"
        ).collect_schema()

    def available_columns(
        self, data_source_ids: list[DataSourceID]
    ) -> set[tuple[str, VariableType]]:
        """Get the intersection of columns and their types across the specified sources.

        Args:
            data_source_ids: List of data source IDs to intersect.

        Returns:
            A set of (column_name, VariableType) tuples.
        """
        if not data_source_ids:
            return set()

        selected_schemas = [
            self._schemas[ds_id] for ds_id in data_source_ids if ds_id in self._schemas
        ]

        if not selected_schemas:
            logger.debug("No matching schemas found for provided data source IDs")
            return set()

        common_cols = set(selected_schemas[0].keys())
        for schema in selected_schemas[1:]:
            common_cols.intersection_update(schema.keys())

        result: set[tuple[str, VariableType]] = set()
        for col in common_cols:
            dtype = self._schema[col]
            var_type = (
                VariableType.NUMERICAL
                if dtype.is_numeric()
                else VariableType.CATEGORICAL
            )
            result.add((col, var_type))

        logger.debug(
            "Available columns across %d sources: %d common columns",
            len(data_source_ids),
            len(result),
        )
        return result
