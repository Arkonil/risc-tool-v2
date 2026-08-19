"""Repository for managing data sources and their configurations."""

import re
import typing as t
from collections import OrderedDict
from pathlib import Path

import polars as pl
from pydantic import ValidationError

from risc_tool.data.models.completion import Completion
from risc_tool.data.models.data_config import DataConfig
from risc_tool.data.models.data_source import DataSource, ReadConfig
from risc_tool.data.models.enums import Signature, VariableType
from risc_tool.data.models.exceptions import DataImportError
from risc_tool.data.models.json_models import DataRepositoryJSON
from risc_tool.data.models.metric import Metric
from risc_tool.data.models.object_id import DataSourceID
from risc_tool.data.models.types import ChangeIDs
from risc_tool.data.repositories.base import BaseRepository


class DataRepository(BaseRepository):
    """Repository for managing data sources and their unified schema.

    This class stores DataSource objects, maintains their configurations,
    and computes a unified schema across all valid sources through DataConfig.

    Attributes:
        data_sources: Ordered dictionary of data sources keyed by DataSourceID.
        data_config: DataConfig instance managing per-source and unified schemas.
    """

    @property
    def signature(self) -> Signature:
        """Get the component signature for change tracking.

        Returns:
            Signature.DATA_REPOSITORY
        """
        return Signature.DATA_REPOSITORY

    def __init__(self) -> None:
        """Initialize an empty DataRepository."""
        super().__init__()
        self.logger.debug("Initializing DataRepository")

        self.data_sources: OrderedDict[DataSourceID, DataSource] = OrderedDict()
        self.data_config = DataConfig()

    def on_dependency_update(self, change_ids: ChangeIDs) -> None:
        """Handle dependency updates (no-op for DataRepository).

        Args:
            change_ids: Set of change IDs from dependencies.
        """

    @property
    def has_valid_sources(self) -> bool:
        """Check if there is at least one valid data source configured.

        Returns:
            True if at least one data source has a loaded schema, False otherwise.
        """
        return any(ds.is_valid for ds in self.data_sources.values())

    # Data Source Management Methods (add, update, delete) are implemented below
    def add_data_source(
        self,
        label: str,
        filepath: Path,
        read_config: ReadConfig,
    ) -> DataSource:
        """Add a new data source to the repository.

        Validates the configuration, checks for duplicate labels/filepaths,
        assigns a unique ID, and updates the unified schema.

        Args:
            label: Human-readable label for the data source.
            filepath: Path to the data file.
            read_config: Configuration for reading the file.

        Returns:
            The newly created and registered DataSource.

        Raises:
            DataImportError: If validation fails, file doesn't exist,
                or label/filepath already exists.
        """
        self.logger.info(
            "Initializing new data source addition. Label: %s, File: %s, Mode: %s",
            label,
            filepath,
            read_config.read_mode,
        )
        try:
            data_source = DataSource(
                uid=DataSourceID.TEMPORARY,
                label=label,
                filepath=filepath,
                read_config=read_config,
            )
            self.logger.debug("Validating configuration for data source: %s", label)
            data_source.validate_read_config()

            for ds in self.data_sources.values():
                if ds.label == data_source.label:
                    raise ValueError(
                        f"Data source with label '{label}' already exists."
                    )
                if ds.filepath == data_source.filepath:
                    raise ValueError(
                        f"Data source with filepath '{filepath}' already exists."
                    )

        except ValidationError as error:
            self.logger.error(
                "Validation error configuring data source %s: %s", label, error
            )
            raise DataImportError(str(error).replace("\n", "\n\n"))
        except (FileNotFoundError, ValueError) as error:
            self.logger.error(
                "Configuration error configuring data source %s: %s", label, error
            )
            raise DataImportError(str(error))

        data_source.uid = DataSourceID(
            self._get_new_id(current_ids=self.data_sources.keys())
        )
        self.data_sources[data_source.uid] = data_source
        self.logger.info("Data source registered with ID %s.", data_source.uid)

        self.data_config.update_schema(self.data_sources.values())
        self.logger.info(
            "Data source %s added successfully. Notifying subscribers.", label
        )
        self.notify_subscribers()

        return data_source

    def update_data_source(
        self,
        data_source_id: DataSourceID,
        label: str | None = None,
        filepath: Path | None = None,
        read_config: ReadConfig | None = None,
    ) -> DataSource:
        """Update an existing data source's configuration.

        Creates a new DataSource with the provided parameters (keeping
        existing values for None parameters), validates it, and replaces
        the old one.

        Args:
            data_source_id: ID of the data source to update.
            label: New label (optional).
            filepath: New file path (optional).
            read_config: New read configuration (optional).

        Returns:
            The updated DataSource.

        Raises:
            DataImportError: If validation fails or file doesn't exist.
            KeyError: If data_source_id doesn't exist.
        """
        if data_source_id not in self.data_sources:
            self.logger.warning(
                "Attempted to update non-existent data source ID %s", data_source_id
            )
            raise KeyError(f"Data source ID '{data_source_id}' not found.")

        data_source = self.data_sources[data_source_id]
        self.logger.info(
            "Updating data source ID %s. Current Label: %s, Current File: %s",
            data_source_id,
            data_source.label,
            data_source.filepath,
        )

        if label is None:
            label = data_source.label
        if filepath is None:
            filepath = data_source.filepath
        if read_config is None:
            read_config = data_source.read_config

        try:
            new_data_source = DataSource(
                uid=data_source_id,
                label=label,
                filepath=filepath,
                read_config=read_config,
            )
            self.logger.debug(
                "Validating configuration for updated data source ID: %s",
                data_source_id,
            )
            new_data_source.validate_read_config()
        except ValidationError as error:
            self.logger.error(
                "Validation error updating data source ID %s: %s", data_source_id, error
            )
            raise DataImportError(str(error).replace("\n", "\n\n"), data_source)
        except (FileNotFoundError, ValueError) as error:
            self.logger.error(
                "Configuration error updating data source ID %s: %s",
                data_source_id,
                error,
            )
            raise DataImportError(str(error), data_source)

        # Store the new source
        self.data_sources[data_source_id] = new_data_source

        # Update the schema for this source in the data config
        self.data_config.update_schema(self.data_sources.values())

        # Notify subscribers
        self.logger.info(
            "Data source ID %s updated successfully. Notifying subscribers.",
            data_source_id,
        )
        self.notify_subscribers()

        return new_data_source

    def delete_data_source(self, data_source_id: DataSourceID) -> None:
        """Delete a data source from the repository.

        Removes the data source and updates the unified schema.

        Args:
            data_source_id: ID of the data source to delete.

        Returns:
            None. Logs a warning if the ID doesn't exist.
        """
        if data_source_id not in self.data_sources:
            self.logger.warning(
                "Attempted to delete non-existent data source ID %s", data_source_id
            )
            return

        self.logger.warning("Deleting data source ID %s", data_source_id)
        del self.data_sources[data_source_id]

        self.logger.debug(
            "Refreshing configuration after deletion of source %s", data_source_id
        )
        self.data_config.update_schema(self.data_sources.values())

        self.logger.info(
            "Data source ID %s deleted. Notifying subscribers.", data_source_id
        )
        self.notify_subscribers()

    # Methods for retrieving combined LazyFrames from valid data sources
    def get_lazyframe(
        self,
        data_source_ids: list[DataSourceID] | None = None,
        limit_per_source: int | None = None,
    ):
        """Get a combined LazyFrame for the specified data sources.

        Args:
            data_source_ids: List of data source IDs to include. If None, all valid sources are included.
            limit_per_source: Optional limit on the number of rows to read from each source.

        Returns:
            A combined LazyFrame for the specified data sources.
        """
        if data_source_ids is None:
            data_source_ids = list(self.data_sources.keys())

        lazy_frames: list[pl.LazyFrame] = []

        for ds_id in data_source_ids:
            if ds_id not in self.data_sources:
                continue

            ds = self.data_sources[ds_id]

            if not ds.is_valid:
                continue

            lf = ds.lazyframe

            if limit_per_source is not None:
                lf = lf.limit(limit_per_source)

            lazy_frames.append(lf)

        if not lazy_frames:
            self.logger.debug("No valid sources, returning empty LazyFrame")
            return pl.LazyFrame()

        self.logger.debug(
            "Building combined LazyFrame from %d sources", len(lazy_frames)
        )
        return pl.concat(lazy_frames, how="diagonal_relaxed")

    # Methods for retrieving common columns across data sources
    def common_columns(
        self, data_source_ids: list[DataSourceID] | None = None
    ) -> set[tuple[str, VariableType]]:
        """Get the intersection of columns and their types across specified sources.

        Args:
            data_source_ids: List of data source IDs to intersect. If None, all data sources are considered.

        Returns:
            A set of (column_name, VariableType) tuples representing common columns.
        """
        if data_source_ids is None:
            data_source_ids = list(self.data_sources.keys())

        return self.data_config.available_columns(data_source_ids)

    def get_completions_for_columns(
        self, data_source_ids: list[DataSourceID] | None = None
    ) -> list[Completion]:
        """Get column name completions for auto-complete in the UI.

        Args:
            data_source_ids: List of data source IDs to consider. If None, all data sources are considered.

        Returns:
            A list of dictionaries with column name completions for the specified data sources.
        """
        if data_source_ids is None:
            data_source_ids = list(self.data_sources.keys())

        completions: list[Completion] = []
        for col_name, var_type in self.data_config.available_columns(data_source_ids):
            completions.append(
                Completion(
                    caption=col_name,
                    value=f"`{col_name}`" if re.search(r"\s+", col_name) else col_name,
                    meta=f"{var_type.value} Column",
                    name=col_name,
                    score=100,
                )
            )
        return completions

    def get_summarized_metrics(
        self,
        groupby_variables: t.Sequence[str | pl.Expr],
        data_filter: pl.Expr | None = None,
        metrics: list[Metric] | None = None,
        with_columns: list[pl.Expr] | None = None,
    ) -> pl.LazyFrame:
        """Summarizes metrics grouped by variables and data source configurations.

        All calculations are done lazily on Polars LazyFrames. Each metric is
        evaluated strictly against its configured data_source_ids.

        Args:
            groupby_variables: List of column names or expressions to group by.
            data_filter: Optional boolean expression to filter the data.
            metrics: List of Metric objects to calculate.
            with_columns: Optional list of expressions to apply to the LazyFrame
                before grouping (e.g. to create derived segment columns).

        Returns:
            A Polars LazyFrame containing the grouped aggregations.
        """
        self.logger.info(
            "Calculating summarized metrics (count=%d) grouped by %s",
            len(metrics or []),
            groupby_variables,
        )

        if not metrics:
            return pl.LazyFrame()

        # Group metrics by their tuple of data_source_ids
        metric_groups: dict[tuple[DataSourceID, ...], list[Metric]] = {}
        for metric in metrics:
            if metric.metric_expr is not None:
                key = tuple(sorted(metric.data_source_ids))
                metric_groups.setdefault(key, []).append(metric)

        if not metric_groups:
            return pl.LazyFrame()

        sub_lfs: list[pl.LazyFrame] = []

        if with_columns is None:
            with_columns = []

        for ds_key, group_metrics in metric_groups.items():
            ds_ids = list(ds_key)
            lf = self.get_lazyframe(data_source_ids=ds_ids)

            if data_filter is not None:
                lf = lf.filter(data_filter)

            for expr in with_columns:
                lf = lf.with_columns(expr)

            total_size = lf.select(pl.len()).collect().item(0, 0)
            lf = lf.with_columns(pl.lit(total_size).alias("__TOTAL_SIZE__"))

            aggregations = [
                m.metric_expr.mul(100 if m.is_percentage else 1).alias(m.pretty_name)
                for m in group_metrics
                if m.metric_expr is not None
            ]

            if groupby_variables:
                grouped_lf = lf.group_by(groupby_variables).agg(aggregations)
            else:
                grouped_lf = lf.select(aggregations)

            sub_lfs.append(grouped_lf)

        if len(sub_lfs) == 1:
            return sub_lfs[0]

        if not groupby_variables:
            return pl.concat(sub_lfs, how="horizontal_extend")

        join_keys: list[str] = []
        for g in groupby_variables:
            if isinstance(g, str):
                join_keys.append(g)
            elif hasattr(g, "meta") and hasattr(g.meta, "output_name"):
                join_keys.append(g.meta.output_name())

        result_lf = sub_lfs[0]
        for next_lf in sub_lfs[1:]:
            result_lf = result_lf.join(
                next_lf, on=join_keys, how="full", coalesce=True, nulls_equal=True
            )

        return result_lf.filter(~pl.all_horizontal(pl.col(join_keys).is_null()))

    def get_cumulative_metrics(
        self,
        groupby_variable: str,
        ordered_groups: list[t.Any],
        data_filter: pl.Expr | None = None,
        metrics: list[Metric] | None = None,
        with_columns: list[pl.Expr] | None = None,
    ) -> pl.LazyFrame:
        """Calculates cumulative metrics grouped by an ordered set of groups.

        All calculations are done lazily on Polars LazyFrames by concatenating
        queries over expanding subsets of ordered groups for each metric's
        configured data_source_ids.

        Args:
            groupby_variable: Column name to filter/group by.
            ordered_groups: List of group values in their sorted order.
            data_filter: Optional boolean expression to filter the data.
            metrics: List of Metric objects to calculate.
            with_columns: Optional list of expressions to apply to the LazyFrame
                before filtering.

        Returns:
            A Polars LazyFrame containing the cumulative metrics for each group.
        """
        self.logger.info(
            "Calculating cumulative metrics (count=%d) grouped by '%s'",
            len(metrics or []),
            groupby_variable,
        )

        if not metrics:
            return pl.LazyFrame()

        metric_groups: dict[tuple[DataSourceID, ...], list[Metric]] = {}
        for metric in metrics:
            if metric.metric_expr is not None:
                key = tuple(sorted(metric.data_source_ids))
                metric_groups.setdefault(key, []).append(metric)

        if not metric_groups:
            return pl.LazyFrame()

        sub_lfs: list[pl.LazyFrame] = []

        if with_columns is None:
            with_columns = []

        for ds_key, group_metrics in metric_groups.items():
            ds_ids = list(ds_key) if ds_key else None
            lf = self.get_lazyframe(data_source_ids=ds_ids)

            if data_filter is not None:
                lf = lf.filter(data_filter)

            for expr in with_columns:
                lf = lf.with_columns(expr)

            total_size = lf.select(pl.len()).collect().item(0, 0)
            lf = lf.with_columns(pl.lit(total_size).alias("__TOTAL_SIZE__"))

            queries: list[pl.LazyFrame] = []
            for i, group_val in enumerate(ordered_groups):
                allowed_vals = ordered_groups[: i + 1]
                subset_lf = lf.filter(pl.col(groupby_variable).is_in(allowed_vals))

                aggregations = [pl.lit(group_val).alias(groupby_variable)]
                for m in group_metrics:
                    if m.metric_expr is not None:
                        aggregations.append(
                            m.metric_expr.mul(100 if m.is_percentage else 1).alias(
                                m.pretty_name
                            )
                        )

                queries.append(subset_lf.select(aggregations))

            if queries:
                sub_lfs.append(pl.concat(queries))

        if not sub_lfs:
            return pl.LazyFrame()

        if len(sub_lfs) == 1:
            return sub_lfs[0]

        result_lf = sub_lfs[0]
        for next_lf in sub_lfs[1:]:
            result_lf = result_lf.join(
                next_lf,
                on=groupby_variable,
                how="full",
                coalesce=True,
                nulls_equal=True,
            )

        return result_lf.filter(pl.col(groupby_variable).is_not_null())

    def to_dict(self) -> DataRepositoryJSON:
        """Serialize DataRepository state to DataRepositoryJSON Pydantic model."""
        return DataRepositoryJSON(data_sources=self.data_sources)

    @classmethod
    def from_dict(cls, data: DataRepositoryJSON):
        """Reconstruct DataRepository from DataRepositoryJSON Pydantic model or dict."""
        repo = cls()
        repo.logger.debug("Deserializing DataRepository from dict")

        for ds_uid, ds in data.data_sources.items():
            try:
                repo.data_sources[ds_uid] = ds
            except Exception as e:  # noqa: BLE001
                repo.logger.warning("Failed to load DataSource %s: %s", ds_uid, e)

        repo.data_config.update_schema(repo.data_sources.values())

        repo.notify_subscribers()
        return repo
