"""Simulation page router: graph view or create view."""

import streamlit as st

from risc_tool_v2.data.core.utils.logging import get_logger
from risc_tool_v2.ui.core.components.load_data_prompt import load_data_prompt
from risc_tool_v2.ui.core.session import get_session
from risc_tool_v2.ui.simulation.simulation_creator import simulation_creator
from risc_tool_v2.ui.simulation.simulation_graph import simulation_graph

logger = get_logger(__name__)


def simulations_view() -> None:
    session = get_session()
    simulation_vm = session.simulation_view_model

    if not simulation_vm.data_loaded:
        load_data_prompt()
        return

    if simulation_vm.mode == "create":
        simulation_creator()
        return

    simulation_graph()


simulation_page = st.Page(
    page=simulations_view,
    title="Simulations",
    icon=":material/science:",
    url_path="/simulations",
)

__all__ = ["simulation_page", "simulations_view"]
