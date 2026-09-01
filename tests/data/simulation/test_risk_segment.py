from collections import OrderedDict

import polars as pl

from risc_tool_v2.data.core.enums import LossRateTypes
from risc_tool_v2.data.core.uid import RiskSegmentID
from risc_tool_v2.data.simulation.models.risk_segment import (
    RiskSegment,
    RiskSegmentConfig,
    get_default_risk_segments,
)
from risc_tool_v2.data.simulation.models.scalar import LossRateScalar, ScalarConfig


def _custom_config() -> RiskSegmentConfig:
    return RiskSegmentConfig(
        segments=OrderedDict([
            (RiskSegmentID(0), RiskSegment(name="A", upper_rate=0.02)),
            (RiskSegmentID(1), RiskSegment(name="B", upper_rate=0.02)),
            (RiskSegmentID(2), RiskSegment(name="C", upper_rate=0.05)),
            (RiskSegmentID(3), RiskSegment(name="D", upper_rate=float("inf"))),
            (RiskSegmentID(4), RiskSegment(name="E", upper_rate=float("inf"))),
        ])
    )


def test_risk_segment_has_no_lower_rate_property() -> None:
    seg = RiskSegment(name="A", upper_rate=0.1)
    assert not hasattr(seg, "lower_rate")


def test_normalized_upper_rates_split_duplicate_bounds_and_keep_last_inf() -> None:
    cfg = _custom_config()

    normalized = cfg._normalize_upper_rates()

    assert normalized[RiskSegmentID(0)] < normalized[RiskSegmentID(1)]
    assert normalized[RiskSegmentID(1)] <= normalized[RiskSegmentID(2)]
    assert normalized[RiskSegmentID(4)] == float("inf")


def test_derived_lower_bounds_follow_previous_normalized_upper() -> None:
    cfg = _custom_config()

    lower_bounds = cfg._compute_lower_bounds()
    upper_bounds = cfg._normalize_upper_rates()

    assert lower_bounds[RiskSegmentID(0)] == 0.0
    assert lower_bounds[RiskSegmentID(1)] == upper_bounds[RiskSegmentID(0)]
    assert lower_bounds[RiskSegmentID(2)] == upper_bounds[RiskSegmentID(1)]


def test_get_segments_normalize_true_returns_distinct_upper_rates() -> None:
    cfg = _custom_config()

    original = cfg.get_segments(normalize=False)
    normalized = cfg.get_segments(normalize=True)

    assert original[RiskSegmentID(0)].upper_rate == 0.02
    assert original[RiskSegmentID(1)].upper_rate == 0.02
    assert (
        normalized[RiskSegmentID(0)].upper_rate
        < normalized[RiskSegmentID(1)].upper_rate
    )


def test_to_polars_expr_uses_derived_bounds_without_nulls() -> None:
    cfg = _custom_config()
    df = pl.DataFrame({"loss_rate": [0.005, 0.015, 0.03, 0.06, 0.2]})

    out = df.with_columns(cfg.to_polars_expr("loss_rate").alias("segment"))

    assert out.get_column("segment").null_count() == 0


def test_segment_content_hash_is_content_addressed() -> None:
    a = RiskSegment(name="A", upper_rate=0.02)
    b = RiskSegment(name="A", upper_rate=0.02)
    toggle = RiskSegment(name="A", upper_rate=0.02, selected=False)

    assert a.uid == b.uid
    assert a.uid != toggle.uid


def test_with_updates_identity_preserved_and_rekeyed_on_content_change() -> None:
    seg = RiskSegment(name="A", upper_rate=0.02)
    same = seg.with_updates(name="A")
    toggled = seg.with_updates(selected=False)

    assert same.uid == seg.uid
    assert toggled.uid != seg.uid
    assert toggled.selected is False


def test_get_segments_filters_by_selected_flag() -> None:
    cfg = RiskSegmentConfig(
        segments=OrderedDict([
            (RiskSegmentID(10), RiskSegment(name="A", upper_rate=0.02)),
            (RiskSegmentID(11), RiskSegment(name="B", upper_rate=0.05, selected=False)),
            (RiskSegmentID(12), RiskSegment(name="C", upper_rate=0.10)),
        ])
    )

    selected = cfg.get_segments(normalize=False)
    unselected = cfg.get_segments(normalize=False, selected=False)

    assert list(selected.keys()) == [RiskSegmentID(10), RiskSegmentID(12)]
    assert list(unselected.keys()) == [RiskSegmentID(11)]


def test_with_selected_rekeys_segment_under_new_uid() -> None:
    cfg = RiskSegmentConfig(
        segments=OrderedDict([
            (RiskSegmentID(20), RiskSegment(name="A", upper_rate=0.02))
        ])
    )
    toggled = cfg.with_selected(RiskSegmentID(20), False)

    assert RiskSegmentID(20) not in toggled.segments
    assert len(toggled.segments) == 1
    updated_seg = next(iter(toggled.segments.values()))
    assert updated_seg.selected is False
    assert toggled.segments[updated_seg.uid] is updated_seg
    assert updated_seg.uid != RiskSegmentID(20)


def test_default_segments_are_all_selected_and_content_addressed() -> None:
    defaults = get_default_risk_segments()

    assert len(defaults) == 10
    assert all(seg.selected for seg in defaults.values())
    assert all(seg_id == seg.uid for seg_id, seg in defaults.items())
    names = [seg.name for seg in defaults.values()]
    assert names == ["1A", "1B", "2A", "2B", "3A", "3B", "4A", "4B", "5A", "5B"]


def test_loss_rate_scalar_create_hash_is_content_addressed() -> None:
    a = LossRateScalar(
        loss_rate_type=LossRateTypes.ULR, current_rate=0.01, lifetime_rate=0.02
    )
    b = LossRateScalar(
        loss_rate_type=LossRateTypes.ULR, current_rate=0.01, lifetime_rate=0.02
    )
    c = LossRateScalar(
        loss_rate_type=LossRateTypes.ULR, current_rate=0.015, lifetime_rate=0.02
    )

    assert a.create_hash() == b.create_hash()
    assert a.create_hash() != c.create_hash()


def test_scalar_config_create_hash_uses_scalar_hashes() -> None:
    a = ScalarConfig(
        ulr_scalar=LossRateScalar(loss_rate_type=LossRateTypes.ULR, current_rate=0.01),
        dlr_scalar=LossRateScalar(loss_rate_type=LossRateTypes.DLR, current_rate=0.02),
    )
    b = ScalarConfig(
        ulr_scalar=LossRateScalar(loss_rate_type=LossRateTypes.ULR, current_rate=0.01),
        dlr_scalar=LossRateScalar(loss_rate_type=LossRateTypes.DLR, current_rate=0.02),
    )

    assert a.create_hash() == b.create_hash()
    changed = ScalarConfig(
        ulr_scalar=LossRateScalar(loss_rate_type=LossRateTypes.ULR, current_rate=0.09),
        dlr_scalar=LossRateScalar(loss_rate_type=LossRateTypes.DLR, current_rate=0.02),
    )
    assert a.create_hash() != changed.create_hash()


def test_risk_segment_config_create_hash_is_order_and_content_sensitive() -> None:
    def build(order):
        return OrderedDict([
            (RiskSegmentID(order[0]), RiskSegment(name=order[1], upper_rate=order[2])),
            (RiskSegmentID(order[3]), RiskSegment(name=order[4], upper_rate=order[5])),
        ])

    cfg1 = RiskSegmentConfig(segments=build((0, "A", 0.02, 1, "B", 0.05)))
    cfg2 = RiskSegmentConfig(segments=build((0, "A", 0.02, 1, "B", 0.05)))
    reordered = RiskSegmentConfig(segments=build((1, "B", 0.05, 0, "A", 0.02)))
    toggled = cfg1.with_selected(RiskSegmentID(0), False)

    assert cfg1.create_hash() == cfg2.create_hash()
    assert cfg1.create_hash() != reordered.create_hash()
    assert cfg1.create_hash() != toggled.create_hash()
