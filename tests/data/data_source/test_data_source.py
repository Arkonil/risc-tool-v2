from risc_tool_v2.data.core.uid import DataSourceID
from risc_tool_v2.data.data_source.models.data_source import DataSource, ReadConfig


def test_data_source_content_hashing(tmp_path):
    csv = tmp_path / "test.csv"
    csv.write_text("a,b\n1,2\n")

    ds1 = DataSource(label="DS1", filepath=csv, read_config=ReadConfig())
    ds2 = DataSource(label="DS1", filepath=csv, read_config=ReadConfig())
    ds3 = DataSource(label="DS2", filepath=csv, read_config=ReadConfig())

    assert ds1.uid == ds2.uid
    assert ds1.uid != ds3.uid
    assert ds1.uid != DataSourceID.UNSET


def test_data_source_is_frozen(tmp_path):
    csv = tmp_path / "test.csv"
    csv.write_text("a,b\n1,2\n")
    ds = DataSource(label="DS1", filepath=csv, read_config=ReadConfig())

    import pytest
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        ds.label = "New Label"
