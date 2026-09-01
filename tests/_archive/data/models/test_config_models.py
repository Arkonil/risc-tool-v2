"""Unit tests for configuration Pydantic models in risc_tool.data.models.config."""

from collections import OrderedDict

import polars as pl
import pytest
from pydantic import ValidationError

from risc_tool.data.models.config import (
    LossRateScalar,
    OptionsConfig,
    RiskSegment,
    RiskSegmentConfig,
    is_valid_hex_color,
)
from risc_tool.data.models.enums import LossRateTypes
from risc_tool.data.models.uid import RiskSegmentID


def test_hex_color_validation():
    assert is_valid_hex_color("#3D8F3D") is True
    assert is_valid_hex_color("#FFF") is True
    assert is_valid_hex_color("INVALID") is False

    seg = RiskSegment(
        name="1A",
        lower_rate=0.0,
        upper_rate=1.0,
        bg_color="3d8f3d",
        font_color="#ffffff",
    )
    assert seg.bg_color == "#3D8F3D"
    assert seg.font_color == "#FFFFFF"

    with pytest.raises(ValidationError):
        RiskSegment(name="1A", lower_rate=0.0, upper_rate=1.0, bg_color="invalid_color")


def test_maf_validation():
    seg = RiskSegment(
        name="1A", lower_rate=0.0, upper_rate=1.0, maf_dlr=1.5, maf_ulr=1.2
    )
    assert seg.maf_dlr == 1.5
    assert seg.maf_ulr == 1.2

    with pytest.raises(ValidationError):
        RiskSegment(name="1A", lower_rate=0.0, upper_rate=1.0, maf_dlr=-0.5)


def test_risk_segment_config_defaults():
    config = RiskSegmentConfig()
    assert len(config.segments) == 10
    assert config.segments[RiskSegmentID(0)].name == "1A"
    assert config.segments[RiskSegmentID(0)].lower_rate == 0.0
    assert config.segments[RiskSegmentID(0)].upper_rate == 0.02
    assert config.segments[RiskSegmentID(9)].name == "5B"
    assert config.segments[RiskSegmentID(9)].upper_rate == float("inf")


def test_recalculate_lower_bounds():
    segments: OrderedDict[RiskSegmentID, RiskSegment] = OrderedDict([
        (
            RiskSegmentID(0),
            RiskSegment(name="Tier 1", lower_rate=0.0, upper_rate=0.05),
        ),
        (
            RiskSegmentID(1),
            RiskSegment(name="Tier 2", lower_rate=0.0, upper_rate=0.10),
        ),
        (
            RiskSegmentID(2),
            RiskSegment(name="Tier 3", lower_rate=0.0, upper_rate=float("inf")),
        ),
    ])
    config = RiskSegmentConfig(segments=segments)
    config.recalculate_lower_bounds()

    assert config.segments[RiskSegmentID(0)].lower_rate == 0.0
    assert config.segments[RiskSegmentID(1)].lower_rate == 0.05
    assert config.segments[RiskSegmentID(2)].lower_rate == 0.10


def test_duplicate_names():
    config = RiskSegmentConfig()
    assert config.get_duplicate_names() == []

    dup_config = RiskSegmentConfig(
        segments=OrderedDict([
            (
                RiskSegmentID(0),
                RiskSegment(name="1A", lower_rate=0.00, upper_rate=0.02),
            ),
            (
                RiskSegmentID(1),
                RiskSegment(name="1A", lower_rate=0.02, upper_rate=0.04),
            ),
        ])
    )
    assert dup_config.get_duplicate_names() == ["1A"]


def test_risk_segment_polars_expr():
    config = RiskSegmentConfig(
        segments=OrderedDict([
            (
                RiskSegmentID(0),
                RiskSegment(name="Low", lower_rate=0.0, upper_rate=0.03),
            ),
            (
                RiskSegmentID(1),
                RiskSegment(name="Med", lower_rate=0.03, upper_rate=0.07),
            ),
            (
                RiskSegmentID(2),
                RiskSegment(name="High", lower_rate=0.07, upper_rate=float("inf")),
            ),
        ])
    )

    df = pl.DataFrame({"bad_rate": [0.01, 0.03, 0.05, 0.07, 0.12]})
    expr = config.to_polars_expr("bad_rate")
    res = df.with_columns(risk_tier=expr)

    expected = ["Low", "Med", "Med", "High", "High"]
    assert res["risk_tier"].to_list() == expected


def test_loss_rate_scalar():
    scalar = LossRateScalar(
        loss_rate_type=LossRateTypes.DLR,
        current_rate=0.02,
        lifetime_rate=0.05,
    )
    assert scalar.portfolio_scalar == 2.5

    scalar_unset = LossRateScalar(loss_rate_type=LossRateTypes.ULR)
    assert scalar_unset.portfolio_scalar == 1.0


def test_risk_scalar_factor_polars_expr():
    scalar = LossRateScalar(
        loss_rate_type=LossRateTypes.DLR,
        current_rate=0.02,
        lifetime_rate=0.04,  # portfolio scalar = 2.0
    )

    df = pl.DataFrame({"maf": [0.4, 0.6, 1.0]})
    expr = scalar.get_risk_scalar_factor_expr("maf")
    res = df.with_columns(rsf=expr)

    # maf * 2.0: 0.8 -> clamped to 1.0; 1.2 -> 1.2; 2.0 -> 2.0
    assert res["rsf"].to_list() == [1.0, 1.2, 2.0]


def test_options_config():
    opts = OptionsConfig()
    assert opts.max_categorical_unique == 20


def test_has_finite_upper_bound_segment():
    config = RiskSegmentConfig()
    # By default, segments 0..7 have finite upper rates, 8 and 9 have inf
    assert config.has_finite_upper_bound_segment() is True
    assert (
        config.has_finite_upper_bound_segment([RiskSegmentID(0), RiskSegmentID(8)])
        is True
    )
    assert (
        config.has_finite_upper_bound_segment([RiskSegmentID(8), RiskSegmentID(9)])
        is False
    )
    assert config.has_finite_upper_bound_segment([]) is False
