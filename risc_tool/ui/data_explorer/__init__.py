"""Data Explorer page for the RISC Tool Streamlit application."""

import streamlit as st

from risc_tool.utils.logging import get_logger

logger = get_logger(__name__)


def data_explorer_view():
    """Render the Data Explorer page view.

    Provides functionality for analyzing variable strength (IV), inspecting
    distributions, managing outliers, and previewing unified data.
    """
    logger.info("Rendering Data Explorer view")
    st.title("Data Explorer")
    st.write(
        "Analyze variable strength (IV), inspect distributions, "
        "manage outliers, and preview your unified data."
    )


data_explorer_page = st.Page(
    page=data_explorer_view,
    title="Data Explorer",
    icon=":material/find_in_page:",
)


__all__ = ["data_explorer_page"]
