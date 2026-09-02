"""Simulation package - main exports."""

from risc_tool_v2.data.simulation.models import (
    BadRateConfig,
    CategoricalGroup,
    GroupBase,
    LossRateScalar,
    NumericalGroup,
    RiskSegment,
    RiskSegmentConfig,
    ScalarConfig,
    Simulation,
    SimulationConfig,
    SimulationConfigGenerator,
    SimulationOutput,
    SimulationStatus,
    SupportsGroups,
    get_default_risk_segments,
    is_valid_hex_color,
    rebuild_group_dict,
)
from risc_tool_v2.data.simulation.repositories import SimulationRepository
from risc_tool_v2.data.simulation.services import (
    create_auto_categorical_bands,
    create_auto_numeric_bands,
    does_high_value_implies_high_risk,
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
    "SimulationRepository",
    "SimulationStatus",
    "SupportsGroups",
    "create_auto_categorical_bands",
    "create_auto_numeric_bands",
    "does_high_value_implies_high_risk",
    "get_default_risk_segments",
    "is_valid_hex_color",
    "rebuild_group_dict",
]
