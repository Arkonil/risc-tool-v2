"""Streamlit page configuration and styling."""

import streamlit as st

from risc_tool.data.models.asset_path import AssetPath
from risc_tool.utils.logging import get_logger

logger = get_logger(__name__)


def set_page_config() -> None:
    """Configure the Streamlit page settings and apply custom styling.

    Sets the page title, icon, layout, and logo based on the current theme.
    Also injects the custom CSS stylesheet.
    """
    if st.context.theme.get("type") == "dark":
        logo_path = AssetPath.APP_LOGO_DARK
    else:
        logo_path = AssetPath.APP_LOGO_LIGHT

    try:
        with open(logo_path, "r") as fp:
            st.logo(fp.read(), size="large")
    except Exception:
        logger.exception("Failed to read app logo from %s", logo_path)

    st.set_page_config(
        page_title="RisC Tool",
        page_icon=AssetPath.APP_ICON,
        layout="wide",
    )

    try:
        with open(AssetPath.STYLESHEET, encoding="utf-8") as file:
            st.html(f"<style>{file.read()}</style>")
    except Exception:
        logger.exception("Failed to read stylesheet from %s", AssetPath.STYLESHEET)
