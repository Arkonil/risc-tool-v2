"""Unit tests for ConfigViewModel in risc_tool.ui.config.config_vm."""

from pandas.io.formats.style import Styler

from risc_tool.data.models.enums import LossRateTypes, RSDetCol, ScalarTableColumn
from risc_tool.data.repositories.data import DataRepository
from risc_tool.data.repositories.metric import MetricRepository
from risc_tool.data.repositories.options import OptionRepository
from risc_tool.data.repositories.scalar import ScalarRepository
from risc_tool.ui.config.config_vm import ConfigViewModel


def test_config_view_model():
    data_repo = DataRepository()
    metric_repo = MetricRepository(data_repo)
    option_repo = OptionRepository()
    scalar_repo = ScalarRepository()

    vm = ConfigViewModel(option_repo, scalar_repo, metric_repo)

    assert len(vm.segments) == 10
    assert vm.current_rate_mob == 12
    assert vm.lifetime_rate_mob == 36

    # Test risk segment mutations through VM
    vm.add_risk_seg_row()
    assert len(vm.segments) == 11

    vm.set_risk_seg_name(10, "TierX")
    assert vm.segments[10].name == "TierX"

    vm.set_risk_seg_upper_rate(10, 0.20)
    assert vm.segments[10].upper_rate == 0.20

    vm.set_risk_seg_font_color([10], "#111111")
    vm.set_risk_seg_bg_color([10], "#222222")
    assert vm.get_color("TierX") == ("#111111", "#222222")

    vm.set_risk_seg_maf(10, 1.4, LossRateTypes.DLR)
    assert vm.segments[10].maf_dlr == 1.4

    vm.delete_selected_risk_seg_rows([10])
    assert len(vm.segments) == 10

    vm.set_risk_seg_default_values()
    assert vm.segments[0].name == "1A"

    # Test scalars through VM
    vm.set_current_rate(LossRateTypes.DLR, 0.04)
    vm.set_lifetime_rate(LossRateTypes.DLR, 0.08)
    assert vm.get_current_rate(LossRateTypes.DLR) == 0.04
    assert vm.get_lifetime_rate(LossRateTypes.DLR) == 0.08
    assert vm.get_scalar(LossRateTypes.DLR).portfolio_scalar == 2.0


def test_config_view_model_styler_and_edit_processing():
    data_repo = DataRepository()
    metric_repo = MetricRepository(data_repo)
    option_repo = OptionRepository()
    scalar_repo = ScalarRepository()

    vm = ConfigViewModel(option_repo, scalar_repo, metric_repo)

    # 1. Test Styler creation
    styler = vm.risk_segment_details_styler
    assert isinstance(styler, Styler)
    df = styler.data
    assert len(df) == 10
    assert RSDetCol.RISK_SEGMENT.value in df.columns

    # 2. Test Validation logic
    invalid_df = df.copy()
    invalid_df.loc[0, RSDetCol.RISK_SEGMENT.value] = ""
    errors = vm.validate_risk_segments(invalid_df)
    assert len(errors) == 1
    assert "cannot be empty" in errors[0]

    dup_df = df.copy()
    dup_df.loc[1, RSDetCol.RISK_SEGMENT.value] = "1A"
    errors_dup = vm.validate_risk_segments(dup_df)
    assert len(errors_dup) == 1
    assert "must be unique" in errors_dup[0]

    # Test monotonicity validation
    # A. Valid monotonicity:
    valid_mono_df = df.copy()
    valid_mono_df.loc[0, RSDetCol.UPPER_RATE.value] = 2.0
    valid_mono_df.loc[1, RSDetCol.UPPER_RATE.value] = 2.0
    valid_mono_df.loc[2, RSDetCol.UPPER_RATE.value] = 3.0
    errors_mono_valid = vm.validate_risk_segments(valid_mono_df)
    assert len(errors_mono_valid) == 0

    # B. Invalid monotonicity (value lower than previous segment):
    invalid_mono_df = df.copy()
    invalid_mono_df.loc[1, RSDetCol.UPPER_RATE.value] = 1.0  # 1B set to 1.0% (less than 1A's 2.0%)
    errors_mono_invalid = vm.validate_risk_segments(invalid_mono_df)
    assert len(errors_mono_invalid) == 1
    assert "cannot be lower than that of segment" in errors_mono_invalid[0]

    # C. Missing/None treated as infinity:
    invalid_none_df = df.copy()
    invalid_none_df.loc[4, RSDetCol.UPPER_RATE.value] = None  # 3A set to None (infinity)
    # Subsequent segment 3B (idx 5) has upper rate 7.0%. Since 7.0% < inf, it should fail.
    errors_none = vm.validate_risk_segments(invalid_none_df)
    assert len(errors_none) > 0
    assert "cannot be lower than that of segment" in errors_none[0]

    # 3. Test Risk Segment Edit processing (using valid monotonic values)
    edited_df = df.copy()
    edited_df.loc[0, RSDetCol.RISK_SEGMENT.value] = "Renamed1A"
    edited_df.loc[0, RSDetCol.UPPER_RATE.value] = 1.5  # 1.5% -> 0.015 decimal
    has_changes = vm.process_risk_segment_edits(edited_df)
    assert has_changes is True
    assert vm.segments[0].name == "Renamed1A"
    assert vm.segments[0].upper_rate == 0.015

    # 4. Test Annualization Table & Edit processing
    ann_df = vm.get_annualization_df(LossRateTypes.DLR)
    assert len(ann_df) == 2
    edited_ann_df = ann_df.copy()
    edited_ann_df.loc[0, "Loss Rates"] = 2.5  # 2.5% -> 0.025
    edited_ann_df.loc[1, "Loss Rates"] = 7.5  # 7.5% -> 0.075
    has_ann_changes = vm.process_annualization_edits(LossRateTypes.DLR, edited_ann_df)
    assert has_ann_changes is True
    assert vm.get_current_rate(LossRateTypes.DLR) == 0.025
    assert vm.get_lifetime_rate(LossRateTypes.DLR) == 0.075

    # 5. Test Risk Scalar Factor Styler & MAF Edit processing
    rsf_styler = vm.get_risk_scalar_factor_styler(LossRateTypes.DLR)
    assert isinstance(rsf_styler, Styler)
    rsf_df = rsf_styler.data
    edited_rsf_df = rsf_df.copy()
    edited_rsf_df.loc[0, ScalarTableColumn.MAF.value] = 140.0  # 140% -> 1.4
    has_maf_changes = vm.process_maf_edits(LossRateTypes.DLR, edited_rsf_df)
    assert has_maf_changes is True
    assert vm.segments[0].maf_dlr == 1.4
