import polars as pl
import pytest

from risc_tool.data.models.metric import DollarBadRate, Metric, Volume
from risc_tool.data.models.types import DataSourceID, MetricID
from risc_tool.data.repositories.data import DataRepository


def test_metric_compilation_and_execution() -> None:
    # 1. Test basic sum and size
    m1 = Metric(
        uid=MetricID(1),
        name="m1",
        query="`value`.sum() / `value`.size",
        data_source_ids=[DataSourceID(1)],
        is_cumulative=False,
    )
    m1.validate_query(available_columns=["value"])
    assert m1.metric_expr is not None

    lf = pl.LazyFrame({"value": [1.0, 2.0, 3.0], "__TOTAL_SIZE__": [3, 3, 3]})
    res = lf.select(m1.metric_expr).collect()
    assert res.item(0, 0) == 2.0

    # 2. Test overall size / __TOTAL_SIZE__ usage
    m2 = Metric(
        uid=MetricID(2),
        name="m2",
        query="`value`.sum() / __TOTAL_SIZE__",
        data_source_ids=[DataSourceID(1)],
        is_cumulative=False,
    )
    m2.validate_query(available_columns=["value"])
    assert m2.metric_expr is not None

    lf = pl.LazyFrame({"value": [1.0, 2.0, 3.0], "__TOTAL_SIZE__": [10, 10, 10]})
    res = lf.select(m2.metric_expr).collect()
    assert res.item(0, 0) == 0.6  # 6.0 / 10


def test_element_wise_aggregations() -> None:
    # Test top-level horizontal functions
    lf = pl.LazyFrame({
        "a": [1.0, 10.0],
        "b": [2.0, 20.0],
        "c": [3.0, 30.0],
        "__TOTAL_SIZE__": [2, 2],
    })

    # sum(a, b, c) -> horizontal sum
    m_sum = Metric(
        uid=MetricID(1),
        name="sum",
        query="sum(a, b, c).mean()",
        data_source_ids=[DataSourceID(1)],
        is_cumulative=False,
    )
    m_sum.validate_query(available_columns=["a", "b", "c"])
    res = lf.select(m_sum.metric_expr).collect()
    # sum elements: [6.0, 60.0] -> mean is 33.0
    assert res.item(0, 0) == 33.0

    # mean(a, b, c)
    m_mean = Metric(
        uid=MetricID(2),
        name="mean",
        query="mean(a, b, c).mean()",
        data_source_ids=[DataSourceID(1)],
        is_cumulative=False,
    )
    m_mean.validate_query(available_columns=["a", "b", "c"])
    res = lf.select(m_mean.metric_expr).collect()
    # mean elements: [2.0, 20.0] -> mean is 11.0
    assert res.item(0, 0) == 11.0

    # median(a, b, c)
    m_med = Metric(
        uid=MetricID(3),
        name="median",
        query="median(a, b, c).mean()",
        data_source_ids=[DataSourceID(1)],
        is_cumulative=False,
    )
    m_med.validate_query(available_columns=["a", "b", "c"])
    res = lf.select(m_med.metric_expr).collect()
    # median elements: [2.0, 20.0] -> mean is 11.0
    assert res.item(0, 0) == 11.0


def test_series_methods_and_attributes() -> None:
    lf = pl.LazyFrame({
        "a": [1.0, 2.0, 3.0, 4.0],
        "b": [2.0, 3.0, 5.0, 6.0],
        "__TOTAL_SIZE__": [4, 4, 4, 4],
    })

    # covariance
    m_cov = Metric(
        uid=MetricID(1),
        name="cov",
        query="`a`.cov(`b`)",
        data_source_ids=[DataSourceID(1)],
        is_cumulative=False,
    )
    m_cov.validate_query(available_columns=["a", "b"])
    res = lf.select(m_cov.metric_expr).collect()
    assert abs(res.item(0, 0) - 2.33333333) < 1e-5

    # correlation
    m_corr = Metric(
        uid=MetricID(2),
        name="corr",
        query="`a`.corr(`b`)",
        data_source_ids=[DataSourceID(1)],
        is_cumulative=False,
    )
    m_corr.validate_query(available_columns=["a", "b"])
    res = lf.select(m_corr.metric_expr).collect()
    assert abs(res.item(0, 0) - 0.98994949) < 1e-5

    # nunique
    m_uniq = Metric(
        uid=MetricID(3),
        name="uniq",
        query="`a`.nunique()",
        data_source_ids=[DataSourceID(1)],
        is_cumulative=False,
    )
    m_uniq.validate_query(available_columns=["a"])
    res = lf.select(m_uniq.metric_expr).collect()
    assert res.item(0, 0) == 4

    # isin / is_in
    m_isin = Metric(
        uid=MetricID(4),
        name="isin",
        query="`a`.isin([1, 2]).sum()",
        data_source_ids=[DataSourceID(1)],
        is_cumulative=False,
    )
    m_isin.validate_query(available_columns=["a"])
    res = lf.select(m_isin.metric_expr).collect()
    assert res.item(0, 0) == 2

    # quantile (positional and default)
    m_q1 = Metric(
        uid=MetricID(5),
        name="quantile_pos",
        query="`a`.quantile(0.75)",
        data_source_ids=[DataSourceID(1)],
        is_cumulative=False,
    )
    m_q1.validate_query(available_columns=["a"])
    res = lf.select(m_q1.metric_expr).collect()
    assert abs(res.item(0, 0) - 3.0) < 1e-4

    m_q2 = Metric(
        uid=MetricID(6),
        name="quantile_kw",
        query="`a`.quantile(quantile=0.75, interpolation='nearest')",
        data_source_ids=[DataSourceID(1)],
        is_cumulative=False,
    )
    m_q2.validate_query(available_columns=["a"])
    res = lf.select(m_q2.metric_expr).collect()
    assert res.item(0, 0) in (3.0, 4.0)


def test_invalid_metric_queries() -> None:
    # 1. Non-scalar result query
    m = Metric(
        uid=MetricID(1),
        name="test",
        query="`value` + 10",
        data_source_ids=[DataSourceID(1)],
        is_cumulative=False,
    )
    with pytest.raises(ValueError, match="does not appear to be a scalar value"):
        m.validate_query(available_columns=["value"])

    # 2. Unsupported function query
    m2 = Metric(
        uid=MetricID(2),
        name="test",
        query="unknown_func(value).sum()",
        data_source_ids=[DataSourceID(1)],
        is_cumulative=False,
    )
    with pytest.raises(ValueError, match="Unsupported function"):
        m2.validate_query(available_columns=["value"])

    # 3. Missing column
    m3 = Metric(
        uid=MetricID(3),
        name="test",
        query="`missing_col`.sum()",
        data_source_ids=[DataSourceID(1)],
        is_cumulative=False,
    )
    with pytest.raises(ValueError, match="not found in the data"):
        m3.validate_query(available_columns=["value"])


def test_data_repository_summarized_and_cumulative_metrics(tmp_path) -> None:
    # Setup test file
    df = pl.DataFrame({
        "segment": ["Tier 1", "Tier 1", "Tier 2", "Tier 2", "Tier 3"],
        "bad": [0, 0, 1, 0, 1],
        "bal": [1000, 2000, 1500, 2500, 3000],
    })
    file_path = tmp_path / "test_data.csv"
    df.write_csv(file_path)

    # Initialize repository
    repo = DataRepository()
    from risc_tool.data.models.data_source import ReadConfig

    read_cfg = ReadConfig(read_mode="CSV")
    ds = repo.add_data_source("test_ds", file_path, read_cfg)

    # Define metrics
    vol_metric = Volume("bad", [ds.uid], MetricID(1), "Volume")
    vol_metric.validate_query(["bad", "bal"])

    bad_rate = DollarBadRate(
        "bad",
        "bal",
        current_rate_mob=12,
        data_source_ids=[ds.uid],
        uid=MetricID(2),
        name="Dollar Bad Rate",
    )
    bad_rate.validate_query(["bad", "bal"])

    # Test get_summarized_metrics overall
    res_lf_overall = repo.get_summarized_metrics(
        groupby_variables=[],
        metrics=[vol_metric, bad_rate],
    )
    res_overall = res_lf_overall.collect()
    assert res_overall.shape == (1, 2)  # Volume, Dollar Bad Rate
    assert res_overall.item(0, "Volume") == 5.0
    # Total bad = 2, Total bal = 10000. Bad rate = 2/10000 * (12/12) * 100 = 0.02 * 100 = 2.0%
    # Wait, DollarBadRate has is_percentage = True, but validation query checks the raw result.
    # In calculate(), is_percentage was scaling by 100.
    # Let's check how the compiled expression behaves.
    # The expression is: (`bad`.sum() / `bal`.sum()) * (12 / 12)
    # 2.0 / 10000.0 * 1 = 0.0002.
    assert abs(res_overall.item(0, "Dollar Bad Rate") - 0.0002) < 1e-6

    # Test get_summarized_metrics grouped by segment
    res_lf_grouped = repo.get_summarized_metrics(
        groupby_variables=["segment"],
        metrics=[vol_metric, bad_rate],
    )
    res_grouped = res_lf_grouped.sort("segment").collect()
    assert res_grouped.shape == (3, 3)
    assert res_grouped.item(0, "segment") == "Tier 1"
    assert res_grouped.item(0, "Volume") == 2.0

    # Test get_cumulative_metrics
    res_lf_cum = repo.get_cumulative_metrics(
        groupby_variable="segment",
        ordered_groups=["Tier 1", "Tier 2", "Tier 3"],
        metrics=[vol_metric],
    )
    res_cum = res_lf_cum.collect()
    assert res_cum.shape == (3, 2)
    assert list(res_cum["Volume"]) == [2.0, 4.0, 5.0]


def test_multi_source_metrics_calculation(tmp_path) -> None:
    # Source 1 (Dev)
    df_dev = pl.DataFrame({"segment": ["A", "B"], "val": [10, 20]})
    path_dev = tmp_path / "dev.csv"
    df_dev.write_csv(path_dev)

    # Source 2 (Test)
    df_tst = pl.DataFrame({"segment": ["A", "B"], "val": [100, 200]})
    path_tst = tmp_path / "tst.csv"
    df_tst.write_csv(path_tst)

    repo = DataRepository()
    from risc_tool.data.models.data_source import ReadConfig

    cfg = ReadConfig(read_mode="CSV")
    ds_dev = repo.add_data_source("dev", path_dev, cfg)
    ds_tst = repo.add_data_source("tst", path_tst, cfg)

    m_dev = Volume("val", [ds_dev.uid], MetricID(1), "Dev Volume")
    m_dev.validate_query(["val"])

    m_tst = Volume("val", [ds_tst.uid], MetricID(2), "Tst Volume")
    m_tst.validate_query(["val"])

    res_lf = repo.get_summarized_metrics(
        groupby_variables=["segment"],
        metrics=[m_dev, m_tst],
    )
    res_df = res_lf.sort("segment").collect()

    assert res_df.shape == (2, 3)  # segment, Dev Volume, Tst Volume
    assert list(res_df["Dev Volume"]) == [1.0, 1.0]
    assert list(res_df["Tst Volume"]) == [1.0, 1.0]


def test_summarized_metrics_edge_cases_and_filters(tmp_path) -> None:
    path = tmp_path / "data.csv"
    pl.DataFrame({
        "group": ["A", "A", "B", "B", "C"],
        "val": [10, 20, 30, 40, 50],
        "score": [100, 200, 300, 400, 500],
    }).write_csv(path)

    repo = DataRepository()
    from risc_tool.data.models.data_source import ReadConfig

    ds = repo.add_data_source("ds", path, ReadConfig(read_mode="CSV"))

    m_sum = Metric(
        uid=MetricID(1),
        name="SumVal",
        query="`val`.sum()",
        data_source_ids=[ds.uid],
        is_cumulative=False,
    )
    m_sum.validate_query(["val"])

    m_pct = Metric(
        uid=MetricID(2),
        name="PctOfTotal",
        query="`val`.sum() / __TOTAL_SIZE__",
        data_source_ids=[ds.uid],
        is_cumulative=False,
    )
    m_pct.validate_query(["val"])

    # 1. Empty metrics list
    res_empty = repo.get_summarized_metrics(
        groupby_variables=["group"], metrics=[]
    ).collect()
    assert res_empty.shape == (0, 0)

    # 2. Test data_filter
    res_filter = (
        repo
        .get_summarized_metrics(
            groupby_variables=["group"],
            data_filter=pl.col("val") > 15,
            metrics=[m_sum],
        )
        .sort("group")
        .collect()
    )
    assert res_filter.shape == (3, 2)
    assert list(res_filter["SumVal"]) == [20.0, 70.0, 50.0]

    # 3. Test with_columns pre-aggregation
    res_with_cols = (
        repo
        .get_summarized_metrics(
            groupby_variables=["band"],
            with_columns=[(pl.col("score") >= 300).alias("band")],
            metrics=[m_sum],
        )
        .sort("band")
        .collect()
    )
    assert res_with_cols.shape == (2, 2)
    assert list(res_with_cols["SumVal"]) == [30.0, 120.0]


def test_summarized_metrics_multi_source_outer_join(tmp_path) -> None:
    # Dev has groups A, B
    p_dev = tmp_path / "dev.csv"
    pl.DataFrame({"group": ["A", "B"], "val": [1, 2]}).write_csv(p_dev)

    # Test has groups B, C (partial overlap)
    p_tst = tmp_path / "tst.csv"
    pl.DataFrame({"group": ["B", "C"], "val": [10, 20]}).write_csv(p_tst)

    repo = DataRepository()
    from risc_tool.data.models.data_source import ReadConfig

    ds_dev = repo.add_data_source("dev", p_dev, ReadConfig(read_mode="CSV"))
    ds_tst = repo.add_data_source("tst", p_tst, ReadConfig(read_mode="CSV"))

    m_dev = Volume("val", [ds_dev.uid], MetricID(1), "DevVol")
    m_dev.validate_query(["val"])

    m_tst = Volume("val", [ds_tst.uid], MetricID(2), "TstVol")
    m_tst.validate_query(["val"])

    # 1. Grouped outer join
    res_df = (
        repo
        .get_summarized_metrics(
            groupby_variables=["group"],
            metrics=[m_dev, m_tst],
        )
        .sort("group")
        .collect()
    )

    assert res_df.shape == (3, 3)  # group, DevVol, TstVol
    assert list(res_df["group"]) == ["A", "B", "C"]
    assert res_df["DevVol"].to_list() == [1.0, 1.0, None]
    assert res_df["TstVol"].to_list() == [None, 1.0, 1.0]

    # 2. Overall horizontal concat (groupby_variables=[])
    res_overall = repo.get_summarized_metrics(
        groupby_variables=[],
        metrics=[m_dev, m_tst],
    ).collect()
    assert res_overall.shape == (1, 2)  # DevVol, TstVol
    assert res_overall.item(0, "DevVol") == 2.0
    assert res_overall.item(0, "TstVol") == 2.0


def test_cumulative_metrics_thorough(tmp_path) -> None:
    p_dev = tmp_path / "dev.csv"
    pl.DataFrame({"tier": ["T1", "T2", "T3"], "count": [10, 20, 30]}).write_csv(p_dev)

    p_tst = tmp_path / "tst.csv"
    pl.DataFrame({"tier": ["T1", "T2", "T4"], "count": [100, 200, 400]}).write_csv(
        p_tst
    )

    repo = DataRepository()
    from risc_tool.data.models.data_source import ReadConfig

    ds_dev = repo.add_data_source("dev", p_dev, ReadConfig(read_mode="CSV"))
    ds_tst = repo.add_data_source("tst", p_tst, ReadConfig(read_mode="CSV"))

    m_dev = Metric(
        uid=MetricID(1),
        name="CumDevCount",
        query="`count`.sum()",
        data_source_ids=[ds_dev.uid],
        is_cumulative=True,
    )
    m_dev.validate_query(["count"])

    m_tst = Metric(
        uid=MetricID(2),
        name="CumTstCount",
        query="`count`.sum()",
        data_source_ids=[ds_tst.uid],
        is_cumulative=True,
    )
    m_tst.validate_query(["count"])

    # 1. Empty metrics or empty ordered_groups
    assert repo.get_cumulative_metrics("tier", ["T1"], metrics=[]).collect().shape == (
        0,
        0,
    )
    assert repo.get_cumulative_metrics("tier", [], metrics=[m_dev]).collect().shape == (
        0,
        0,
    )

    # 2. Single metric cumulative calculation
    res_single = repo.get_cumulative_metrics(
        groupby_variable="tier",
        ordered_groups=["T1", "T2", "T3"],
        metrics=[m_dev],
    ).collect()
    assert res_single.shape == (3, 2)  # tier, CumDevCount
    assert list(res_single["CumDevCount"]) == [10.0, 30.0, 60.0]

    # 3. Multi-source cumulative calculation (Full Join)
    res_multi = repo.get_cumulative_metrics(
        groupby_variable="tier",
        ordered_groups=["T1", "T2", "T3"],
        metrics=[m_dev, m_tst],
    ).collect()
    assert res_multi.shape == (3, 3)  # tier, CumDevCount, CumTstCount
    assert list(res_multi["CumDevCount"]) == [10.0, 30.0, 60.0]
    assert list(res_multi["CumTstCount"]) == [100.0, 300.0, 300.0]
