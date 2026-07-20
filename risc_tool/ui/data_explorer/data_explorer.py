"""Data Explorer page for the RISC Tool Streamlit application."""

import streamlit as st

from risc_tool.data.models.enums import DataExplorerTabName
from risc_tool.data.session import Session
from risc_tool.ui.components.load_data_prompt import load_data_prompt
from risc_tool.ui.data_explorer.iv_analysis import iv_analysis
from risc_tool.ui.data_explorer.outlier import outlier_rules
from risc_tool.utils.logging import get_logger

logger = get_logger(__name__)


def data_explorer_view():
    """Render the Data Explorer page view.

    Provides functionality for analyzing variable strength (IV).
    """
    logger.info("Rendering Data Explorer view")
    session: Session = st.session_state["session"]
    de_view_model = session.data_explorer_view_model

    if not de_view_model.data_loaded:
        load_data_prompt()
        return

    st.title("Data Explorer")

    tab_names = [DataExplorerTabName.IV_ANALYSIS, DataExplorerTabName.OUTLIER_RULES]
    tabs = st.tabs(
        tabs=[tab.value for tab in tab_names],
        key="data-explorer-tabs",
        on_change="rerun",
    )
    for name, tab in zip(tab_names, tabs):
        if not tab.open:
            continue

        if name == DataExplorerTabName.IV_ANALYSIS:
            iv_analysis()
            break
        elif name == DataExplorerTabName.OUTLIER_RULES:
            outlier_rules()
            break


data_explorer_page = st.Page(
    page=data_explorer_view,
    title="Data Explorer",
    icon=":material/find_in_page:",
    url_path="/data-explorer",
)


__all__ = ["data_explorer_page"]
