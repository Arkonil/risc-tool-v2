"""Tests for the frozen, content-addressed Filter and OutlierRule models.

Filter identities are derived as UUIDv5 hashes of their content (name,
query); OutlierRule identities hash only the rule parameters so data-driven
threshold recalculations never churn IDs.
"""

import polars as pl
import pytest
from pydantic import ValidationError

from risc_tool.data.models.enums import ComparisonOperation, PercentileOptions
from risc_tool.data.models.filter import Filter
from risc_tool.data.models.outlier import OutlierRule
from risc_tool.data.models.uid import FilterID


def test_filter_content_hash_is_deterministic_and_excludes_uid() -> None:
    a = Filter(name="Dev", query="value > 10")
    b = Filter(name="Dev", query="value > 10")

    assert a.uid == b.uid
    assert a.create_hash() == b.create_hash()
    assert a.create_hash() == a.uid
    assert isinstance(a.uid, FilterID)


def test_filter_content_hash_changes_with_content() -> None:
    base = Filter(name="F", query="value > 10")
    relabeled = Filter(name="G", query="value > 10")
    requeries = Filter(name="F", query="value > 11")

    assert relabeled.uid != base.uid
    assert requeries.uid != base.uid


def test_filter_explicit_uid_is_preserved() -> None:
    f = Filter(uid=FilterID(7), name="F", query="value > 10")

    assert f.uid == FilterID(7)


def test_filter_unset_uid_derives_content_hash() -> None:
    omitted = Filter(name="F", query="value > 10")
    explicit_unset = Filter(uid=FilterID.UNSET, name="F", query="value > 10")

    assert FilterID.UNSET.int == 2**128 - 6
    assert omitted.uid == omitted.create_hash()
    assert explicit_unset.uid is not FilterID.UNSET
    assert explicit_unset.uid == omitted.create_hash()
    assert "uid" in explicit_unset.model_fields_set


def test_filter_is_frozen() -> None:
    f = Filter(name="F", query="value > 10")

    with pytest.raises(ValidationError):
        f.name = "Changed"


def test_filter_sentinels_have_reserved_values() -> None:
    assert FilterID.TEMPORARY.int == 2**128 - 3
    assert FilterID.EMPTY.int == 2**128 - 4
    assert FilterID.UNSET.int == 2**128 - 6
    assert len({FilterID.TEMPORARY, FilterID.EMPTY, FilterID.UNSET}) == 3


def test_filter_sentinel_validation_maps_value_to_singleton() -> None:
    parsed = FilterID.validate(str(FilterID.EMPTY))
    assert parsed is FilterID.EMPTY
    assert FilterID.validate(FilterID.TEMPORARY) is FilterID.TEMPORARY


def test_filter_duplicate_rename_derives_new_identity() -> None:
    f = Filter(name="F", query="value > 10")
    f.validate_query(available_columns=["value"])

    dup = f.duplicate(name="F (copy)")

    assert dup.uid != f.uid
    assert dup.name == "F (copy)"
    assert dup.query == f.query
    # Compiled state depends only on the query and is carried over.
    assert dup.filter_expr is not None
    assert dup.used_columns == ["value"]


def test_filter_duplicate_without_changes_keeps_identity() -> None:
    f = Filter(name="F", query="value > 10")

    assert f.duplicate().uid == f.uid


def test_filter_json_roundtrip_preserves_identity() -> None:
    f = Filter(name="F", query="value > 10")

    restored = Filter.from_dict(f.to_dict())

    assert restored.uid == f.uid
    assert restored.name == f.name
    assert restored.query == f.query


def test_outlier_rule_hash_covers_only_parameters() -> None:
    a = OutlierRule(
        variable_name="score",
        comparison_op=ComparisonOperation.GT,
        comparison_base=PercentileOptions.PERC_90,
    )
    b = OutlierRule(
        variable_name="score",
        comparison_op=ComparisonOperation.GT,
        comparison_base=PercentileOptions.PERC_90,
    )
    other_base = OutlierRule(
        variable_name="score",
        comparison_op=ComparisonOperation.GT,
        comparison_base=PercentileOptions.PERC_95,
    )
    other_var = OutlierRule(
        variable_name="other",
        comparison_op=ComparisonOperation.GT,
        comparison_base=PercentileOptions.PERC_90,
    )
    other_op = OutlierRule(
        variable_name="score",
        comparison_op=ComparisonOperation.GE,
        comparison_base=PercentileOptions.PERC_90,
    )

    assert a.uid == b.uid == a.create_hash()
    assert a.uid != other_base.uid
    assert a.uid != other_var.uid
    assert a.uid != other_op.uid


def test_outlier_rule_name_and_uid_derived_from_parameters() -> None:
    rule = OutlierRule(
        variable_name="score",
        comparison_op=ComparisonOperation.GT,
        comparison_base=PercentileOptions.PERC_90,
    )

    assert rule.name == "score > 90th Percentile"
    assert rule.uid == rule.create_hash()


def test_outlier_rule_fixed_threshold_name() -> None:
    rule = OutlierRule(
        variable_name="score",
        comparison_op=ComparisonOperation.LE,
        comparison_base=1.5,
    )

    assert rule.name == "score <= 1.5"


def test_outlier_rule_recalculation_keeps_identity_stable() -> None:
    lf = pl.LazyFrame({"score": [0, 0, 0, 0, 0, 1, 2, 3, 10, 100]})
    rule = OutlierRule(
        variable_name="score",
        comparison_op=ComparisonOperation.GT,
        comparison_base=PercentileOptions.PERC_90,
    )
    uid_before = rule.uid

    rule.recalculate_thresholds(lf)

    assert rule.uid == uid_before == rule.create_hash()
    assert rule.mode == 0
    assert rule.threshold_val is not None and rule.threshold_val > 10.0
    assert rule.frequency == 1
    assert rule.filter_expr is not None
    assert rule.query.startswith("~((")


def test_outlier_rule_is_frozen() -> None:
    rule = OutlierRule(
        variable_name="score",
        comparison_op=ComparisonOperation.GT,
        comparison_base=1.0,
    )

    with pytest.raises(ValidationError):
        rule.variable_name = "changed"
