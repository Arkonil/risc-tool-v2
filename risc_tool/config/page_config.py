"""Streamlit page configuration and styling."""

import streamlit as st

from risc_tool.data.models.asset_path import AssetPath


def set_page_config() -> None:
    """Configure the Streamlit page settings and apply custom styling.

    Sets the page title, icon, layout, and logo based on the current theme.
    Also injects the custom CSS stylesheet.
    """
    if st.context.theme.get("type") == "dark":
        logo_path = AssetPath.APP_LOGO_DARK
    else:
        logo_path = AssetPath.APP_LOGO_LIGHT

    with open(logo_path, "r") as fp:
        st.logo(fp.read(), size="large")

    st.set_page_config(
        page_title="RisC Tool",
        page_icon=AssetPath.APP_ICON,
        layout="wide",
    )

    with open(AssetPath.STYLESHEET, encoding="utf-8") as file:
        st.html(f"<style>{file.read()}</style>")
