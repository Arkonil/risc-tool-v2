"""Repository for managing data sources and their configurations."""

import re
from collections import OrderedDict
from pathlib import Path

import polars as pl
from pydantic import ValidationError

from risc_tool.data.models.completion import Completion
from risc_tool.data.models.data_config import DataConfig
from risc_tool.data.models.data_source import DataSource, ReadConfig
from risc_tool.data.models.enums import Signature, VariableType
from risc_tool.data.models.exceptions import DataImportError
from risc_tool.data.models.types import ChangeIDs, DataSourceID
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
        pass

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
            return pl.LazyFrame()

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
