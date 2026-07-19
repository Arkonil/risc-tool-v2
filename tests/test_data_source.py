from pathlib import Path
import polars as pl

from risc_tool.data.models.data_source import DataSource, ReadConfig
from risc_tool.data.models.types import DataSourceID


def write_csv(path: Path, contents: str) -> None:
    path.write_text(contents, encoding="utf-8")


def test_data_source_sample_df(tmp_path: Path) -> None:
    csv_path = tmp_path / "test.csv"
    # Write 5 rows of data
    write_csv(csv_path, "id,value\n1,foo\n2,bar\n3,baz\n4,qux\n5,quux\n")

    # Set sample_row_count to 3
    source = DataSource(
        uid=DataSourceID(1),
        label="test_source",
        filepath=csv_path,
        read_config=ReadConfig(sample_row_count=3),
    )

    # 1. Fetch sample_df
    df1 = source.sample_df
    assert isinstance(df1, pl.LazyFrame)
    collected1 = df1.collect()
    assert len(collected1) == 5
    assert list(collected1["id"]) == [1, 2, 3, 4, 5]
    assert list(collected1["value"]) == ["foo", "bar", "baz", "qux", "quux"]

    # 2. Verify it is cached (identically same object)
    df2 = source.sample_df
    assert df1 is df2

    # 3. Verify cache invalidation when config changes
    source.read_config = ReadConfig(sample_row_count=2, delimiter=",")
    df3 = source.sample_df
    assert df3 is not df1
    collected3 = df3.collect()
    assert len(collected3) == 5

    # 4. Verify cache invalidation when filepath changes
    csv_path_2 = tmp_path / "test2.csv"
    write_csv(csv_path_2, "id,value\n10,abc\n20,def\n")
    source.filepath = csv_path_2
    df4 = source.sample_df
    assert df4 is not df3
    collected4 = df4.collect()
    assert len(collected4) == 2
    assert list(collected4["id"]) == [10, 20]

    # 5. Verify cache invalidation when config is mutated in place
    source.read_config.sample_row_count = 1
    df5 = source.sample_df
    assert df5 is not df4
    collected5 = df5.collect()
    assert len(collected5) == 2
