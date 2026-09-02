"""Data Importer page for the risc-tool-v2 Streamlit application."""

import streamlit as st

from risc_tool_v2.data.core.utils.logging import get_logger
from risc_tool_v2.ui.core.session import get_session
from risc_tool_v2.ui.data_source.data_importer.data_selector import data_selector
from risc_tool_v2.ui.data_source.data_importer.data_viewer import data_viewer

logger = get_logger(__name__)


def data_importer_view():
    logger.debug("Rendering Data Importer page")
    session = get_session()
    data_importer_view_model = session.data_importer_view_model

    st.title("Data Importer")

    st.subheader("Select Data Sources")
    data_selector()

    if data_importer_view_model.is_empty:
        return

    st.space()
    data_viewer()


data_importer_page = st.Page(
    page=data_importer_view,
    title="Data Importer",
    icon=":material/upload:",
    url_path="/data-importer",
)


__all__ = ["data_importer_page", "data_importer_view"]
