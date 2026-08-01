"""Iterations page router for the RISC Tool application."""

import streamlit as st

from risc_tool.data.models.enums import IterationType
from risc_tool.data.session import Session
from risc_tool.ui.components.load_data_prompt import load_data_prompt
from risc_tool.ui.iterations.double_var_iteration import double_var_iteration
from risc_tool.ui.iterations.graph import iteration_graph
from risc_tool.ui.iterations.iteration_creator import iteration_creator
from risc_tool.ui.iterations.single_var_iteration import single_var_iteration
from risc_tool.utils.logging import get_logger

logger = get_logger(__name__)


def iterations_view() -> None:
    """Render the Iterations page view."""
    session: Session = st.session_state["session"]
    iterations_vm = session.iterations_view_model

    if not iterations_vm.data_loaded:
        load_data_prompt()
        return

    view, _ = iterations_vm.current_status

    if view == "view":
        if iterations_vm.current_iteration_type == IterationType.SINGLE:
            single_var_iteration()
        else:
            double_var_iteration()
    elif view == "create":
        iteration_creator()
    else:
        iteration_graph()


iterations_page = st.Page(
    page=iterations_view,
    title="Iterations",
    icon=":material/replay:",
    url_path="/iterations",
)

__all__ = ["iterations_page"]
