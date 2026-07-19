"""Data Importer page for the RISC Tool Streamlit application.

This module renders the main Data Importer UI, which allows users to add,
configure, and preview data sources.
"""

import streamlit as st

from risc_tool.data.session import Session
from risc_tool.ui.data_importer.data_selector import data_selector
from risc_tool.ui.data_importer.data_viewer import data_viewer
from risc_tool.utils.logging import get_logger

logger = get_logger(__name__)


def data_importer_view():
    """Render the Data Importer page.

    Displays the data source selector and, if sources are configured,
    the data preview viewer.
    """
    logger.info("Rendering Data Importer page")
    session: Session = st.session_state["session"]
    data_importer_view_model = session.data_importer_view_model

    st.title("Data Importer")

    st.subheader("Select Data Sources")
    data_selector()

    if data_importer_view_model.is_empty:
        return

    st.space()

    data_viewer()

    st.space()

    st.subheader("Variable Selector")
    # with st.container(border=True):
    #     variable_selector()


data_importer_page = st.Page(
    page=data_importer_view,
    title="Data Importer",
    icon=":material/upload:",
    url_path="/data-importer",
)


__all__ = ["data_importer_page"]
