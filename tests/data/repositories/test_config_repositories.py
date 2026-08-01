"""Unit tests for OptionRepository and ScalarRepository in risc_tool.data.repositories."""

from unittest.mock import Mock

from risc_tool.data.models.enums import LossRateTypes
from risc_tool.data.models.types import RiskSegmentID
from risc_tool.data.repositories.options import OptionRepository
from risc_tool.data.repositories.scalar import ScalarRepository


def test_option_repository_init():
    repo = OptionRepository()
    assert len(repo.segments) == 10
    assert repo.max_iteration_depth == 10
    assert repo.max_categorical_unique == 20
    assert repo.get_color(RiskSegmentID(0)) == ("#FFFFFF", "#3D8F3D")


def test_option_repository_mutations():
    repo = OptionRepository()
    subscriber = Mock(return_value=True)
    repo.subscribe(subscriber)

    # 1. Add row
    repo.add_risk_seg_row()
    assert len(repo.segments) == 11
    assert repo.segments[RiskSegmentID(10)].name == ""
    assert (
        repo.segments[RiskSegmentID(10)].lower_rate == 0.10
    )  # Recalculated based on previous upper rate (none -> 0)
    assert subscriber.call_count == 1

    # 2. Set name
    repo.set_risk_seg_name(RiskSegmentID(10), "NewTier")
    assert repo.segments[RiskSegmentID(10)].name == "NewTier"
    assert subscriber.call_count == 2

    # 3. Set upper rate
    repo.set_risk_seg_upper_rate(RiskSegmentID(10), 0.15)
    assert repo.segments[RiskSegmentID(10)].upper_rate == 0.15
    assert subscriber.call_count == 3

    # 4. Set colors
    repo.set_risk_seg_bg_color([RiskSegmentID(10)], "#000000")
    repo.set_risk_seg_font_color([RiskSegmentID(10)], "#FFFF00")
    assert repo.segments[RiskSegmentID(10)].bg_color == "#000000"
    assert repo.segments[RiskSegmentID(10)].font_color == "#FFFF00"
    assert subscriber.call_count == 5

    # 5. Set MAF
    repo.set_risk_seg_maf(RiskSegmentID(10), 1.25, LossRateTypes.DLR)
    assert repo.segments[RiskSegmentID(10)].maf_dlr == 1.25
    assert subscriber.call_count == 6

    # 6. Delete row
    repo.delete_selected_risk_seg_rows([RiskSegmentID(10)])
    assert len(repo.segments) == 10
    assert subscriber.call_count == 7


def test_option_repository_reset_and_serialization():
    repo = OptionRepository()
    repo.set_risk_seg_name(RiskSegmentID(0), "Modified")

    # Reset
    repo.reset_risk_seg_defaults()
    assert repo.segments[RiskSegmentID(0)].name == "1A"

    # Serialization
    repo.set_risk_seg_name(RiskSegmentID(0), "Custom1")
    serialized = repo.to_dict()
    new_repo = OptionRepository.from_dict(serialized)
    assert new_repo.segments[RiskSegmentID(0)].name == "Custom1"
    assert new_repo.max_iteration_depth == 10


def test_scalar_repository_mutations_and_serialization():
    repo = ScalarRepository()
    subscriber = Mock(return_value=True)
    repo.subscribe(subscriber)

    repo.set_current_rate(LossRateTypes.DLR, 0.05)
    repo.set_lifetime_rate(LossRateTypes.DLR, 0.15)
    assert repo.get_scalar(LossRateTypes.DLR).current_rate == 0.05
    assert repo.get_scalar(LossRateTypes.DLR).lifetime_rate == 0.15
    import pytest

    assert repo.get_scalar(LossRateTypes.DLR).portfolio_scalar == pytest.approx(3.0)
    assert subscriber.call_count == 2

    # Serialization
    serialized = repo.to_dict()
    new_repo = ScalarRepository.from_dict(serialized)
    assert new_repo.get_scalar(LossRateTypes.DLR).current_rate == 0.05
    assert new_repo.get_scalar(LossRateTypes.DLR).lifetime_rate == 0.15
    assert new_repo.get_scalar(LossRateTypes.ULR).current_rate is None
