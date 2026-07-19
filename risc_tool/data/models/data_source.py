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


class ReadConfig(BaseModel):
    read_mode: ReadMode = "CSV"

    # CSV specific options
    delimiter: str = ","
    header_row: int = 0
    sample_row_count: int = Field(default=1000, exclude=True)

    def __hash__(self) -> int:
        return hash((
            self.read_mode,
            self.delimiter,
            self.header_row,
            self.sample_row_count,
        ))


class DataSource(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True, extra="forbid")

    uid: DataSourceID
    label: str
    filepath: Path
    read_config: ReadConfig

    _logger: logging.Logger = PrivateAttr(
        default_factory=lambda: get_logger("DataSource")
    )
    _pl_schema: pl.Schema | None = PrivateAttr(default=None)
    _full_lf: pl.LazyFrame | None = PrivateAttr(default=None)
    _full_lf_cache_key: tuple[Path, ReadConfig] | None = PrivateAttr(default=None)

    def validate_read_config(self):
        self._logger.debug(
            f"Validating read config for {self.label} with read mode {self.read_config.read_mode}"
        )

        if not self.filepath or not self.filepath.is_file():
            self._logger.error(
                f"Filepath {self.filepath} does not exist or is not a file"
            )
            raise FileNotFoundError(
                f"Filepath {self.filepath} does not exist or is not a file"
            )

        if self.read_config.read_mode == "CSV":
            if not self.filepath.suffix.lower() == ".csv":
                self._logger.error(
                    f"Filepath {self.filepath} does not match read mode CSV"
                )
                raise ValueError(
                    f"Filepath {self.filepath} does not match read mode CSV"
                )

        else:
            self._logger.error(f"Unsupported read mode: {self.read_config.read_mode}")
            raise ValueError(f"Unsupported read mode: {self.read_config.read_mode}")

    @property
    def is_valid(self) -> bool:
        try:
            self.validate_read_config()
            return True
        except (FileNotFoundError, ValueError):
            return False

    @property
    def sample_df(self) -> pl.LazyFrame:
        current_key = (self.filepath, self.read_config)

        if self._full_lf is None or self._full_lf_cache_key != current_key:
            self._logger.debug(
                f"Generating sample pandas DataFrame for {self.filepath}"
            )
            schema = (
                self._pl_schema if self._pl_schema is not None else self.get_schema()
            )

            self._full_lf = self.get_lazyframe(schema)
            self._full_lf_cache_key = (
                self.filepath,
                self.read_config.model_copy(deep=True),
            )

        return self._full_lf

    def get_schema(self) -> pl.Schema:
        self._logger.debug(
            f"Inferring schema for {self.filepath} with read mode {self.read_config.read_mode}"
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
            self._logger.error(f"Unsupported read mode: {self.read_config.read_mode}")
            raise ValueError(f"Unsupported read mode: {self.read_config.read_mode}")

        return self._pl_schema

    def get_lazyframe(self, schema: pl.Schema) -> pl.LazyFrame:
        self._logger.debug(
            f"Reading data from {self.filepath} with read mode {self.read_config.read_mode}"
        )

        if self.read_config.read_mode == "CSV":
            return pl.scan_csv(
                source=self.filepath,
                separator=self.read_config.delimiter,
                skip_lines=self.read_config.header_row,
                schema_overrides=schema,
                missing_columns="insert",
            )
        else:
            self._logger.error(f"Unsupported read mode: {self.read_config.read_mode}")
            raise ValueError(f"Unsupported read mode: {self.read_config.read_mode}")

    @classmethod
    def empty(cls) -> "DataSource":
        return cls(
            uid=DataSourceID.EMPTY,
            label="New Data Source",
            filepath=Path(),
            read_config=ReadConfig(),
        )
