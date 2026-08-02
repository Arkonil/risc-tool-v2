"""Summary Dashboard page router for the RISC Tool application."""

import streamlit as st

from risc_tool.data.models.enums import SummaryPageTabName
from risc_tool.data.session import Session
from risc_tool.ui.components.load_data_prompt import load_data_prompt
from risc_tool.ui.summary.comparison import comparison
from risc_tool.ui.summary.no_summary_placeholder import no_summary_placeholder
from risc_tool.ui.summary.overview import overview
from risc_tool.ui.summary.pivot import pivot
from risc_tool.utils.logging import get_logger

logger = get_logger(__name__)


def summary_view() -> None:
    """Render the Summary Dashboard page view."""
    session: Session = st.session_state["session"]
    summary_vm = session.summary_view_model

    if not summary_vm.sample_loaded:
        logger.debug("Sample data not loaded; showing load_data_prompt in Summary")
        load_data_prompt()
        return

    if summary_vm.no_iteration:
        logger.debug("No iterations exist; showing no_summary_placeholder in Summary")
        no_summary_placeholder()
        return

    st.title("Summary Dashboard")

    tab_names = summary_vm.tab_names
    tabs = st.tabs(
        tabs=[tab.value for tab in tab_names],
        key="summary-page-tabs",
        on_change="rerun",
    )

    for tab_enum, tab in zip(tab_names, tabs):
        if not tab.open:
            continue

        summary_vm.current_tab_name = tab_enum

        if tab_enum == SummaryPageTabName.OVERVIEW:
            overview()
        elif tab_enum == SummaryPageTabName.COMPARISON:
            comparison()
        elif tab_enum == SummaryPageTabName.PIVOT:
            pivot()


summary_page = st.Page(
    page=summary_view,
    title="Summary Dashboard",
    icon=":material/dashboard:",
    url_path="/summary",
)

__all__ = ["summary_page"]
