"""Shared helpers for the Simulation Creator's high-level section components."""

import typing as t

import streamlit as st

from risc_tool_v2.data.session import Session
from risc_tool_v2.ui.core.session import get_session
from risc_tool_v2.ui.simulation.simulation_vm import SimulationViewModel


def session() -> Session:
    return get_session()


def vm() -> SimulationViewModel:
    return session().simulation_view_model


def reconcile(current: object, new: object, update_fn: t.Callable[[], None]) -> None:
    """Apply an edit and rerun only when the value actually changed."""
    if new == current:
        return
    update_fn()
    st.rerun()
