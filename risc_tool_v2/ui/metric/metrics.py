"""Toggle between list view and edit view in the Metrics page."""

import streamlit as st

from risc_tool_v2.data.core.utils.logging import get_logger
from risc_tool_v2.data.session import Session
from risc_tool_v2.ui.core.components.load_data_prompt import load_data_prompt
from risc_tool_v2.ui.metric.metric_editor.metric_editor import metric_editor
from risc_tool_v2.ui.metric.metric_list.metric_list import metric_list

logger = get_logger(__name__)


def metrics_view():
    session: Session = st.session_state["session"]
    metric_editor_vm = session.metric_editor_view_model

    if not metric_editor_vm.data_loaded:
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


__all__ = ["metrics_page", "metrics_view"]
