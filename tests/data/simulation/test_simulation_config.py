from collections import OrderedDict

from risc_tool_v2.data.core.enums import LossRateTypes, VariableType
from risc_tool_v2.data.core.uid import DataSourceID, FilterID, RiskSegmentID
from risc_tool_v2.data.simulation.models.risk_segment import (
    RiskSegment,
    RiskSegmentConfig,
)
from risc_tool_v2.data.simulation.models.scalar import ScalarConfig
from risc_tool_v2.data.simulation.models.simulation_config import (
    BadRateConfig,
    SimulationConfig,
    SimulationConfigGenerator,
)


def _risk_config() -> RiskSegmentConfig:
    return RiskSegmentConfig(
        segments=OrderedDict([
            (RiskSegmentID(0), RiskSegment(name="A", upper_rate=0.02)),
            (RiskSegmentID(1), RiskSegment(name="B", upper_rate=0.02)),
            (RiskSegmentID(2), RiskSegment(name="C", upper_rate=float("inf"))),
        ])
    )


def _dev_unit_br() -> BadRateConfig:
    return BadRateConfig(
        loss_rate_type=LossRateTypes.ULR,
        numerator_col="unt_bad",
        current_rate_mob=6,
        data_source_ids=(DataSourceID(int=1),),
        is_annualized=True,
    )


def _dev_dollar_br() -> BadRateConfig:
    return BadRateConfig(
        loss_rate_type=LossRateTypes.DLR,
        numerator_col="dlr_bad",
        denominator_col="avg_bal",
        current_rate_mob=6,
        data_source_ids=(DataSourceID(int=1),),
        is_annualized=True,
    )


def _test_unit_br() -> BadRateConfig:
    return BadRateConfig(
        loss_rate_type=LossRateTypes.ULR,
        numerator_col="unt_bad",
        current_rate_mob=12,
        data_source_ids=(DataSourceID(int=1),),
        is_annualized=False,
    )


def _test_dollar_br() -> BadRateConfig:
    return BadRateConfig(
        loss_rate_type=LossRateTypes.DLR,
        numerator_col="dlr_bad",
        denominator_col="avg_bal",
        current_rate_mob=12,
        data_source_ids=(DataSourceID(int=1),),
        is_annualized=False,
    )


def test_simulation_config_hash_is_deterministic_with_derived_bounds() -> None:
    scalar_config = ScalarConfig()

    c1 = SimulationConfig(
        risk_segment_config=_risk_config(),
        dev_unit_bad_rate=_dev_unit_br(),
        dev_dollar_bad_rate=_dev_dollar_br(),
        test_unit_bad_rate=_test_unit_br(),
        test_dollar_bad_rate=_test_dollar_br(),
        bad_rate_type=LossRateTypes.ULR,
        scalar_config=scalar_config,
        filter_ids=(FilterID(int=1),),
        variable_name="score",
        variable_type=VariableType.NUMERICAL,
    )
    c2 = SimulationConfig(
        risk_segment_config=_risk_config(),
        dev_unit_bad_rate=_dev_unit_br(),
        dev_dollar_bad_rate=_dev_dollar_br(),
        test_unit_bad_rate=_test_unit_br(),
        test_dollar_bad_rate=_test_dollar_br(),
        bad_rate_type=LossRateTypes.ULR,
        scalar_config=scalar_config,
        filter_ids=(FilterID(int=1),),
        variable_name="score",
        variable_type=VariableType.NUMERICAL,
    )

    assert c1.uid == c2.uid


def test_simulation_config_hash_changes_when_upper_rates_change() -> None:
    base_cfg = _risk_config()
    changed_cfg = RiskSegmentConfig(
        segments=OrderedDict([
            (RiskSegmentID(0), RiskSegment(name="A", upper_rate=0.01)),
            (RiskSegmentID(1), RiskSegment(name="B", upper_rate=0.03)),
            (RiskSegmentID(2), RiskSegment(name="C", upper_rate=float("inf"))),
        ])
    )

    scalar_config = ScalarConfig()

    c1 = SimulationConfig(
        risk_segment_config=base_cfg,
        dev_unit_bad_rate=_dev_unit_br(),
        dev_dollar_bad_rate=_dev_dollar_br(),
        test_unit_bad_rate=_test_unit_br(),
        test_dollar_bad_rate=_test_dollar_br(),
        bad_rate_type=LossRateTypes.ULR,
        scalar_config=scalar_config,
        filter_ids=(FilterID(int=1),),
        variable_name="score",
        variable_type=VariableType.NUMERICAL,
    )
    c2 = SimulationConfig(
        risk_segment_config=changed_cfg,
        dev_unit_bad_rate=_dev_unit_br(),
        dev_dollar_bad_rate=_dev_dollar_br(),
        test_unit_bad_rate=_test_unit_br(),
        test_dollar_bad_rate=_test_dollar_br(),
        bad_rate_type=LossRateTypes.ULR,
        scalar_config=scalar_config,
        filter_ids=(FilterID(int=1),),
        variable_name="score",
        variable_type=VariableType.NUMERICAL,
    )

    assert c1.uid != c2.uid


def test_simulation_config_hash_ignores_test_bad_rates() -> None:
    """Test that changing test bad rates does not change the config hash."""
    scalar_config = ScalarConfig()

    test_unit_br_1 = _test_unit_br()
    test_unit_br_2 = BadRateConfig(
        loss_rate_type=LossRateTypes.ULR,
        numerator_col="unt_bad_v2",
        current_rate_mob=12,
        data_source_ids=(DataSourceID(int=1),),
        is_annualized=False,
    )

    c1 = SimulationConfig(
        risk_segment_config=_risk_config(),
        dev_unit_bad_rate=_dev_unit_br(),
        dev_dollar_bad_rate=_dev_dollar_br(),
        test_unit_bad_rate=test_unit_br_1,
        test_dollar_bad_rate=_test_dollar_br(),
        bad_rate_type=LossRateTypes.ULR,
        scalar_config=scalar_config,
        filter_ids=(FilterID(int=1),),
        variable_name="score",
        variable_type=VariableType.NUMERICAL,
    )
    c2 = SimulationConfig(
        risk_segment_config=_risk_config(),
        dev_unit_bad_rate=_dev_unit_br(),
        dev_dollar_bad_rate=_dev_dollar_br(),
        test_unit_bad_rate=test_unit_br_2,
        test_dollar_bad_rate=_test_dollar_br(),
        bad_rate_type=LossRateTypes.ULR,
        scalar_config=scalar_config,
        filter_ids=(FilterID(int=1),),
        variable_name="score",
        variable_type=VariableType.NUMERICAL,
    )

    assert c1.uid == c2.uid


def test_simulation_config_hash_uses_selected_dev_bad_rate() -> None:
    """Test that hash changes based on selected dev bad rate (ULR vs DLR)."""
    scalar_config = ScalarConfig()

    # ULR selected
    c1 = SimulationConfig(
        risk_segment_config=_risk_config(),
        dev_unit_bad_rate=_dev_unit_br(),
        dev_dollar_bad_rate=_dev_dollar_br(),
        test_unit_bad_rate=_test_unit_br(),
        test_dollar_bad_rate=_test_dollar_br(),
        bad_rate_type=LossRateTypes.ULR,
        scalar_config=scalar_config,
        filter_ids=(FilterID(int=1),),
        variable_name="score",
        variable_type=VariableType.NUMERICAL,
    )

    # DLR selected - different hash
    c2 = SimulationConfig(
        risk_segment_config=_risk_config(),
        dev_unit_bad_rate=_dev_unit_br(),
        dev_dollar_bad_rate=_dev_dollar_br(),
        test_unit_bad_rate=_test_unit_br(),
        test_dollar_bad_rate=_test_dollar_br(),
        bad_rate_type=LossRateTypes.DLR,
        scalar_config=scalar_config,
        filter_ids=(FilterID(int=1),),
        variable_name="score",
        variable_type=VariableType.NUMERICAL,
    )

    assert c1.uid != c2.uid


def test_simulation_config_hash_changes_when_selected_dev_bad_rate_changes() -> None:
    """Test that hash changes when the selected dev bad rate changes."""
    scalar_config = ScalarConfig()

    dev_unit_br_1 = _dev_unit_br()
    dev_unit_br_2 = BadRateConfig(
        loss_rate_type=LossRateTypes.ULR,
        numerator_col="unt_bad_v2",
        current_rate_mob=6,
        data_source_ids=(DataSourceID(int=1),),
        is_annualized=True,
    )

    # ULR selected, different dev unit bad rate
    c1 = SimulationConfig(
        risk_segment_config=_risk_config(),
        dev_unit_bad_rate=dev_unit_br_1,
        dev_dollar_bad_rate=_dev_dollar_br(),
        test_unit_bad_rate=_test_unit_br(),
        test_dollar_bad_rate=_test_dollar_br(),
        bad_rate_type=LossRateTypes.ULR,
        scalar_config=scalar_config,
        filter_ids=(FilterID(int=1),),
        variable_name="score",
        variable_type=VariableType.NUMERICAL,
    )
    c2 = SimulationConfig(
        risk_segment_config=_risk_config(),
        dev_unit_bad_rate=dev_unit_br_2,
        dev_dollar_bad_rate=_dev_dollar_br(),
        test_unit_bad_rate=_test_unit_br(),
        test_dollar_bad_rate=_test_dollar_br(),
        bad_rate_type=LossRateTypes.ULR,
        scalar_config=scalar_config,
        filter_ids=(FilterID(int=1),),
        variable_name="score",
        variable_type=VariableType.NUMERICAL,
    )

    assert c1.uid != c2.uid


def test_bad_rate_config_validator_enforces_test_mob() -> None:
    """Test that test bad rates must have current_rate_mob=12."""
    # Valid test bad rate
    br = BadRateConfig(
        loss_rate_type=LossRateTypes.ULR,
        numerator_col="unt_bad",
        current_rate_mob=12,
        data_source_ids=(DataSourceID(int=1),),
        is_annualized=False,
    )
    assert br.current_rate_mob == 12

    # Invalid test bad rate - should raise
    try:
        BadRateConfig(
            loss_rate_type=LossRateTypes.ULR,
            numerator_col="unt_bad",
            current_rate_mob=6,
            data_source_ids=(DataSourceID(int=1),),
            is_annualized=False,
        )
        assert False, "Should have raised ValueError"
    except ValueError as e:
        assert "Test bad rates must have current_rate_mob=12" in str(e)


def test_bad_rate_config_optional_numerator_denominator() -> None:
    """Test that numerator_col and denominator_col are optional."""
    # ULR with None numerator
    br_ulr = BadRateConfig(
        loss_rate_type=LossRateTypes.ULR,
        numerator_col=None,
        current_rate_mob=12,
        data_source_ids=(DataSourceID(int=1),),
        is_annualized=True,
    )
    assert br_ulr.numerator_col is None

    # DLR with None numerator and denominator
    br_dlr = BadRateConfig(
        loss_rate_type=LossRateTypes.DLR,
        numerator_col=None,
        denominator_col=None,
        current_rate_mob=12,
        data_source_ids=(DataSourceID(int=1),),
        is_annualized=True,
    )
    assert br_dlr.numerator_col is None
    assert br_dlr.denominator_col is None


def test_bad_rate_config_to_metric_returns_default_when_columns_none() -> None:
    """Test that to_metric returns default metrics when columns are None."""
    import uuid

    from risc_tool_v2.data.core.uid import MetricID
    from risc_tool_v2.data.metric.models.metric import DollarBadRate, UnitBadRate

    # ULR with None numerator
    br_ulr = BadRateConfig(
        loss_rate_type=LossRateTypes.ULR,
        numerator_col=None,
        current_rate_mob=12,
        data_source_ids=(DataSourceID(int=1),),
        is_annualized=True,
    )
    metric = br_ulr.to_metric(MetricID(str(uuid.uuid4())), "test")
    assert isinstance(metric, UnitBadRate)
    assert metric.is_default

    # DLR with None numerator/denominator
    br_dlr = BadRateConfig(
        loss_rate_type=LossRateTypes.DLR,
        numerator_col=None,
        denominator_col=None,
        current_rate_mob=12,
        data_source_ids=(DataSourceID(int=1),),
        is_annualized=True,
    )
    metric = br_dlr.to_metric(MetricID(str(uuid.uuid4())), "test")
    assert isinstance(metric, DollarBadRate)
    assert metric.is_default


def test_scg_get_configs_returns_single_matching_config() -> None:
    scalar_config = ScalarConfig()

    scg = SimulationConfigGenerator(
        name="base",
        risk_segment_config=_risk_config(),
        dev_unit_bad_rate=_dev_unit_br(),
        dev_dollar_bad_rate=_dev_dollar_br(),
        test_unit_bad_rate=_test_unit_br(),
        test_dollar_bad_rate=_test_dollar_br(),
        bad_rate_type=LossRateTypes.ULR,
        scalar_config=scalar_config,
        filter_ids=(FilterID(int=1),),
        variable_name="score",
        variable_type=VariableType.NUMERICAL,
    )

    generated = scg.get_configs()

    assert len(generated) == 1
    assert generated[0].risk_segment_config == scg.risk_segment_config
    assert generated[0].dev_unit_bad_rate == scg.dev_unit_bad_rate
    assert generated[0].dev_dollar_bad_rate == scg.dev_dollar_bad_rate
    assert generated[0].test_unit_bad_rate == scg.test_unit_bad_rate
    assert generated[0].test_dollar_bad_rate == scg.test_dollar_bad_rate
    assert generated[0].bad_rate_type == scg.bad_rate_type
    assert generated[0].scalar_config == scg.scalar_config
    assert generated[0].filter_ids == scg.filter_ids
    assert generated[0].variable_name == scg.variable_name
    assert generated[0].variable_type == scg.variable_type


def test_scg_hash_changes_when_generator_fields_change() -> None:
    scalar_config = ScalarConfig()

    scg1 = SimulationConfigGenerator(
        name="base",
        risk_segment_config=_risk_config(),
        dev_unit_bad_rate=_dev_unit_br(),
        dev_dollar_bad_rate=_dev_dollar_br(),
        test_unit_bad_rate=_test_unit_br(),
        test_dollar_bad_rate=_test_dollar_br(),
        bad_rate_type=LossRateTypes.ULR,
        scalar_config=scalar_config,
        filter_ids=(FilterID(int=1),),
        variable_name="score",
        variable_type=VariableType.NUMERICAL,
    )
    scg2 = scg1.with_updates(variable_name="score_v2")

    assert scg1.uid != scg2.uid


def test_scg_hash_includes_all_four_bad_rates() -> None:
    """Test that generator hash includes all four bad rate configs."""
    scalar_config = ScalarConfig()

    scg1 = SimulationConfigGenerator(
        name="base",
        risk_segment_config=_risk_config(),
        dev_unit_bad_rate=_dev_unit_br(),
        dev_dollar_bad_rate=_dev_dollar_br(),
        test_unit_bad_rate=_test_unit_br(),
        test_dollar_bad_rate=_test_dollar_br(),
        bad_rate_type=LossRateTypes.ULR,
        scalar_config=scalar_config,
        filter_ids=(FilterID(int=1),),
        variable_name="score",
        variable_type=VariableType.NUMERICAL,
    )

    # Change test unit bad rate - generator hash should change
    scg2 = scg1.with_updates(
        test_unit_bad_rate=BadRateConfig(
            loss_rate_type=LossRateTypes.ULR,
            numerator_col="unt_bad_v2",
            current_rate_mob=12,
            data_source_ids=(DataSourceID(int=1),),
            is_annualized=False,
        )
    )

    assert scg1.uid != scg2.uid


def test_scg_hash_includes_bad_rate_type() -> None:
    """Test that generator hash includes bad_rate_type."""
    scalar_config = ScalarConfig()

    scg1 = SimulationConfigGenerator(
        name="base",
        risk_segment_config=_risk_config(),
        dev_unit_bad_rate=_dev_unit_br(),
        dev_dollar_bad_rate=_dev_dollar_br(),
        test_unit_bad_rate=_test_unit_br(),
        test_dollar_bad_rate=_test_dollar_br(),
        bad_rate_type=LossRateTypes.ULR,
        scalar_config=scalar_config,
        filter_ids=(FilterID(int=1),),
        variable_name="score",
        variable_type=VariableType.NUMERICAL,
    )

    scg2 = scg1.with_updates(bad_rate_type=LossRateTypes.DLR)

    assert scg1.uid != scg2.uid


def test_simulation_config_hash_changes_when_segment_selected_toggles() -> None:
    """Test that toggling a segment's selected flag changes the config hash."""
    scalar_config = ScalarConfig()
    toggled_cfg = _risk_config().with_selected(
        next(iter(_risk_config().segments.keys())), False
    )

    c1 = SimulationConfig(
        risk_segment_config=_risk_config(),
        dev_unit_bad_rate=_dev_unit_br(),
        dev_dollar_bad_rate=_dev_dollar_br(),
        test_unit_bad_rate=_test_unit_br(),
        test_dollar_bad_rate=_test_dollar_br(),
        bad_rate_type=LossRateTypes.ULR,
        scalar_config=scalar_config,
        filter_ids=(FilterID(int=1),),
        variable_name="score",
        variable_type=VariableType.NUMERICAL,
    )
    c2 = SimulationConfig(
        risk_segment_config=toggled_cfg,
        dev_unit_bad_rate=_dev_unit_br(),
        dev_dollar_bad_rate=_dev_dollar_br(),
        test_unit_bad_rate=_test_unit_br(),
        test_dollar_bad_rate=_test_dollar_br(),
        bad_rate_type=LossRateTypes.ULR,
        scalar_config=scalar_config,
        filter_ids=(FilterID(int=1),),
        variable_name="score",
        variable_type=VariableType.NUMERICAL,
    )

    assert c1.uid != c2.uid


def test_dev_bad_rates_must_share_data_sources() -> None:
    """Dev unit and dollar bad rates must use the same data sources."""
    scalar_config = ScalarConfig()

    mismatched_dev_unit = _dev_unit_br().with_updates(
        data_source_ids=(DataSourceID(int=2),)
    )

    for cls in (SimulationConfig, SimulationConfigGenerator):
        kwargs = {
            "name": "base",
            "risk_segment_config": _risk_config(),
            "dev_unit_bad_rate": mismatched_dev_unit,
            "dev_dollar_bad_rate": _dev_dollar_br(),
            "test_unit_bad_rate": _test_unit_br(),
            "test_dollar_bad_rate": _test_dollar_br(),
            "bad_rate_type": LossRateTypes.ULR,
            "scalar_config": scalar_config,
            "filter_ids": (FilterID(int=1),),
            "variable_name": "score",
            "variable_type": VariableType.NUMERICAL,
        }
        if cls is SimulationConfig:
            kwargs.pop("name")
        try:
            cls(**kwargs)
            assert False, f"{cls.__name__} should have raised ValueError"
        except ValueError as e:
            assert "same data sources" in str(e)


def test_test_bad_rates_must_share_data_sources() -> None:
    """Test unit and dollar bad rates must use the same data sources."""
    scalar_config = ScalarConfig()

    mismatched_test_dollar = _test_dollar_br().with_updates(
        data_source_ids=(DataSourceID(int=2),)
    )

    for cls in (SimulationConfig, SimulationConfigGenerator):
        kwargs = {
            "name": "base",
            "risk_segment_config": _risk_config(),
            "dev_unit_bad_rate": _dev_unit_br(),
            "dev_dollar_bad_rate": _dev_dollar_br(),
            "test_unit_bad_rate": _test_unit_br(),
            "test_dollar_bad_rate": mismatched_test_dollar,
            "bad_rate_type": LossRateTypes.ULR,
            "scalar_config": scalar_config,
            "filter_ids": (FilterID(int=1),),
            "variable_name": "score",
            "variable_type": VariableType.NUMERICAL,
        }
        if cls is SimulationConfig:
            kwargs.pop("name")
        try:
            cls(**kwargs)
            assert False, f"{cls.__name__} should have raised ValueError"
        except ValueError as e:
            assert "same data sources" in str(e)


def test_bad_rate_data_source_equality_skipped_when_side_missing() -> None:
    """Data source equality is only enforced when both sides are present."""
    scalar_config = ScalarConfig()

    # Only dev unit present (no dev dollar): no validation error.
    sim = SimulationConfig(
        risk_segment_config=_risk_config(),
        dev_unit_bad_rate=_dev_unit_br(),
        dev_dollar_bad_rate=None,
        test_unit_bad_rate=None,
        test_dollar_bad_rate=None,
        bad_rate_type=LossRateTypes.ULR,
        scalar_config=scalar_config,
        filter_ids=(FilterID(int=1),),
        variable_name="score",
        variable_type=VariableType.NUMERICAL,
    )
    assert sim.dev_unit_bad_rate is not None
    assert sim.dev_dollar_bad_rate is None


def test_simulation_config_hash_changes_when_scalar_config_changes() -> None:
    """Test that changing the scalar config changes the config hash."""
    base_scalars = ScalarConfig()
    changed_scalars = ScalarConfig(
        ulr_scalar=base_scalars.ulr_scalar.model_copy(update={"current_rate": 0.015}),
        dlr_scalar=base_scalars.dlr_scalar,
    )

    c1 = SimulationConfig(
        risk_segment_config=_risk_config(),
        dev_unit_bad_rate=_dev_unit_br(),
        dev_dollar_bad_rate=_dev_dollar_br(),
        test_unit_bad_rate=_test_unit_br(),
        test_dollar_bad_rate=_test_dollar_br(),
        bad_rate_type=LossRateTypes.ULR,
        scalar_config=base_scalars,
        filter_ids=(FilterID(int=1),),
        variable_name="score",
        variable_type=VariableType.NUMERICAL,
    )
    c2 = SimulationConfig(
        risk_segment_config=_risk_config(),
        dev_unit_bad_rate=_dev_unit_br(),
        dev_dollar_bad_rate=_dev_dollar_br(),
        test_unit_bad_rate=_test_unit_br(),
        test_dollar_bad_rate=_test_dollar_br(),
        bad_rate_type=LossRateTypes.ULR,
        scalar_config=changed_scalars,
        filter_ids=(FilterID(int=1),),
        variable_name="score",
        variable_type=VariableType.NUMERICAL,
    )

    assert c1.uid != c2.uid
