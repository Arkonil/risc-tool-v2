"""Filter multiselect component for iterations and summary views."""

import streamlit as st

from risc_tool.data.models.types import FilterID
from risc_tool.data.session import Session


def filter_selector(
    key: str, filter_ids: list[FilterID] | None = None
) -> list[FilterID]:
    """Render a multiselect widget for choosing filters.

    Args:
        key: The widget key.
        filter_ids: Optional default selection of filter IDs.

    Returns:
        The selected filter IDs.
    """
    session: Session = st.session_state["session"]
    filters = session.filter_repository.get_filters()

    options = list(filters.keys())
    if filter_ids is None:
        filter_ids = []

    selected_filter_ids = st.multiselect(
        label="Filter",
        options=options,
        default=filter_ids,
        format_func=lambda f_id: filters[f_id].pretty_name,
        label_visibility="collapsed",
        key=f"filter_selector_{key}",
        help="Select filters to apply to the iteration",
        placeholder="Select Filters",
    )

    return selected_filter_ids


__all__ = ["filter_selector"]
