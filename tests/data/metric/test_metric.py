from risc_tool_v2.data.core.uid import DataSourceID, MetricID
from risc_tool_v2.data.metric.models.metric import Metric, Volume


def test_metric_content_hash():
    ds_id = DataSourceID(int=1)
    m1 = Metric(
        name="Bad Rate",
        query="unt_bad.sum() / unt_bad.size",
        data_source_ids=[ds_id],
        is_cumulative=False,
    )
    m2 = Metric(
        name="Bad Rate",
        query="unt_bad.sum() / unt_bad.size",
        data_source_ids=[ds_id],
        is_cumulative=False,
    )
    m3 = Metric(
        name="Bad Rate",
        query="unt_bad.sum() / unt_bad.size",
        data_source_ids=[ds_id],
        is_cumulative=True,
    )

    assert m1.uid == m2.uid
    assert m1.uid != m3.uid
    assert m1.uid != MetricID.UNSET


def test_volume_subclass():
    ds_id = DataSourceID(int=1)
    v = Volume(
        column_name="credit_score",
        data_source_ids=[ds_id],
        uid=MetricID(int=10),
        name="Vol",
    )
    assert v.query == "`credit_score`.size"
