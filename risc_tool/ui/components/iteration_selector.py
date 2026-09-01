"""Iteration dropdown selector component."""

import streamlit as st

from risc_tool.data.models.uid import IterationID
from risc_tool.data.session import Session


def iteration_selector(
    key: str,
    iteration_id: IterationID | None = None,
    default: bool | None = None,
) -> tuple[IterationID, bool]:
    """Render a dropdown widget for selecting an iteration view.

    Args:
        key: The widget key.
        iteration_id: Optional preselected iteration ID.
        default: Optional preselected default/custom flag.

    Returns:
        A tuple of (iteration_id, default) for the selected option.
    """
    session: Session = st.session_state["session"]
    iterations = session.iterations_repository.iteration_selector_options()
    options = list(iterations.keys())

    if (
        iteration_id is not None
        and default is not None
        and (iteration_id, default) in options
    ):
        index = options.index((iteration_id, default))
    else:
        index = 0

    selected = st.selectbox(
        label=f"iter_selector_{key}",
        options=options,
        index=index,
        label_visibility="collapsed",
        format_func=lambda k: iterations.get(k, ""),
        key=f"iter_selector_{key}",
    )

    return selected


__all__ = ["iteration_selector"]
