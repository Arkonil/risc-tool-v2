"""Toggle between list view and edit view in the Metrics page."""

import streamlit as st

from risc_tool.data.session import Session
from risc_tool.ui.components.load_data_prompt import load_data_prompt
from risc_tool.ui.metrics.metric_editor import metric_editor
from risc_tool.ui.metrics.metric_list import metric_list
from risc_tool.utils.logging import get_logger

logger = get_logger(__name__)


def metrics_view():
    """Toggle between list view and edit view in the Metrics page."""
    session: Session = st.session_state["session"]
    metric_editor_vm = session.metric_editor_view_model

    if not metric_editor_vm.data_loaded:
        logger.debug("No data loaded; showing load data prompt in metrics page")
        load_data_prompt()
        return

    logger.debug("Metrics page in mode: %s", metric_editor_vm.mode)
    if metric_editor_vm.mode == "view":
        metric_list()
    else:
        metric_editor()


metrics_page = st.Page(
    page=metrics_view,
    title="Metrics",
    icon=":material/analytics:",
    url_path="/metrics",
)


__all__ = ["metrics_page"]
