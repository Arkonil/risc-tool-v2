"""Metric selection and reordering modal button component."""

import typing as t

import streamlit as st
from streamlit_sortables import sort_items  # type: ignore

from risc_tool.data.models.uid import MetricID
from risc_tool.data.session import Session


def metric_selector_one(
    current_metric_id: MetricID | None,
    set_metric: t.Callable[[MetricID | None], None],
    key: int = 0,
    is_double_var: bool = False,
) -> None:
    """Render a single metric dropdown selector.

    Args:
        current_metric_id: The currently selected metric ID, or None.
        set_metric: Callback invoked with the newly selected metric ID.
        key: The widget key.
        is_double_var: If True, excludes cumulative metrics.
    """
    session: Session = st.session_state["session"]
    metric_repository = session.metric_repository
    all_metrics = metric_repository.metrics

    if is_double_var:
        all_metrics = {k: v for k, v in all_metrics.items() if not v.is_cumulative}

    available_metric_ids = sorted(all_metrics.keys())

    st.write("Select Metric:")
    selected_metric_id: MetricID | str | None = st.selectbox(
        label="Metrics",
        options=available_metric_ids,
        index=available_metric_ids.index(current_metric_id)
        if current_metric_id is not None and current_metric_id in available_metric_ids
        else None,
        format_func=lambda metric_id: all_metrics[metric_id].pretty_name,
        label_visibility="collapsed",
        key=f"metric_selector_{key}",
    )

    if isinstance(selected_metric_id, str):
        try:
            selected_metric_id = MetricID(selected_metric_id)
        except (ValueError, TypeError, AttributeError):
            selected_metric_id = None

    if selected_metric_id != current_metric_id:
        set_metric(selected_metric_id)
        st.rerun()


def metric_selector(
    current_metric_ids: list[MetricID],
    set_metrics: t.Callable[[list[MetricID]], None],
    key: int = 0,
    is_double_var: bool = False,
) -> None:
    """Render a metric multiselect and reordering widget.

    Args:
        current_metric_ids: The currently selected metric IDs.
        set_metrics: Callback invoked with the reordered metric IDs.
        key: The widget key.
        is_double_var: If True, excludes cumulative metrics.
    """
    session: Session = st.session_state["session"]
    metric_repository = session.metric_repository
    all_metrics = metric_repository.metrics

    if is_double_var:
        all_metrics = {k: v for k, v in all_metrics.items() if not v.is_cumulative}

    available_metric_ids = sorted(all_metrics.keys())
    current_metric_ids = [
        uid for uid in current_metric_ids if uid in available_metric_ids
    ]

    st.write("Select Metrics:")
    selected_metric_ids = st.multiselect(
        label="Metrics",
        options=list(all_metrics.keys()),
        default=current_metric_ids,
        format_func=lambda metric_id: all_metrics[metric_id].pretty_name,
        label_visibility="collapsed",
        key=f"metric_selector_{key}",
    )

    existing_metrics = [uid for uid in current_metric_ids if uid in selected_metric_ids]
    new_metrics = [uid for uid in selected_metric_ids if uid not in current_metric_ids]
    selected_metric_ids = existing_metrics + new_metrics

    st.write("Reorder Metrics:")
    selected_metric_names = [
        all_metrics[m_id].pretty_name for m_id in selected_metric_ids
    ]
    sorted_metric_names = (
        sort_items(items=selected_metric_names) if selected_metric_names else []
    )
    sorted_metric_ids = [
        selected_metric_ids[selected_metric_names.index(m_name)]
        for m_name in sorted_metric_names
    ]

    _, col = st.columns(2)
    with col:
        if st.button("Submit", type="primary", width="stretch"):
            set_metrics(sorted_metric_ids)
            st.rerun()


@st.dialog("Set Metrics")
def metric_selector_dialog(
    current_metric_ids: list[MetricID],
    set_metrics: t.Callable[[list[MetricID]], None],
    key: int = 0,
    is_double_var: bool = False,
) -> None:
    """Open a modal dialog wrapping the metric selector.

    Args:
        current_metric_ids: The currently selected metric IDs.
        set_metrics: Callback invoked with the reordered metric IDs.
        key: The widget key.
        is_double_var: If True, excludes cumulative metrics.
    """
    metric_selector(
        current_metric_ids=current_metric_ids,
        set_metrics=set_metrics,
        key=key,
        is_double_var=is_double_var,
    )


def default_set_metrics(metric_ids: list[MetricID]) -> None:
    """Default function to handle metric selection changes."""
    # Implement the logic to handle metric selection changes as needed


def metric_selector_button(
    current_metrics: list[MetricID] | None = None,
    set_metrics: t.Callable[[list[MetricID]], None] | None = None,
    key: int = 0,
    is_double_var: bool = False,
) -> None:
    """Render a button that opens the metric selector dialog.

    Args:
        current_metrics: The currently selected metric IDs.
        set_metrics: Callback invoked with the reordered metric IDs.
        key: The widget key.
        is_double_var: If True, excludes cumulative metrics.
    """
    if current_metrics is None:
        current_metrics = []

    if set_metrics is None:
        set_metrics = default_set_metrics

    st.button(
        label="Set Metrics",
        width="stretch",
        icon=":material/functions:",
        help="Set metrics to display in the table",
        key=f"metric_selector_button_{key}",
        on_click=lambda: metric_selector_dialog(
            current_metrics, set_metrics, key, is_double_var
        ),
    )


__all__ = ["metric_selector_button", "metric_selector_one"]
