"""Tests for the content-addressed UUID identifier and sentinels."""

from pathlib import Path

import pytest
from pydantic import BaseModel, ValidationError

from risc_tool.data.models.data_source import DataSource, ReadConfig
from risc_tool.data.models.uid import DataSourceID, short_id


def _write_csv(path: Path, contents: str) -> None:
    path.write_text(contents, encoding="utf-8")


def test_content_hash_is_deterministic_and_excludes_uid(tmp_path: Path) -> None:
    csv_path = tmp_path / "data.csv"
    _write_csv(csv_path, "id;value\n1;foo\n")

    source = DataSource(label="Dev", filepath=csv_path, read_config=ReadConfig())
    duplicate = DataSource(label="Dev", filepath=csv_path, read_config=ReadConfig())

    assert source.uid == duplicate.uid
    assert hash(source.uid) == hash(duplicate.uid)
    assert source.create_hash() == source.uid
    assert isinstance(source.uid, DataSourceID)


def test_content_hash_changes_with_content(tmp_path: Path) -> None:
    csv_path = tmp_path / "data.csv"
    _write_csv(csv_path, "id;value\n1;foo\n")

    base = DataSource(label="Dev", filepath=csv_path, read_config=ReadConfig())

    relabeled = DataSource(label="Test", filepath=csv_path, read_config=ReadConfig())
    redirected = DataSource(
        label="Dev", filepath=tmp_path / "other.csv", read_config=ReadConfig()
    )
    reconfig = DataSource(
        label="Dev", filepath=csv_path, read_config=ReadConfig(delimiter=";")
    )

    assert relabeled.uid != base.uid
    assert redirected.uid != base.uid
    assert reconfig.uid != base.uid


def test_explicit_uid_is_preserved(tmp_path: Path) -> None:
    csv_path = tmp_path / "data.csv"
    _write_csv(csv_path, "id;value\n1;foo\n")

    source = DataSource(
        uid=DataSourceID(7),
        label="Dev",
        filepath=csv_path,
        read_config=ReadConfig(),
    )

    assert source.uid == DataSourceID(7)


def test_sentinels_have_reserved_values() -> None:
    assert DataSourceID.TEMPORARY is not DataSourceID.EMPTY
    assert DataSourceID.TEMPORARY != DataSourceID.EMPTY
    assert DataSourceID.TEMPORARY.int == 2**128 - 1
    assert DataSourceID.EMPTY.int == 2**128 - 2


def test_sentinel_validation_maps_value_to_singleton() -> None:
    parsed = DataSourceID.validate(str(DataSourceID.EMPTY))
    assert parsed is DataSourceID.EMPTY
    assert DataSourceID.validate(DataSourceID.TEMPORARY) is DataSourceID.TEMPORARY


def test_sentinel_never_collides_with_normal_id() -> None:
    normal = DataSourceID(1)
    assert normal != DataSourceID.TEMPORARY
    assert normal != DataSourceID.EMPTY


def test_sentinel_json_roundtrip_preserves_singleton() -> None:
    class Model(BaseModel):
        uid: DataSourceID

    dumped = Model(uid=DataSourceID.EMPTY).model_dump_json()
    restored = Model.model_validate_json(dumped)
    assert restored.uid is DataSourceID.EMPTY


def test_dict_key_roundtrip_preserves_singleton() -> None:
    class Repo(BaseModel):
        sources: dict[DataSourceID, DataSource]

    repo = Repo(
        sources={
            DataSourceID(1): DataSource(
                label="Dev", filepath=Path("data.csv"), read_config=ReadConfig()
            ),
            DataSourceID.EMPTY: DataSource.empty(),
        }
    )
    restored = Repo.model_validate_json(repo.model_dump_json())

    assert any(key is DataSourceID.EMPTY for key in restored.sources)


def test_json_roundtrip_preserves_id_type(tmp_path: Path) -> None:
    csv_path = tmp_path / "data.csv"
    _write_csv(csv_path, "id;value\n1;foo\n")
    source = DataSource(label="Dev", filepath=csv_path, read_config=ReadConfig())

    restored = DataSource.model_validate_json(source.model_dump_json())

    assert isinstance(restored.uid, DataSourceID)
    assert restored.uid == source.uid
    assert restored == source


def test_data_source_is_frozen(tmp_path: Path) -> None:
    csv_path = tmp_path / "data.csv"
    _write_csv(csv_path, "id;value\n1;foo\n")
    source = DataSource(label="Dev", filepath=csv_path, read_config=ReadConfig())

    with pytest.raises(ValidationError):
        source.label = "Changed"


def test_empty_template_keeps_empy_sentinel() -> None:
    empty = DataSource.empty()
    assert empty.uid is DataSourceID.EMPTY


def test_short_id_renders_decimal_below_threshold() -> None:
    assert short_id(0) == "0"
    assert short_id(255) == "255"
    assert short_id(-1) == "-1"
    assert short_id(2**32 - 1) == str(2**32 - 1)


def test_short_id_renders_hex_at_or_above_threshold() -> None:
    big = 2**64 + 15
    assert short_id(big) == f"h{big:x}"
    assert short_id(2**32) == "h100000000"
    assert short_id(DataSourceID.TEMPORARY) == "h" + "f" * 32


def test_short_id_accepts_uid_instances_and_plain_ints() -> None:
    assert short_id(DataSourceID(5)) == short_id(5)
    assert short_id(DataSourceID(2**40)) == f"h{2**40:x}"
