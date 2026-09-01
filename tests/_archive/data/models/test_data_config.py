from pathlib import Path

import polars as pl

from risc_tool.data.models.data_config import DataConfig
from risc_tool.data.models.data_source import DataSource, ReadConfig
from risc_tool.data.models.uid import DataSourceID
from risc_tool.data.repositories.data import DataRepository


def write_csv(path: Path, contents: str) -> None:
    """Write CSV content to a file for test setup.

    Args:
        path: The file path to write to.
        contents: The CSV content string.
    """
    path.write_text(contents, encoding="utf-8")


def make_source(uid: int, path: Path) -> DataSource:
    """Create a DataSource for testing with default ReadConfig.

    Args:
        uid: The numeric ID for the DataSourceID.
        path: The file path for the data source.

    Returns:
        A new DataSource instance with default CSV read configuration.
    """
    return DataSource(
        uid=DataSourceID(uid),
        label=path.stem,
        filepath=path,
        read_config=ReadConfig(),
    )


def assert_dtype(schema: pl.Schema, field_name: str, expected: pl.DataType) -> None:
    """Assert that a schema field has the expected data type.

    Args:
        schema: The Polars Schema to check.
        field_name: The column name to look up.
        expected: The expected Polars DataType.
    """
    assert schema[field_name] == expected


def test_data_config_merges_missing_columns_and_widens_numeric_types(
    tmp_path: Path,
) -> None:
    first_path = tmp_path / "first.csv"
    second_path = tmp_path / "second.csv"

    write_csv(first_path, "id,value,city\n1,1.5,paris\n")
    write_csv(second_path, "id,value,flag\n2,2,1\n")

    data_config = DataConfig()
    data_config.update_schema([make_source(1, first_path), make_source(2, second_path)])

    schema = data_config.schema

    assert set(schema.keys()) == {"id", "value", "city", "flag"}
    assert_dtype(schema, "id", pl.Int64())
    assert_dtype(schema, "value", pl.Float64())
    assert_dtype(schema, "city", pl.String())
    assert_dtype(schema, "flag", pl.Int64())


def test_data_config_uses_string_for_conflicting_scalar_types(tmp_path: Path) -> None:
    first_path = tmp_path / "numeric.csv"
    second_path = tmp_path / "text.csv"

    write_csv(first_path, "value\n1\n")
    write_csv(second_path, "value\nhello\n")

    data_config = DataConfig()
    data_config.update_schema([make_source(1, first_path), make_source(2, second_path)])

    assert_dtype(data_config.schema, "value", pl.String())


def test_repository_refreshes_superset_schema_when_a_source_changes(
    tmp_path: Path,
) -> None:
    changing_path = tmp_path / "changing.csv"
    write_csv(changing_path, "value\n1\n")

    repository = DataRepository()
    ds = repository.add_data_source(
        label=changing_path.stem, filepath=changing_path, read_config=ReadConfig()
    )

    assert_dtype(repository.data_config.schema, "value", pl.Int64())

    write_csv(changing_path, "value\ntext\n")
    repository.update_data_source(ds.uid)

    assert_dtype(repository.data_config.schema, "value", pl.String())


def test_repository_updates_and_clears_cached_source_schemas(tmp_path: Path) -> None:
    first_path = tmp_path / "first.csv"
    second_path = tmp_path / "second.csv"
    missing_path = tmp_path / "missing.csv"

    write_csv(first_path, "value\n1\n")
    write_csv(second_path, "value\n1.5\n")
    write_csv(missing_path, "value\ntemp\n")

    repository = DataRepository()
    _ = repository.add_data_source("first", first_path, ReadConfig())
    ds2 = repository.add_data_source("second", second_path, ReadConfig())
    _ = repository.add_data_source("missing", missing_path, ReadConfig())

    # Make the file missing by deleting it
    missing_path.unlink()
    repository.data_config.update_schema(repository.data_sources.values())

    assert_dtype(repository.data_config.schema, "value", pl.Float64())

    replacement_path = tmp_path / "replacement.csv"
    write_csv(replacement_path, "value\nupdated\n")
    updated_ds = repository.update_data_source(ds2.uid, filepath=replacement_path)

    assert_dtype(repository.data_config.schema, "value", pl.String())

    repository.delete_data_source(updated_ds.uid)

    assert_dtype(repository.data_config.schema, "value", pl.Int64())

    repository.clear()

    assert repository.data_config.schema == pl.Schema()
