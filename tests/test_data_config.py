from pathlib import Path

import polars as pl

from risc_tool.data.models.data_config import DataConfig, normalize_type
from risc_tool.data.models.data_source import DataSource, ReadConfig
from risc_tool.data.models.types import DataSourceID
from risc_tool.data.repositories.data import DataRepository


def write_csv(path: Path, contents: str) -> None:
    path.write_text(contents, encoding="utf-8")


def make_source(uid: int, path: Path) -> DataSource:
    return DataSource(
        uid=DataSourceID(uid),
        label=path.stem,
        filepath=path,
        read_config=ReadConfig(),
    )


def assert_dtype(schema: pl.Schema, field_name: str, expected: pl.DataType) -> None:
    assert normalize_type(schema[field_name]) == normalize_type(expected)


def test_data_config_merges_missing_columns_and_widens_numeric_types(
    tmp_path: Path,
) -> None:
    first_path = tmp_path / "first.csv"
    second_path = tmp_path / "second.csv"

    write_csv(first_path, "id,value,city\n1,1.5,paris\n")
    write_csv(second_path, "id,value,flag\n2,2,1\n")

    data_config = DataConfig()
    data_config.update_source(make_source(1, first_path))
    data_config.update_source(make_source(2, second_path))

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
    data_config.update_source(make_source(1, first_path))
    data_config.update_source(make_source(2, second_path))

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
    ds1 = repository.add_data_source("first", first_path, ReadConfig())
    ds2 = repository.add_data_source("second", second_path, ReadConfig())
    _ = repository.add_data_source("missing", missing_path, ReadConfig())

    # Make the file missing by deleting it
    missing_path.unlink()

    # Rebuild the schema configuration manually by iterating and calling update_source
    for source in repository.data_sources.values():
        repository.data_config.update_source(source)

    assert set(repository.data_config.schemas.keys()) == {
        ds1.uid,
        ds2.uid,
    }
    assert_dtype(repository.data_config.schema, "value", pl.Float64())

    replacement_path = tmp_path / "replacement.csv"
    write_csv(replacement_path, "value\nupdated\n")
    repository.update_data_source(ds2.uid, filepath=replacement_path)

    assert_dtype(repository.data_config.schema, "value", pl.String())

    repository.delete_data_source(ds2.uid)

    assert set(repository.data_config.schemas.keys()) == {ds1.uid}
    assert_dtype(repository.data_config.schema, "value", pl.Int64())

    repository.data_sources.clear()
    for uid in list(repository.data_config.schemas.keys()):
        repository.data_config.remove_source(uid)
    repository.notify_subscribers()

    assert repository.data_config.schemas == {}
    assert repository.data_config.schema == pl.Schema()
