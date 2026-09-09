"""Dedicated double-variable iteration creation page.

This is the v1-style creator page for layering a new double-variable iteration
over an existing one. All controls sit in the main area between a top-of-page
Back button and a Create button; the sidebars stay free of navigation.
"""

import streamlit as st

from risc_tool_v2.data.core.enums import VariableType
from risc_tool_v2.data.core.uid import IterationID, short_id
from risc_tool_v2.ui.core.session import get_session
from risc_tool_v2.ui.simulation.simulation_vm import SimulationViewModel


def _back_button(simulation_vm: SimulationViewModel) -> None:
    columns = st.columns([100, 900], vertical_alignment="center")
    with columns[0]:
        if st.button(
            label="Back",
            icon=":material/arrow_back_ios:",
            type="primary",
            key="iteration_creator_back",
        ):
            simulation_vm.cancel_iteration_create()
            st.rerun()


def _variable_selector(
    simulation_vm: SimulationViewModel, base_iteration_id: IterationID
) -> tuple[str, VariableType]:
    candidates = simulation_vm.double_var_candidate_columns(base_iteration_id)
    if not candidates:
        st.caption("No other common columns available for a double-variable iteration.")
        return "", VariableType.NUMERICAL
    names = [name for name, _ in candidates]
    name_to_type = dict(candidates)
    variable = st.selectbox(
        label="Variable",
        options=names,
        label_visibility="collapsed",
        key="iteration_creator_variable",
        placeholder="Select variable to band",
    )
    return variable, name_to_type[variable]


def simulation_iteration_creator() -> None:
    """Render the double-variable iteration creation page."""
    simulation_vm = get_session().simulation_view_model

    base = simulation_vm.iteration_create_base
    if base is None:
        simulation_vm.set_mode("graph")
        st.rerun()
        return

    simulation_vm.clear_errors()
    _back_button(simulation_vm)

    st.title("Create Double-Variable Iteration")
    st.caption(
        f"Base iteration **#{int(base.uid)}** · variable **{base.variable_name}** · "
        f"from Simulation **#{short_id(base.simulation_id)}**"
    )

    variable, variable_type = _variable_selector(simulation_vm, base.uid)

    col1, col2 = st.columns(2)
    with col1:
        upgrade_limit = st.number_input(
            label="Max Upgrades",
            min_value=0,
            max_value=10,
            value=2,
            step=1,
            key="iteration_creator_upgrade",
            help="Upgrade Current RT to a lower risk tier.",
        )
    with col2:
        downgrade_limit = st.number_input(
            label="Max Downgrades",
            min_value=0,
            max_value=10,
            value=2,
            step=1,
            key="iteration_creator_downgrade",
            help="Downgrade Current RT to a higher risk tier.",
        )
    auto_rank = st.checkbox(
        label="Auto-Rank Ordering",
        value=True,
        key="iteration_creator_auto_rank",
    )

    for error in simulation_vm.errors:
        st.error(error, icon=":material/error:")

    create_disabled = not variable
    if st.button(
        label="Create Double-Variable Iteration",
        type="primary",
        icon=":material/layers:",
        width="content",
        key="iteration_creator_create",
        disabled=create_disabled,
    ):
        try:
            simulation_vm.create_double_var_iteration(
                base.uid,
                new_variable_name=variable,
                new_variable_type=variable_type,
                upgrade_limit=int(upgrade_limit),
                downgrade_limit=int(downgrade_limit),
                auto_rank_ordering=auto_rank,
            )
            st.rerun()
        except ValueError as exc:
            simulation_vm.add_error(str(exc))
            st.rerun()


__all__ = ["simulation_iteration_creator"]
