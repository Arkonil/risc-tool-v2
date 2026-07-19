"""Filter Editor page for the RISC Tool Streamlit application."""

import streamlit as st

from risc_tool.utils.logging import get_logger

logger = get_logger(__name__)


def filters_view():
    """Render the Filter Editor page view.

    Allows building hierarchical population subsets to isolate and analyze
    specific risk cohorts.
    """
    logger.info("Rendering Filter Editor view")
    st.title("Filter Editor")
    st.write(
        "Build hierarchical population subsets to isolate and analyze specific risk cohorts."
    )


filter_page = st.Page(
    page=filters_view,
    title="Filter Editor",
    icon=":material/filter_alt:",
)


__all__ = ["filter_page"]
