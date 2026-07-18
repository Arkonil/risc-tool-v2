import streamlit as st

from risc_tool.utils.logging import get_logger

logger = get_logger(__name__)


def documentation_view():
    logger.info("Rendering Documentation view")
    st.title("Documentation")
    st.write(
        "Access comprehensive user guides, references for metric and filter syntax, "
        "and strategies on data cleaning and exporting."
    )


documentation_page = st.Page(
    page=documentation_view,
    title="Documentation",
    icon=":material/description:",
)


__all__ = ["documentation_page"]
