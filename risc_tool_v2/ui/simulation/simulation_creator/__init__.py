"""Simulation Creator page.

A single-column, top-to-bottom creation flow composed of self-contained
high-level section components. Each section reads the current draft from the
SimulationViewModel (via session state), renders prop-driven low-level widgets,
and on an edit reconciles the returned value against the draft field by calling
the matching per-field ViewModel update method followed by ``st.rerun()``. Only
the ViewModel talks to repositories; section components never mutate the draft
directly.
"""

import streamlit as st

from risc_tool_v2.ui.data_source.data_explorer.iv_analysis import iv_analysis
from risc_tool_v2.ui.simulation.simulation_creator import (
    bad_rate_config,
    iteration_inputs,
    risk_segment_config,
    scalar_config,
    validation,
    variable_config,
)
from risc_tool_v2.ui.simulation.simulation_creator.base import vm


def _back_button() -> None:
    simulation_vm = vm()
    columns = st.columns([100, 900], vertical_alignment="center")
    with columns[0]:
        if st.button(
            label="Back",
            icon=":material/arrow_back_ios:",
            type="primary",
        ):
            if simulation_vm.is_editing:
                simulation_vm.cancel_edit_draft()
            else:
                simulation_vm.clear_draft()
            simulation_vm.set_mode("graph")
            st.rerun()


def simulation_creator() -> None:
    """Render the simulation creation flow; persist draft via the VM."""
    simulation_vm = vm()
    simulation_vm.clear_errors()

    _back_button()

    if simulation_vm.is_editing:
        st.title("Edit Simulation")
    else:
        st.title("Create New Simulation")

    draft = simulation_vm.draft_scg

    try:
        bad_rate_config.bad_rate_config_section(draft)
        st.divider()

        risk_segment_config.risk_segment_config_section(draft)
        st.divider()

        scalar_config.scalar_config_section(draft)
        st.divider()

        with st.expander("Information Value (Reference)", expanded=False):
            iv_analysis()

        variable_config.variable_config_section(draft)
        iteration_inputs.iteration_inputs_section(draft)
    except Exception as exc:  # noqa: BLE001 - surface unexpected errors to the page
        simulation_vm.add_error(f"Unexpected error: {exc}")

    draft = simulation_vm.draft_scg
    for err in validation.validate(draft):
        simulation_vm.add_error(err)

    st.divider()

    errors = simulation_vm.errors
    if errors:
        body = "\n".join(f"- {err}" for err in errors)
        st.error(body, icon=":material/error:")

    with st.expander("Debug: Full Current SCG", expanded=False):
        st.json(draft.model_dump_json())

    st.divider()

    if st.button(
        label="Save Changes" if simulation_vm.is_editing else "Create New Simulation",
        type="primary",
        icon=":material/save:" if simulation_vm.is_editing else ":material/add:",
        width="content",
        disabled=bool(errors),
    ):
        simulation_vm.confirm_draft()
        st.rerun()


__all__ = ["simulation_creator"]
