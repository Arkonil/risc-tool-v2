"""Metrics Editor page for the RISC Tool Streamlit application."""

import streamlit as st

from risc_tool.utils.logging import get_logger

logger = get_logger(__name__)


def metrics_view():
    """Render the Metrics Editor page view.

    Allows defining complex, expression-based metrics using a Python-like
    syntax (e.g., Annualized Bad Rates, Dollar Loss).
    """
    logger.debug("Rendering Metrics Editor view")
    st.title("Metrics Editor")
    st.write(
        "Define complex, expression-based metrics using a Python-like syntax "
        "(e.g., Annualized Bad Rates, Dollar Loss)."
    )


metrics_page = st.Page(
    page=metrics_view,
    title="Metrics Editor",
    icon=":material/edit:",
)


__all__ = ["metrics_page"]
