from risc_tool_v2.data.core.enums import ComparisonOperation, PercentileOptions
from risc_tool_v2.data.core.uid import FilterID
from risc_tool_v2.data.filter.models.outlier import OutlierRule


def test_outlier_rule_content_hash():
    o1 = OutlierRule(
        variable_name="income",
        comparison_op=ComparisonOperation.GT,
        comparison_base=PercentileOptions.PERC_99,
    )
    o2 = OutlierRule(
        variable_name="income",
        comparison_op=ComparisonOperation.GT,
        comparison_base=PercentileOptions.PERC_99,
    )
    o3 = OutlierRule(
        variable_name="income",
        comparison_op=ComparisonOperation.GT,
        comparison_base=PercentileOptions.PERC_95,
    )

    assert o1.uid == o2.uid
    assert o1.uid != o3.uid
    assert o1.uid != FilterID.UNSET


def test_outlier_rule_recalculation(data_repository):
    rule = OutlierRule(
        variable_name="income",
        comparison_op=ComparisonOperation.GT,
        comparison_base=PercentileOptions.PERC_95,
    )
    lf = data_repository.get_lazyframe()
    rule.recalculate_thresholds(lf)

    assert rule.filter_expr is not None
    assert rule.threshold_val is not None
