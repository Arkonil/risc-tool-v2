"""Home page for the RISC Tool Streamlit application."""

import streamlit as st

from risc_tool.utils.logging import get_logger

logger = get_logger(__name__)


def home_view():
    """Render the Home page view.

    Displays a welcome message and navigation hint.
    """
    logger.info("Rendering Home view")
    st.title("Home")
    st.write(
        "Welcome to the RisC Tool (Risk Identifier and Segmentation Creator). "
        "Use the sidebar to navigate to the different modules."
    )


home_page = st.Page(
    page=home_view,
    title="Home",
    icon=":material/home:",
    default=True,
)


__all__ = ["home_page"]

