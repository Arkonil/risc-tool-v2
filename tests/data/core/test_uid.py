from risc_tool_v2.data.core.uid import (
    BaseUID,
    DataSourceID,
    FilterID,
    MetricID,
    short_id,
)


def test_base_uid_creation():
    uid = BaseUID(int=100)
    assert uid.int == 100
    assert uid.value == 100


def test_sentinels_exist_and_distinct():
    assert DataSourceID.TEMPORARY != DataSourceID.EMPTY
    assert DataSourceID.EMPTY != DataSourceID.UNSET
    assert FilterID.TEMPORARY != FilterID.EMPTY
    assert FilterID.EMPTY != FilterID.UNSET
    assert MetricID.TEMPORARY != MetricID.EMPTY
    assert MetricID.EMPTY != MetricID.UNSET


def test_short_id():
    uid_small = BaseUID(int=100)
    assert short_id(uid_small) == "100"

    uid_large = BaseUID(int=2**40 + 15)
    assert short_id(uid_large).startswith("h")
