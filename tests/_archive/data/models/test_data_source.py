from pathlib import Path

import polars as pl

from risc_tool.data.models.data_source import DataSource, ReadConfig
from risc_tool.data.models.uid import DataSourceID


def write_csv(path: Path, contents: str) -> None:
    """Write CSV content to a file for test setup.

    Args:
        path: The file path to write to.
        contents: The CSV content string.
    """
    path.write_text(contents, encoding="utf-8")


def test_data_source_lazyframe_cache_and_invalidation(tmp_path: Path) -> None:
    first_path = tmp_path / "test.csv"
    second_path = tmp_path / "test2.csv"

    write_csv(first_path, "id;value\n1;foo\n2;bar\n3;baz\n")
    write_csv(second_path, "id;value\n10;abc\n20;def\n")

    source = DataSource(
        label="test_source",
        filepath=first_path,
        read_config=ReadConfig(delimiter=";"),
    )

    lf1 = source.lazyframe
    assert isinstance(lf1, pl.LazyFrame)
    collected1 = lf1.collect()
    assert len(collected1) == 3
    assert list(collected1["id"]) == [1, 2, 3]
    assert list(collected1["value"]) == ["foo", "bar", "baz"]

    lf2 = source.lazyframe
    assert lf1 is lf2

    changed_config = DataSource(
        label="test_source",
        filepath=first_path,
        read_config=ReadConfig(delimiter=","),
    )
    lf3 = changed_config.lazyframe
    assert lf3 is not lf1
    assert len(lf3.collect()) == 3

    changed_file = DataSource(
        label="test_source",
        filepath=second_path,
        read_config=ReadConfig(delimiter=";"),
    )
    lf4 = changed_file.lazyframe
    assert lf4 is not lf3
    collected4 = lf4.collect()
    assert len(collected4) == 2
    assert list(collected4["id"]) == [10, 20]


def test_data_source_content_hash(tmp_path: Path) -> None:
    first_path = tmp_path / "test.csv"
    first_path.write_text("id;value\n1;foo\n", encoding="utf-8")

    source_a = DataSource(
        label="test_source",
        filepath=first_path,
        read_config=ReadConfig(delimiter=";"),
    )
    source_b = DataSource(
        label="test_source",
        filepath=first_path,
        read_config=ReadConfig(delimiter=";"),
    )
    source_c = DataSource(
        label="other",
        filepath=first_path,
        read_config=ReadConfig(delimiter=";"),
    )

    assert source_a.create_hash() == source_b.create_hash()
    assert source_a.uid == source_b.uid
    assert source_a.uid != source_c.uid
    assert source_a.create_hash() == source_a.uid


def test_data_source_explicit_uid_is_preserved(tmp_path: Path) -> None:
    first_path = tmp_path / "test.csv"
    first_path.write_text("id;value\n1;foo\n", encoding="utf-8")

    source = DataSource(
        uid=DataSourceID(7),
        label="test_source",
        filepath=first_path,
        read_config=ReadConfig(),
    )

    assert source.uid == DataSourceID(7)


def test_data_source_unset_uid_derives_content_hash(tmp_path: Path) -> None:
    first_path = tmp_path / "test.csv"
    first_path.write_text("id;value\n1;foo\n", encoding="utf-8")

    omitted = DataSource(
        label="test_source",
        filepath=first_path,
        read_config=ReadConfig(),
    )
    explicit_unset = DataSource(
        uid=DataSourceID.UNSET,
        label="test_source",
        filepath=first_path,
        read_config=ReadConfig(),
    )

    assert DataSourceID.UNSET.int == 2**128 - 5
    assert omitted.uid == omitted.create_hash()
    assert explicit_unset.uid is not DataSourceID.UNSET
    assert explicit_unset.uid == omitted.create_hash()
    assert "uid" in explicit_unset.model_fields_set
