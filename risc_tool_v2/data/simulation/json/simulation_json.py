"""JSON serialization models for Simulation."""

import typing as t
from collections import OrderedDict
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from risc_tool_v2.data.core.enums import LossRateTypes, VariableType
from risc_tool_v2.data.core.uid import (
    DataSourceID,
    FilterID,
    RiskSegmentID,
    SimulationConfigGeneratorID,
    SimulationConfigID,
    SimulationID,
    SimulationOutputID,
)


class RiskSegmentJSON(BaseModel):
    model_config = ConfigDict(serialize_by_alias=True, validate_by_alias=True)

    name: str
    upper_rate: float
    bg_color: str
    font_color: str
    maf_dlr: float
    maf_ulr: float
    selected: bool = True


class RiskSegmentConfigJSON(BaseModel):
    model_config = ConfigDict(serialize_by_alias=True, validate_by_alias=True)

    segments: OrderedDict[RiskSegmentID, RiskSegmentJSON]


class LossRateScalarJSON(BaseModel):
    model_config = ConfigDict(serialize_by_alias=True, validate_by_alias=True)

    loss_rate_type: LossRateTypes
    current_rate: float | None = None
    lifetime_rate: float | None = None


class ScalarConfigJSON(BaseModel):
    model_config = ConfigDict(serialize_by_alias=True, validate_by_alias=True)

    ulr_scalar: LossRateScalarJSON
    dlr_scalar: LossRateScalarJSON


class BadRateConfigJSON(BaseModel):
    model_config = ConfigDict(serialize_by_alias=True, validate_by_alias=True)

    loss_rate_type: LossRateTypes
    numerator_col: str | None = None
    denominator_col: str | None = None
    current_rate_mob: int
    data_source_ids: list[DataSourceID]
    is_annualized: bool = True


class NumericalGroupJSON(BaseModel):
    model_config = ConfigDict(serialize_by_alias=True, validate_by_alias=True)

    type: t.Literal["numerical"] = "numerical"
    lower_bound: float
    upper_bound: float


class CategoricalGroupJSON(BaseModel):
    model_config = ConfigDict(serialize_by_alias=True, validate_by_alias=True)

    type: t.Literal["categorical"] = "categorical"
    categories: list[str]


GroupJSON = NumericalGroupJSON | CategoricalGroupJSON


class SimulationConfigJSON(BaseModel):
    model_config = ConfigDict(serialize_by_alias=True, validate_by_alias=True)

    uid: SimulationConfigID
    risk_segment_config: RiskSegmentConfigJSON
    dev_unit_bad_rate: BadRateConfigJSON | None = None
    dev_dollar_bad_rate: BadRateConfigJSON | None = None
    test_unit_bad_rate: BadRateConfigJSON | None = None
    test_dollar_bad_rate: BadRateConfigJSON | None = None
    bad_rate_type: LossRateTypes
    scalar_config: ScalarConfigJSON
    filter_ids: list[FilterID]
    remove_outliers: bool
    variable_name: str
    variable_type: VariableType
    auto_band: bool
    use_scalars: bool


class SimulationConfigGeneratorJSON(BaseModel):
    model_config = ConfigDict(serialize_by_alias=True, validate_by_alias=True)

    uid: SimulationConfigGeneratorID
    name: str
    risk_segment_config: RiskSegmentConfigJSON
    dev_unit_bad_rate: BadRateConfigJSON | None = None
    dev_dollar_bad_rate: BadRateConfigJSON | None = None
    test_unit_bad_rate: BadRateConfigJSON | None = None
    test_dollar_bad_rate: BadRateConfigJSON | None = None
    bad_rate_type: LossRateTypes
    scalar_config: ScalarConfigJSON
    filter_ids: list[FilterID]
    remove_outliers: bool
    variable_name: str
    variable_type: VariableType
    auto_band: bool
    use_scalars: bool
    lifetime_rate_mob: int = Field(default=36, ge=1)


class SimulationOutputJSON(BaseModel):
    model_config = ConfigDict(serialize_by_alias=True, validate_by_alias=True)

    uid: SimulationOutputID
    simulation_config_id: SimulationConfigID
    simulation_config_hash: SimulationConfigID
    variable_name: str
    variable_type: VariableType
    groups: OrderedDict[RiskSegmentID, GroupJSON]
    created_at: datetime
    is_valid: bool
    validation_warnings: list[str]


class SimulationJSON(BaseModel):
    model_config = ConfigDict(serialize_by_alias=True, validate_by_alias=True)

    uid: SimulationID
    simulation_config_generator_id: SimulationConfigGeneratorID
    status: str
    error_message: str | None = None
    created_at: datetime
    run_started_at: datetime | None = None
    run_completed_at: datetime | None = None


class SimulationRepositoryJSON(BaseModel):
    model_config = ConfigDict(serialize_by_alias=True, validate_by_alias=True)

    simulations: dict[SimulationID, SimulationJSON]
    generators: dict[SimulationConfigGeneratorID, SimulationConfigGeneratorJSON] = (
        Field(
            default_factory=dict[
                SimulationConfigGeneratorID, SimulationConfigGeneratorJSON
            ]
        )
    )
    outputs: dict[SimulationConfigID, SimulationOutputJSON] = Field(
        default_factory=dict[SimulationConfigID, SimulationOutputJSON]
    )


__all__ = [
    "BadRateConfigJSON",
    "CategoricalGroupJSON",
    "GroupJSON",
    "LossRateScalarJSON",
    "NumericalGroupJSON",
    "RiskSegmentConfigJSON",
    "RiskSegmentJSON",
    "ScalarConfigJSON",
    "SimulationConfigGeneratorJSON",
    "SimulationConfigJSON",
    "SimulationJSON",
    "SimulationOutputJSON",
    "SimulationRepositoryJSON",
]
