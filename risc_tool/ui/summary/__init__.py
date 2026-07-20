"""Summary Dashboard page for the RISC Tool Streamlit application."""

import streamlit as st

from risc_tool.utils.logging import get_logger

logger = get_logger(__name__)


def summary_view():
    """Render the Summary Dashboard page view.

    Allows comparing multiple simulation iterations side-by-side using
    interactive metrics and charts.
    """
    logger.debug("Rendering Summary Dashboard view")
    st.title("Summary Dashboard")
    st.write(
        "Compare multiple simulation iterations side-by-side using interactive metrics and charts."
    )


summary_page = st.Page(
    page=summary_view,
    title="Summary Dashboard",
    icon=":material/dashboard:",
)


__all__ = ["summary_page"]
