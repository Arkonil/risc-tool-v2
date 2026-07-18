import streamlit as st

from risc_tool.utils.logging import get_logger

logger = get_logger(__name__)


def summary_view():
    logger.info("Rendering Summary Dashboard view")
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
