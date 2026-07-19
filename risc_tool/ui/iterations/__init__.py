"""Iterations page for the RISC Tool Streamlit application."""

import streamlit as st

from risc_tool.utils.logging import get_logger

logger = get_logger(__name__)


def iterations_view():
    """Render the Iterations page view.

    Allows combining metrics and filters to prototype and simulate
    risk-tiering strategies with instant feedback on population volumes
    and performance metrics.
    """
    logger.info("Rendering Iterations view")
    st.title("Iterations")
    st.write(
        "Combine metrics and filters to prototype and simulate risk-tiering strategies. "
        "Get instant feedback on population volumes and performance metrics."
    )


iterations_page = st.Page(
    page=iterations_view,
    title="Iterations",
    icon=":material/replay:",
)


__all__ = ["iterations_page"]
