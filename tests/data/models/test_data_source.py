from pathlib import Path

import polars as pl

from risc_tool.data.models.data_source import DataSource, ReadConfig
from risc_tool.data.models.object_id import DataSourceID


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
        uid=DataSourceID(1),
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

    source.read_config = ReadConfig(delimiter=",")
    lf3 = source.lazyframe
    assert lf3 is not lf1
    assert len(lf3.collect()) == 3

    source.filepath = second_path
    source.read_config = ReadConfig(delimiter=";")
    lf4 = source.lazyframe
    assert lf4 is not lf3
    collected4 = lf4.collect()
    assert len(collected4) == 2
    assert list(collected4["id"]) == [10, 20]
