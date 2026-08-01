"""Theme detection helper for Streamlit UI components."""

import typing as t

import streamlit as st


def get_theme() -> t.Literal["light", "dark"]:
    """Return the current Streamlit theme mode ('light' or 'dark')."""

    return st.context.theme.get("type") or "dark"


__all__ = ["get_theme"]
