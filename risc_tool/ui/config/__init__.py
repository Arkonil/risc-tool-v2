import streamlit as st

from risc_tool.utils.logging import get_logger

logger = get_logger(__name__)


def config_view():
    logger.info("Rendering Configuration view")
    st.title("Configuration")
    st.write(
        "Manage global settings, define modeling options, and configure scalar constants."
    )


config_page = st.Page(
    page=config_view,
    title="Configuration",
    icon=":material/settings:",
)


__all__ = ["config_page"]
