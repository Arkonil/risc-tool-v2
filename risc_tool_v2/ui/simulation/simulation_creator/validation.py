"""Draft validation for the Simulation Creator."""

from risc_tool_v2.data.core.enums import LossRateTypes
from risc_tool_v2.data.simulation.models.simulation_config import (
    SimulationConfigGenerator,
)


def get_selected_bad_rate(
    scg: SimulationConfigGenerator, loss_rate_type: LossRateTypes
):
    if loss_rate_type == LossRateTypes.ULR:
        return scg.dev_unit_bad_rate
    return scg.dev_dollar_bad_rate


def validate(scg: SimulationConfigGenerator) -> list[str]:
    errors: list[str] = []
    if not scg.name.strip():
        errors.append("Simulation name cannot be empty.")
    if not scg.variable_name.strip():
        errors.append("Please select a variable.")
    selected_br = get_selected_bad_rate(scg, scg.bad_rate_type)
    if selected_br is None or not selected_br.numerator_col:
        errors.append("Please configure the bad rate numerator column.")
    if scg.bad_rate_type == LossRateTypes.DLR and (
        selected_br is None or not selected_br.denominator_col
    ):
        errors.append("Please configure the bad rate denominator column.")
    if not scg.risk_segment_config.segments:
        errors.append("At least one risk segment is required.")
    return errors


__all__ = ["get_selected_bad_rate", "validate"]
