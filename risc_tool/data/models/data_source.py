import logging
import typing as t
from pathlib import Path

import polars as pl
from pydantic import BaseModel, ConfigDict, Field, PrivateAttr

from risc_tool.data.models.types import DataSourceID
from risc_tool.utils.logging import get_logger

ReadMode = t.Literal[
    "CSV"
]  # , "EXCEL"]  # EXCEL support is planned for future implementation


class ReadConfig(BaseModel, frozen=True):
    """Configuration for reading data from a file source.

    Attributes:
        read_mode: The file format to read (currently only "CSV" is supported).
        delimiter: The delimiter character used in CSV files.
        header_row: The row index (0-based) to use as column headers.
        sample_row_count: Number of rows to read for schema inference and preview.
    """

    read_mode: ReadMode = "CSV"

    # CSV specific options
    delimiter: str = ","
    header_row: int = 0
    sample_row_count: int = Field(default=1000, exclude=True)


class DataSource(BaseModel):
    """Represents a single data source with its configuration and cached data.

    Attributes:
        uid: Unique identifier for the data source.
        label: Human-readable label for the data source.
        filepath: Path to the data file.
        read_config: Configuration for reading the data file.
        _logger: Private logger instance for this data source.
        _pl_schema: Cached Polars schema inferred from the data file.
        _full_lf: Cached Polars LazyFrame for the full dataset.
        _full_lf_cache_key: Cache key for the LazyFrame (filepath, read_config).
    """

    model_config = ConfigDict(arbitrary_types_allowed=True, extra="forbid")

    uid: DataSourceID
    label: str
    filepath: Path
    read_config: ReadConfig

    _logger: logging.Logger = PrivateAttr(
        default_factory=lambda: get_logger("DataSource")
    )
    _pl_schema: pl.Schema | None = PrivateAttr(default=None)
    _cache_lf: pl.LazyFrame | None = PrivateAttr(default=None)
    _cache_lf_key: tuple[Path, ReadConfig] | None = PrivateAttr(default=None)

    def validate_read_config(self) -> None:
        """Validate the read configuration against the data file.

        Checks that the file exists, is a valid file, and matches the configured
        read mode (currently only CSV is supported with .csv extension).

        Raises:
            FileNotFoundError: If the filepath does not exist or is not a file.
            ValueError: If the file extension does not match the read mode,
                or if the read mode is unsupported.
        """
        self._logger.debug(
            "Validating read config for %s with read mode %s",
            self.label,
            self.read_config.read_mode,
        )

        if not self.filepath or not self.filepath.is_file():
            self._logger.error(
                "Filepath %s does not exist or is not a file", self.filepath
            )
            raise FileNotFoundError(
                f"Filepath {self.filepath} does not exist or is not a file"
            )

        if self.read_config.read_mode == "CSV":
            if self.filepath.suffix.lower() != ".csv":
                self._logger.error(
                    "Filepath %s does not match read mode CSV", self.filepath
                )
                raise ValueError(
                    f"Filepath {self.filepath} does not match read mode CSV"
                )

        else:
            self._logger.error("Unsupported read mode: %s", self.read_config.read_mode)
            raise ValueError(f"Unsupported read mode: {self.read_config.read_mode}")

    @property
    def is_valid(self) -> bool:
        """Check if the data source configuration is valid.

        Returns:
            True if the read configuration validates successfully, False otherwise.
        """
        try:
            self.validate_read_config()
            return True
        except (FileNotFoundError, ValueError):
            return False

    def get_schema(self) -> pl.Schema:
        """Infer and return the Polars schema from the data file.

        Returns:
            A Polars Schema object containing column names and data types.

        Raises:
            ValueError: If the read mode is unsupported.
        """
        self._logger.debug(
            "Inferring schema for %s with read mode %s",
            self.filepath,
            self.read_config.read_mode,
        )

        if self.read_config.read_mode == "CSV":
            self._pl_schema = pl.scan_csv(
                source=self.filepath,
                separator=self.read_config.delimiter,
                skip_lines=self.read_config.header_row,
                infer_schema=True,
                infer_schema_length=None,
            ).collect_schema()

        else:
            self._logger.error("Unsupported read mode: %s", self.read_config.read_mode)
            raise ValueError(f"Unsupported read mode: {self.read_config.read_mode}")

        return self._pl_schema

    @property
    def lazyframe(self) -> pl.LazyFrame:
        """Create a Polars LazyFrame for the data source using its cached schema.

        Returns:
            A Polars LazyFrame configured with the data source's read configuration.

        Raises:
            ValueError: If the read mode is unsupported.
        """
        self._logger.debug(
            "Reading data from %s as a lazyframe property", self.filepath
        )

        current_key = (self.filepath, self.read_config)

        if self._cache_lf is None or self._cache_lf_key != current_key:
            self._logger.debug(
                "Generating sample pandas DataFrame for %s", self.filepath
            )

            if not self._pl_schema:
                self._pl_schema = self.get_schema()

            if self.read_config.read_mode == "CSV":
                self._cache_lf = pl.scan_csv(
                    source=self.filepath,
                    separator=self.read_config.delimiter,
                    skip_lines=self.read_config.header_row,
                    schema_overrides=self._pl_schema,
                )
            else:
                self._logger.error(
                    "Unsupported read mode: %s", self.read_config.read_mode
                )
                raise ValueError(f"Unsupported read mode: {self.read_config.read_mode}")

            self._cache_lf_key = current_key
        else:
            self._logger.debug(
                "Using cached LazyFrame for %s with read config %s",
                self.filepath,
                self.read_config,
            )

        return self._cache_lf

    @classmethod
    def empty(cls) -> "DataSource":
        """Create an empty DataSource instance for use as a template.

        Returns:
            A new DataSource with EMPTY uid, default label, empty filepath, and default ReadConfig.
        """
        return cls(
            uid=DataSourceID.EMPTY,
            label="New Data Source",
            filepath=Path(),
            read_config=ReadConfig(),
        )
