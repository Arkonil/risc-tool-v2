"""Simulation package exports."""

from risc_tool_v2.data.simulation.models.groups import (
    CategoricalGroup,
    GroupBase,
    NumericalGroup,
    SupportsGroups,
    rebuild_group_dict,
)
from risc_tool_v2.data.simulation.models.risk_segment import (
    RiskSegment,
    RiskSegmentConfig,
    get_default_risk_segments,
    is_valid_hex_color,
)
from risc_tool_v2.data.simulation.models.scalar import LossRateScalar, ScalarConfig
from risc_tool_v2.data.simulation.models.simulation import Simulation, SimulationStatus
from risc_tool_v2.data.simulation.models.simulation_config import (
    BadRateConfig,
    SimulationConfig,
    SimulationConfigGenerator,
    SimulationOutput,
)

__all__ = [
    "BadRateConfig",
    "CategoricalGroup",
    "GroupBase",
    "LossRateScalar",
    "NumericalGroup",
    "RiskSegment",
    "RiskSegmentConfig",
    "ScalarConfig",
    "Simulation",
    "SimulationConfig",
    "SimulationConfigGenerator",
    "SimulationOutput",
    "SimulationStatus",
    "SupportsGroups",
    "get_default_risk_segments",
    "is_valid_hex_color",
    "rebuild_group_dict",
]
