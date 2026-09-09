"""Tests for the frozen, content-addressed Metric model.

Metric identities are derived as UUIDv5 hashes of their content (name,
query, sorted data source IDs, and display settings); data source list
ordering never affects identity.
"""

import pytest
from pydantic import ValidationError

from risc_tool.data.models.metric import (
    DefaultDollarBadRate,
    DefaultUnitBadRate,
    DollarBadRate,
    Metric,
    UnitBadRate,
    Volume,
)
from risc_tool.data.models.uid import DataSourceID, MetricID


def test_metric_content_hash_is_deterministic_and_excludes_uid() -> None:
    a = Metric(
        name="M", query="`value`.sum()", data_source_ids=[DataSourceID(1)], is_cumulative=False
    )
    b = Metric(
        name="M", query="`value`.sum()", data_source_ids=[DataSourceID(1)], is_cumulative=False
    )

    assert a.uid == b.uid
    assert a.create_hash() == a.uid
    assert isinstance(a.uid, MetricID)


def test_metric_content_hash_changes_with_content() -> None:
    base = Metric(
        name="M", query="`value`.sum()", data_source_ids=[DataSourceID(1)], is_cumulative=False
    )

    relabeled = Metric(
        name="N", query="`value`.sum()", data_source_ids=[DataSourceID(1)], is_cumulative=False
    )
    requeries = Metric(
        name="M", query="`value`.mean()", data_source_ids=[DataSourceID(1)], is_cumulative=False
    )
    resourced = Metric(
        name="M",
        query="`value`.sum()",
        data_source_ids=[DataSourceID(2)],
        is_cumulative=False,
    )
    reformatted = Metric(
        name="M",
        query="`value`.sum()",
        data_source_ids=[DataSourceID(1)],
        is_cumulative=False,
        is_percentage=True,
    )

    assert relabeled.uid != base.uid
    assert requeries.uid != base.uid
    assert resourced.uid != base.uid
    assert reformatted.uid != base.uid


def test_metric_hash_is_order_insensitive_for_sources() -> None:
    a = Metric(
        name="M",
        query="`value`.sum()",
        data_source_ids=[DataSourceID(1), DataSourceID(2)],
        is_cumulative=False,
    )
    b = Metric(
        name="M",
        query="`value`.sum()",
        data_source_ids=[DataSourceID(2), DataSourceID(1)],
        is_cumulative=False,
    )

    assert a.uid == b.uid


def test_metric_explicit_uid_is_preserved() -> None:
    m = Metric(
        uid=MetricID(7),
        name="M",
        query="`v`.sum()",
        data_source_ids=[DataSourceID(1)],
        is_cumulative=False,
    )

    assert m.uid == MetricID(7)


def test_metric_unset_uid_derives_content_hash() -> None:
    omitted = Metric(
        name="M", query="`v`.sum()", data_source_ids=[DataSourceID(1)], is_cumulative=False
    )
    explicit_unset = Metric(
        uid=MetricID.UNSET,
        name="M",
        query="`v`.sum()",
        data_source_ids=[DataSourceID(1)],
        is_cumulative=False,
    )

    assert MetricID.UNSET.int == 2**128 - 9
    assert omitted.uid == omitted.create_hash()
    assert explicit_unset.uid == omitted.create_hash()
    assert "uid" in explicit_unset.model_fields_set


def test_metric_is_frozen() -> None:
    m = Metric(
        name="M", query="`v`.sum()", data_source_ids=[DataSourceID(1)], is_cumulative=False
    )

    with pytest.raises(ValidationError):
        m.name = "Changed"


def test_metric_sentinels_have_reserved_values() -> None:
    assert MetricID.TEMPORARY.int == 2**128 - 7
    assert MetricID.EMPTY.int == 2**128 - 8
    assert MetricID.UNSET.int == 2**128 - 9
    assert len({MetricID.TEMPORARY, MetricID.EMPTY, MetricID.UNSET}) == 3


def test_metric_sentinel_validation_maps_value_to_singleton() -> None:
    parsed = MetricID.validate(str(MetricID.EMPTY))
    assert parsed is MetricID.EMPTY
    assert MetricID.validate(MetricID.TEMPORARY) is MetricID.TEMPORARY


def test_metric_with_updates_rehashes_on_content_change() -> None:
    m = Metric(
        name="M",
        query="`v`.sum()",
        data_source_ids=[DataSourceID(1)],
        is_cumulative=False,
    )
    m.validate_query(available_columns=["v"])

    renamed = m.with_updates(name="M2")

    assert renamed.uid != m.uid
    assert renamed.name == "M2"
    # Compiled state depends only on the query and is carried over.
    assert renamed.metric_expr is not None


def test_metric_with_updates_pins_explicit_uid() -> None:
    m = Metric(
        name="M",
        query="`v`.sum()",
        data_source_ids=[DataSourceID(1)],
        is_cumulative=False,
    )
    draft = Metric(uid=MetricID.EMPTY, name="", query="", data_source_ids=[], is_cumulative=False)

    pinned = m.with_updates(uid=MetricID(42))
    redrafted = draft.with_updates(data_source_ids=[DataSourceID(1)])
    kept = m.with_updates(use_thousand_sep=True)

    assert pinned.uid == MetricID(42)
    # Sentinel drafts keep their placeholder identity across edits.
    assert redrafted.uid is MetricID.EMPTY
    assert redrafted.data_source_ids == [DataSourceID(1)]
    # Non-content changes keep the derived ID.
    assert kept.uid == m.uid


def test_metric_duplicate_keeps_identity_and_state() -> None:
    m = Metric(
        name="M",
        query="`v`.sum()",
        data_source_ids=[DataSourceID(1)],
        is_cumulative=False,
        decimal_places=3,
    )
    m.validate_query(available_columns=["v"])

    dup = m.duplicate()

    assert dup.uid == m.uid
    assert dup.used_columns == ["v"]
    assert dup.metric_expr is not None

    renamed = m.duplicate(name="M (copy)")
    assert renamed.uid != m.uid
    assert renamed.name == "M (copy)"


def test_metric_json_roundtrip_preserves_identity() -> None:
    m = Metric(
        name="M",
        query="`v`.sum()",
        data_source_ids=[DataSourceID(1), DataSourceID(3)],
        is_cumulative=True,
        is_percentage=True,
        decimal_places=4,
    )

    restored = Metric.from_dict(m.to_dict())

    assert restored.uid == m.uid
    assert restored.name == m.name
    assert restored.query == m.query
    assert restored.data_source_ids == m.data_source_ids
    assert restored.is_percentage is True
    assert restored.decimal_places == 4


def test_metric_formatting_settings_roundtrip_via_properties() -> None:
    m = Metric(
        name="Pct",
        query="`v`.mean()",
        data_source_ids=[],
        is_cumulative=False,
        use_thousand_sep=False,
        is_percentage=True,
        decimal_places=1,
    )

    # Percentage formatting appends '%' only; callers scale values beforehand
    # (the compiled expression is multiplied by 100 in aggregation queries).
    assert m.format(25.6) == "25.6%"
    assert m.format(None) is None


def test_volume_subclass_builds_query_and_compiles() -> None:
    v = Volume("bad", [DataSourceID(1)], MetricID(1), "Volume")
    v.validate_query(["bad"])

    assert v.query == "`bad`.size"
    assert v.uid == Volume("bad", [DataSourceID(1)], MetricID(1), "Volume").uid
    assert v.metric_expr is not None
    assert not v.is_default


def test_volume_default_subclass_compiles_missing_query() -> None:
    v = Volume(None, [DataSourceID(1)], MetricID.TEMPORARY, "Default Volume")
    assert v.query == "__MISSING__"
    assert v.metric_expr is not None
    assert v.is_default


def test_bad_rate_subclasses_build_queries_and_compile() -> None:
    u = UnitBadRate(
        "unt_bad", current_rate_mob=12, data_source_ids=[DataSourceID(1)],
        uid=MetricID(1), name="Unt Bad Rate",
    )
    u.validate_query(["unt_bad"])
    assert "12 / 12" in u.query

    d = DollarBadRate(
        "dlr_bad",
        var_avg_bal="avg_bal",
        current_rate_mob=24,
        data_source_ids=[DataSourceID(1)],
        uid=MetricID(2),
        name="Dlr Bad Rate",
    )
    d.validate_query(["dlr_bad", "avg_bal"])
    assert "`avg_bal`.sum()" in d.query


def test_default_placeholder_subclasses_compile_missing_query() -> None:
    for cls in (DefaultUnitBadRate, DefaultDollarBadRate):
        m = cls([DataSourceID(1)], MetricID.TEMPORARY, "Placeholder")
        assert m.query == "__MISSING__"
        assert m.metric_expr is not None

    v = Volume(None, [DataSourceID(1)], MetricID.TEMPORARY, "Default Volume")
    assert v.query == "__MISSING__"
    assert v.metric_expr is not None
    assert v.is_default
