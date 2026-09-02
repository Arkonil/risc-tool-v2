"""Shared Streamlit session-state access helpers."""

import streamlit as st

from risc_tool_v2.data.session import Session


def get_session() -> Session:
    """Return the application :class:`Session` from Streamlit session state."""
    return st.session_state["session"]


__all__ = ["get_session"]
