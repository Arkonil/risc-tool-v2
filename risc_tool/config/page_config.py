import streamlit as st

from risc_tool.data.models.asset_path import AssetPath


def set_page_config() -> None:
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


__all__ = ["set_page_config"]
