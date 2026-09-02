"""Simulation configuration models for SCG, SC, BadRateConfig, and SO."""

import json
import typing as t
from collections import OrderedDict
from datetime import datetime
from uuid import NAMESPACE_URL, uuid5

from pydantic import BaseModel, ConfigDict, Field, model_validator

from risc_tool_v2.data.core.enums import LossRateTypes, VariableType
from risc_tool_v2.data.core.uid import (
    DataSourceID,
    FilterID,
    GroupID,
    MetricID,
    SimulationConfigGeneratorID,
    SimulationConfigID,
    SimulationOutputID,
)
from risc_tool_v2.data.metric.models.metric import (
    DollarBadRate,
    Metric,
    UnitBadRate,
)
from risc_tool_v2.data.simulation.json.simulation_json import (
    BadRateConfigJSON,
    CategoricalGroupJSON,
    NumericalGroupJSON,
    SimulationConfigGeneratorJSON,
    SimulationConfigJSON,
    SimulationOutputJSON,
)
from risc_tool_v2.data.simulation.models.groups import (
    CategoricalGroup,
    NumericalGroup,
)
from risc_tool_v2.data.simulation.models.risk_segment import RiskSegmentConfig
from risc_tool_v2.data.simulation.models.scalar import ScalarConfig


class BadRateConfig(BaseModel, frozen=True):
    """Defines bad rate metric; produces Metric objects for efficient evaluation."""

    model_config = ConfigDict(extra="forbid")

    loss_rate_type: LossRateTypes
    numerator_col: str | None = None
    denominator_col: str | None = None
    current_rate_mob: int = Field(default=12, ge=1)
    data_source_ids: tuple[DataSourceID, ...] = Field(default_factory=tuple)
    is_annualized: bool = True

    @model_validator(mode="after")
    def _validate_test_bad_rate(self) -> "BadRateConfig":
        if not self.is_annualized and self.current_rate_mob != 12:
            raise ValueError("Test bad rates must have current_rate_mob=12")
        return self

    def to_metric(self, uid: MetricID, name: str) -> Metric:
        """Produce UnitBadRate or DollarBadRate Metric for evaluation."""
        if self.loss_rate_type == LossRateTypes.ULR:
            return UnitBadRate(
                var_unt_bad=self.numerator_col,
                current_rate_mob=self.current_rate_mob,
                data_source_ids=list(self.data_source_ids),
                uid=uid,
                name=name,
            )
        else:
            return DollarBadRate(
                var_dlr_bad=self.numerator_col,
                var_avg_bal=self.denominator_col,
                current_rate_mob=self.current_rate_mob,
                data_source_ids=list(self.data_source_ids),
                uid=uid,
                name=name,
            )

    def with_updates(self, **updates: t.Any) -> "BadRateConfig":
        """Return a copy of this config with updated fields."""
        fields: dict[str, t.Any] = {
            "loss_rate_type": self.loss_rate_type,
            "numerator_col": self.numerator_col,
            "denominator_col": self.denominator_col,
            "current_rate_mob": self.current_rate_mob,
            "data_source_ids": self.data_source_ids,
            "is_annualized": self.is_annualized,
        }
        fields.update(updates)
        return BadRateConfig(**fields)

    def to_dict(self) -> BadRateConfigJSON:
        return BadRateConfigJSON(
            loss_rate_type=self.loss_rate_type,
            numerator_col=self.numerator_col,
            denominator_col=self.denominator_col,
            current_rate_mob=self.current_rate_mob,
            data_source_ids=list(self.data_source_ids),
            is_annualized=self.is_annualized,
        )

    @classmethod
    def from_dict(cls, data: BadRateConfigJSON) -> t.Self:
        return cls(
            loss_rate_type=data.loss_rate_type,
            numerator_col=data.numerator_col,
            denominator_col=data.denominator_col,
            current_rate_mob=data.current_rate_mob,
            data_source_ids=tuple(data.data_source_ids),
            is_annualized=data.is_annualized,
        )


def _validate_bad_rate_data_sources(
    *,
    unit_bad_rate: BadRateConfig | None,
    dollar_bad_rate: BadRateConfig | None,
    label: str,
) -> None:
    """Raise ValueError if unit and dollar bad rates use different data sources.

    Both unit and dollar bad rates for a group (target/dev or early/test) must
    reference the same data sources. The check is skipped when either side is
    unconfigured.
    """
    if unit_bad_rate is None or dollar_bad_rate is None:
        return
    if unit_bad_rate.data_source_ids != dollar_bad_rate.data_source_ids:
        raise ValueError(
            f"{label} unit and dollar bad rate configurations must use the "
            "same data sources."
        )


def _validate_bad_rate_mob(
    *,
    unit_bad_rate: BadRateConfig | None,
    dollar_bad_rate: BadRateConfig | None,
    label: str,
) -> None:
    """Raise ValueError if unit and dollar bad rates use different current-rate MOBs.

    Both unit and dollar bad rates for a group (target/dev or early/test) share a
    single current-rate MOB value. The check is skipped when either side is
    unconfigured.
    """
    if unit_bad_rate is None or dollar_bad_rate is None:
        return
    if unit_bad_rate.current_rate_mob != dollar_bad_rate.current_rate_mob:
        raise ValueError(
            f"{label} unit and dollar bad rate configurations must use the "
            "same current rate MOB."
        )


class SimulationConfig(BaseModel, frozen=True):
    """Single simulation config - fully defines one run; content-hashed for caching."""

    model_config = ConfigDict(extra="forbid")

    uid: SimulationConfigID = SimulationConfigID.UNSET

    # Core configuration (all frozen, self-contained)
    risk_segment_config: RiskSegmentConfig
    dev_unit_bad_rate: BadRateConfig | None = None
    dev_dollar_bad_rate: BadRateConfig | None = None
    test_unit_bad_rate: BadRateConfig | None = None
    test_dollar_bad_rate: BadRateConfig | None = None
    bad_rate_type: LossRateTypes = LossRateTypes.ULR
    scalar_config: ScalarConfig
    filter_ids: tuple[FilterID, ...] = Field(default_factory=tuple)
    remove_outliers: bool = True

    # Input variable
    variable_name: str
    variable_type: VariableType

    # Banding behavior
    auto_band: bool = True
    use_scalars: bool = True

    def _selected_dev_bad_rate(self) -> BadRateConfig | None:
        """Return the selected dev bad rate based on bad_rate_type."""
        if self.bad_rate_type == LossRateTypes.ULR:
            return self.dev_unit_bad_rate
        return self.dev_dollar_bad_rate

    def create_hash(self) -> SimulationConfigID:
        """Return a content-addressed ID derived from this config's content."""
        selected_br = self._selected_dev_bad_rate()

        bad_rate_hash = None
        if selected_br is not None:
            metric = selected_br.to_metric(
                uid=MetricID.TEMPORARY,
                name=f"sim_bad_rate_{selected_br.loss_rate_type.value}",
            )
            bad_rate_hash = str(metric.create_hash())

        payload = json.dumps(
            {
                "risk_segment_config_hash": self.risk_segment_config.create_hash(),
                "bad_rate_config_hash": bad_rate_hash,
                "scalar_config_hash": self.scalar_config.create_hash(),
                "filter_ids": sorted(str(fid) for fid in self.filter_ids),
                "remove_outliers": self.remove_outliers,
                "variable_name": self.variable_name,
                "variable_type": self.variable_type.value,
                "auto_band": self.auto_band,
                "use_scalars": self.use_scalars,
            },
            sort_keys=True,
            default=str,
        )
        return SimulationConfigID(uuid5(NAMESPACE_URL, payload))

    @model_validator(mode="after")
    def _validate_data_source_equality(self) -> "SimulationConfig":
        _validate_bad_rate_data_sources(
            unit_bad_rate=self.dev_unit_bad_rate,
            dollar_bad_rate=self.dev_dollar_bad_rate,
            label="Dev",
        )
        _validate_bad_rate_data_sources(
            unit_bad_rate=self.test_unit_bad_rate,
            dollar_bad_rate=self.test_dollar_bad_rate,
            label="Test",
        )
        _validate_bad_rate_mob(
            unit_bad_rate=self.dev_unit_bad_rate,
            dollar_bad_rate=self.dev_dollar_bad_rate,
            label="Dev",
        )
        _validate_bad_rate_mob(
            unit_bad_rate=self.test_unit_bad_rate,
            dollar_bad_rate=self.test_dollar_bad_rate,
            label="Test",
        )
        return self

    @model_validator(mode="after")
    def _derive_uid(self) -> "SimulationConfig":
        if self.uid is SimulationConfigID.UNSET:
            object.__setattr__(self, "uid", self.create_hash())
        return self

    def with_updates(self, **updates: t.Any) -> "SimulationConfig":
        """Return a copy of this config with updated fields."""
        fields: dict[str, t.Any] = {
            "risk_segment_config": self.risk_segment_config,
            "dev_unit_bad_rate": self.dev_unit_bad_rate,
            "dev_dollar_bad_rate": self.dev_dollar_bad_rate,
            "test_unit_bad_rate": self.test_unit_bad_rate,
            "test_dollar_bad_rate": self.test_dollar_bad_rate,
            "bad_rate_type": self.bad_rate_type,
            "scalar_config": self.scalar_config,
            "filter_ids": self.filter_ids,
            "remove_outliers": self.remove_outliers,
            "variable_name": self.variable_name,
            "variable_type": self.variable_type,
            "auto_band": self.auto_band,
            "use_scalars": self.use_scalars,
        }
        fields.update(updates)
        return SimulationConfig(**fields)

    def to_dict(self) -> "SimulationConfigJSON":
        def bad_rate_to_json(br: BadRateConfig | None):
            return br.to_dict() if br is not None else None

        return SimulationConfigJSON(
            uid=self.uid,
            risk_segment_config=self.risk_segment_config.to_dict(),
            dev_unit_bad_rate=bad_rate_to_json(self.dev_unit_bad_rate),
            dev_dollar_bad_rate=bad_rate_to_json(self.dev_dollar_bad_rate),
            test_unit_bad_rate=bad_rate_to_json(self.test_unit_bad_rate),
            test_dollar_bad_rate=bad_rate_to_json(self.test_dollar_bad_rate),
            bad_rate_type=self.bad_rate_type,
            scalar_config=self.scalar_config.to_dict(),
            filter_ids=list(self.filter_ids),
            remove_outliers=self.remove_outliers,
            variable_name=self.variable_name,
            variable_type=self.variable_type,
            auto_band=self.auto_band,
            use_scalars=self.use_scalars,
        )

    @classmethod
    def from_dict(cls, data: "SimulationConfigJSON") -> "SimulationConfig":
        def json_to_bad_rate(br_json: BadRateConfigJSON | None) -> BadRateConfig | None:
            return BadRateConfig.from_dict(br_json) if br_json is not None else None

        return cls(
            uid=data.uid,
            risk_segment_config=RiskSegmentConfig.from_dict(data.risk_segment_config),
            dev_unit_bad_rate=json_to_bad_rate(data.dev_unit_bad_rate),
            dev_dollar_bad_rate=json_to_bad_rate(data.dev_dollar_bad_rate),
            test_unit_bad_rate=json_to_bad_rate(data.test_unit_bad_rate),
            test_dollar_bad_rate=json_to_bad_rate(data.test_dollar_bad_rate),
            bad_rate_type=data.bad_rate_type,
            scalar_config=ScalarConfig.from_dict(data.scalar_config),
            filter_ids=tuple(data.filter_ids),
            remove_outliers=data.remove_outliers,
            variable_name=data.variable_name,
            variable_type=data.variable_type,
            auto_band=data.auto_band,
            use_scalars=data.use_scalars,
        )


class SimulationConfigGenerator(BaseModel, frozen=True):
    """Generates multiple SCs (hyperparameter tuning style); initially 1 SC."""

    model_config = ConfigDict(extra="forbid")

    uid: SimulationConfigGeneratorID = SimulationConfigGeneratorID.UNSET
    name: str

    # Core configuration (all frozen, self-contained)
    risk_segment_config: RiskSegmentConfig
    dev_unit_bad_rate: BadRateConfig | None = None
    dev_dollar_bad_rate: BadRateConfig | None = None
    test_unit_bad_rate: BadRateConfig | None = None
    test_dollar_bad_rate: BadRateConfig | None = None
    bad_rate_type: LossRateTypes = LossRateTypes.ULR
    scalar_config: ScalarConfig
    filter_ids: tuple[FilterID, ...] = Field(default_factory=tuple)
    remove_outliers: bool = True

    # Input variable
    variable_name: str
    variable_type: VariableType

    # Banding behavior
    auto_band: bool = True
    use_scalars: bool = True

    # Metadata (not used in calculations)
    lifetime_rate_mob: int = Field(default=36, ge=1)

    def create_hash(self) -> SimulationConfigGeneratorID:
        """Return a content-addressed ID derived from this generator's content."""

        def bad_rate_hash(br: BadRateConfig | None) -> str | None:
            if br is None:
                return None
            metric = br.to_metric(
                uid=MetricID.TEMPORARY,
                name=f"scg_bad_rate_{br.loss_rate_type.value}",
            )
            return str(metric.create_hash())

        payload = json.dumps(
            {
                "name": self.name,
                "risk_segment_config_hash": self.risk_segment_config.create_hash(),
                "dev_unit_bad_rate_hash": bad_rate_hash(self.dev_unit_bad_rate),
                "dev_dollar_bad_rate_hash": bad_rate_hash(self.dev_dollar_bad_rate),
                "test_unit_bad_rate_hash": bad_rate_hash(self.test_unit_bad_rate),
                "test_dollar_bad_rate_hash": bad_rate_hash(self.test_dollar_bad_rate),
                "bad_rate_type": self.bad_rate_type.value,
                "scalar_config_hash": self.scalar_config.create_hash(),
                "filter_ids": sorted(str(fid) for fid in self.filter_ids),
                "remove_outliers": self.remove_outliers,
                "variable_name": self.variable_name,
                "variable_type": self.variable_type.value,
                "auto_band": self.auto_band,
                "use_scalars": self.use_scalars,
                "lifetime_rate_mob": self.lifetime_rate_mob,
            },
            sort_keys=True,
            default=str,
        )
        return SimulationConfigGeneratorID(uuid5(NAMESPACE_URL, payload))

    @model_validator(mode="after")
    def _validate_data_source_equality(self) -> "SimulationConfigGenerator":
        _validate_bad_rate_data_sources(
            unit_bad_rate=self.dev_unit_bad_rate,
            dollar_bad_rate=self.dev_dollar_bad_rate,
            label="Dev",
        )
        _validate_bad_rate_data_sources(
            unit_bad_rate=self.test_unit_bad_rate,
            dollar_bad_rate=self.test_dollar_bad_rate,
            label="Test",
        )
        _validate_bad_rate_mob(
            unit_bad_rate=self.dev_unit_bad_rate,
            dollar_bad_rate=self.dev_dollar_bad_rate,
            label="Dev",
        )
        _validate_bad_rate_mob(
            unit_bad_rate=self.test_unit_bad_rate,
            dollar_bad_rate=self.test_dollar_bad_rate,
            label="Test",
        )
        return self

    @model_validator(mode="after")
    def _derive_uid(self) -> "SimulationConfigGenerator":
        if self.uid is SimulationConfigGeneratorID.UNSET:
            object.__setattr__(self, "uid", self.create_hash())
        return self

    def with_updates(self, **updates: t.Any) -> "SimulationConfigGenerator":
        """Return a copy of this generator with updated fields."""
        fields: dict[str, t.Any] = {
            "name": self.name,
            "risk_segment_config": self.risk_segment_config,
            "dev_unit_bad_rate": self.dev_unit_bad_rate,
            "dev_dollar_bad_rate": self.dev_dollar_bad_rate,
            "test_unit_bad_rate": self.test_unit_bad_rate,
            "test_dollar_bad_rate": self.test_dollar_bad_rate,
            "bad_rate_type": self.bad_rate_type,
            "scalar_config": self.scalar_config,
            "filter_ids": self.filter_ids,
            "remove_outliers": self.remove_outliers,
            "variable_name": self.variable_name,
            "variable_type": self.variable_type,
            "auto_band": self.auto_band,
            "use_scalars": self.use_scalars,
            "lifetime_rate_mob": self.lifetime_rate_mob,
        }
        fields.update(updates)
        return SimulationConfigGenerator(**fields)

    def get_configs(self) -> tuple[SimulationConfig, ...]:
        """Generate simulation configs from this generator; currently returns one."""
        return (
            SimulationConfig(
                risk_segment_config=self.risk_segment_config,
                dev_unit_bad_rate=self.dev_unit_bad_rate,
                dev_dollar_bad_rate=self.dev_dollar_bad_rate,
                test_unit_bad_rate=self.test_unit_bad_rate,
                test_dollar_bad_rate=self.test_dollar_bad_rate,
                bad_rate_type=self.bad_rate_type,
                scalar_config=self.scalar_config,
                filter_ids=self.filter_ids,
                remove_outliers=self.remove_outliers,
                variable_name=self.variable_name,
                variable_type=self.variable_type,
                auto_band=self.auto_band,
                use_scalars=self.use_scalars,
            ),
        )

    def to_dict(self) -> "SimulationConfigGeneratorJSON":
        def bad_rate_to_json(br: BadRateConfig | None):
            return br.to_dict() if br is not None else None

        return SimulationConfigGeneratorJSON(
            uid=self.uid,
            name=self.name,
            risk_segment_config=self.risk_segment_config.to_dict(),
            dev_unit_bad_rate=bad_rate_to_json(self.dev_unit_bad_rate),
            dev_dollar_bad_rate=bad_rate_to_json(self.dev_dollar_bad_rate),
            test_unit_bad_rate=bad_rate_to_json(self.test_unit_bad_rate),
            test_dollar_bad_rate=bad_rate_to_json(self.test_dollar_bad_rate),
            bad_rate_type=self.bad_rate_type,
            scalar_config=self.scalar_config.to_dict(),
            filter_ids=list(self.filter_ids),
            remove_outliers=self.remove_outliers,
            variable_name=self.variable_name,
            variable_type=self.variable_type,
            auto_band=self.auto_band,
            use_scalars=self.use_scalars,
            lifetime_rate_mob=self.lifetime_rate_mob,
        )

    @classmethod
    def from_dict(
        cls, data: "SimulationConfigGeneratorJSON"
    ) -> "SimulationConfigGenerator":
        def json_to_bad_rate(br_json: BadRateConfigJSON | None) -> BadRateConfig | None:
            return BadRateConfig.from_dict(br_json) if br_json is not None else None

        return cls(
            uid=data.uid,
            name=data.name,
            risk_segment_config=RiskSegmentConfig.from_dict(data.risk_segment_config),
            dev_unit_bad_rate=json_to_bad_rate(data.dev_unit_bad_rate),
            dev_dollar_bad_rate=json_to_bad_rate(data.dev_dollar_bad_rate),
            test_unit_bad_rate=json_to_bad_rate(data.test_unit_bad_rate),
            test_dollar_bad_rate=json_to_bad_rate(data.test_dollar_bad_rate),
            bad_rate_type=data.bad_rate_type,
            scalar_config=ScalarConfig.from_dict(data.scalar_config),
            filter_ids=tuple(data.filter_ids),
            remove_outliers=data.remove_outliers,
            variable_name=data.variable_name,
            variable_type=data.variable_type,
            auto_band=data.auto_band,
            use_scalars=data.use_scalars,
            lifetime_rate_mob=data.lifetime_rate_mob,
        )


class SimulationOutput(BaseModel, frozen=True):
    """Immutable output of one simulation run - just grouping definitions."""

    model_config = ConfigDict(extra="forbid")

    uid: SimulationOutputID = SimulationOutputID.UNSET
    simulation_config_id: SimulationConfigID
    simulation_config_hash: SimulationConfigID

    # Single grouping (no default_groups distinction - immutable)
    variable_name: str
    variable_type: VariableType
    groups: OrderedDict[GroupID, NumericalGroup | CategoricalGroup]

    # Metadata
    created_at: datetime = Field(default_factory=datetime.now)
    is_valid: bool = True
    validation_warnings: tuple[str, ...] = Field(default_factory=tuple)

    def create_hash(self) -> SimulationOutputID:
        """Return a content-addressed ID derived from this output's content."""
        payload = json.dumps(
            {
                "simulation_config_id": str(self.simulation_config_id),
                "simulation_config_hash": str(self.simulation_config_hash),
                "variable_name": self.variable_name,
                "variable_type": self.variable_type.value,
                "groups": {
                    str(gid): {
                        "type": "numerical"
                        if isinstance(g, NumericalGroup)
                        else "categorical",
                        "lower_bound": g.lower_bound
                        if isinstance(g, NumericalGroup)
                        else None,
                        "upper_bound": g.upper_bound
                        if isinstance(g, NumericalGroup)
                        else None,
                        "categories": sorted(g.categories)
                        if isinstance(g, CategoricalGroup)
                        else None,
                    }
                    for gid, g in self.groups.items()
                },
                "created_at": self.created_at.isoformat(),
                "is_valid": self.is_valid,
                "validation_warnings": list(self.validation_warnings),
            },
            sort_keys=True,
            default=str,
        )
        return SimulationOutputID(uuid5(NAMESPACE_URL, payload))

    @model_validator(mode="after")
    def _derive_uid(self) -> "SimulationOutput":
        if self.uid is SimulationOutputID.UNSET:
            object.__setattr__(self, "uid", self.create_hash())
        return self

    def with_updates(self, **updates: t.Any) -> "SimulationOutput":
        """Return a copy of this output with updated fields."""
        fields: dict[str, t.Any] = {
            "simulation_config_id": self.simulation_config_id,
            "simulation_config_hash": self.simulation_config_hash,
            "variable_name": self.variable_name,
            "variable_type": self.variable_type,
            "groups": self.groups,
            "created_at": self.created_at,
            "is_valid": self.is_valid,
            "validation_warnings": self.validation_warnings,
        }
        fields.update(updates)
        return SimulationOutput(**fields)

    def to_dict(self) -> "SimulationOutputJSON":
        return SimulationOutputJSON(
            uid=self.uid,
            simulation_config_id=self.simulation_config_id,
            simulation_config_hash=self.simulation_config_hash,
            variable_name=self.variable_name,
            variable_type=self.variable_type,
            groups=OrderedDict(
                (
                    gid,
                    NumericalGroupJSON(
                        type="numerical",
                        lower_bound=g.lower_bound,
                        upper_bound=g.upper_bound,
                    )
                    if isinstance(g, NumericalGroup)
                    else CategoricalGroupJSON(
                        type="categorical",
                        categories=sorted(g.categories),
                    ),
                )
                for gid, g in self.groups.items()
            ),
            created_at=self.created_at,
            is_valid=self.is_valid,
            validation_warnings=list(self.validation_warnings),
        )

    @classmethod
    def from_dict(cls, data: "SimulationOutputJSON") -> "SimulationOutput":
        groups: OrderedDict[GroupID, NumericalGroup | CategoricalGroup] = OrderedDict()
        for gid, group_json in data.groups.items():
            if group_json.type == "numerical":
                num_json = group_json
                groups[gid] = NumericalGroup(
                    lower_bound=num_json.lower_bound, upper_bound=num_json.upper_bound
                )
            else:
                cat_json = group_json
                groups[gid] = CategoricalGroup(
                    categories=frozenset(cat_json.categories)
                )

        return cls(
            uid=data.uid,
            simulation_config_id=data.simulation_config_id,
            simulation_config_hash=data.simulation_config_hash,
            variable_name=data.variable_name,
            variable_type=data.variable_type,
            groups=groups,
            created_at=data.created_at,
            is_valid=data.is_valid,
            validation_warnings=tuple(data.validation_warnings),
        )


__all__ = [
    "BadRateConfig",
    "ScalarConfig",
    "SimulationConfig",
    "SimulationConfigGenerator",
    "SimulationOutput",
]
