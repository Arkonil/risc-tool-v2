"""Variable Config high-level section for the Simulation Creator."""

import streamlit as st

from risc_tool_v2.data.simulation.models.simulation_config import (
    SimulationConfigGenerator,
)
from risc_tool_v2.ui.simulation import widgets
from risc_tool_v2.ui.simulation.simulation_creator.base import reconcile, vm


def variable_config_section(draft: SimulationConfigGenerator) -> None:
    """Variable selector (variable name, type, loss rate type)."""
    sim_vm = vm()

    col1, col2, col3 = st.columns([2, 2, 2])

    with col1:
        variable = widgets.variable_selector(draft.variable_name)
        reconcile(
            draft.variable_name,
            variable,
            lambda: sim_vm.update_draft_variable_name(variable),
        )

    with col2:
        variable_type = widgets.variable_type_selector(draft.variable_type)
        reconcile(
            draft.variable_type,
            variable_type,
            lambda: sim_vm.update_draft_variable_type(variable_type),
        )

    with col3:
        loss_rate_type = widgets.loss_rate_type_selector(draft.bad_rate_type)
        reconcile(
            draft.bad_rate_type,
            loss_rate_type,
            lambda: sim_vm.update_draft_bad_rate_type(loss_rate_type),
        )


__all__ = ["variable_config_section"]
