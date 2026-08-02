"""Overview tab view for summary dashboard."""

import streamlit as st

from risc_tool.data.session import Session
from risc_tool.ui.components.filter_selector import filter_selector
from risc_tool.ui.components.iteration_metric_table import iteration_metric_table
from risc_tool.ui.components.iteration_selector import iteration_selector
from risc_tool.ui.components.metric_selector import metric_selector_button


def sidebar_widgets() -> None:
    """Render sidebar control widgets for Overview tab."""
    session: Session = st.session_state["session"]
    summary_vm = session.summary_view_model

    # Metric Selection
    metric_selector_button(
        current_metrics=summary_vm.ov_metric_ids,
        set_metrics=summary_vm.set_overview_metrics,
    )

    # Filter Selection
    current_filter_ids = summary_vm.ov_filter_ids

    selected_filter_ids = filter_selector(
        key="summary-overview-filter-selector",
        filter_ids=current_filter_ids,
    )

    if set(selected_filter_ids) != set(current_filter_ids):
        summary_vm.ov_filter_ids = selected_filter_ids
        st.rerun()

    # Outlier Toggle
    current_remove_outliers = summary_vm.ov_remove_outliers

    remove_outliers = st.checkbox(
        label="Remove Outliers",
        value=current_remove_outliers,
        help="Remove Outliers",
    )

    if remove_outliers != current_remove_outliers:
        summary_vm.ov_remove_outliers = remove_outliers
        st.rerun()

    # Scalar Toggle
    current_scalars_enabled = summary_vm.ov_scalars_enabled

    scalars_enabled = st.checkbox(
        label="Enable Scalars",
        value=current_scalars_enabled,
        help="Use Scalars for Annualized Write Off Rates",
    )

    if scalars_enabled != current_scalars_enabled:
        summary_vm.ov_scalars_enabled = scalars_enabled
        st.rerun()


def overview() -> None:
    """Render main Overview tab content."""
    session: Session = st.session_state["session"]
    summary_vm = session.summary_view_model

    with st.sidebar:
        sidebar_widgets()

    iteration_id, default = iteration_selector(
        key="summary-overview-iteration-selector",
        iteration_id=summary_vm.ov_selected_iteration_id,
        default=summary_vm.ov_selected_iteration_default,
    )

    if (
        iteration_id != summary_vm.ov_selected_iteration_id
        or default != summary_vm.ov_selected_iteration_default
    ):
        summary_vm.ov_selected_iteration_id = iteration_id
        summary_vm.ov_selected_iteration_default = default
        st.rerun()

    iteration_metric_table(
        iteration_id=iteration_id,
        default=default,
        show_controls=True,
        filter_ids=summary_vm.ov_filter_ids,
        metric_ids=summary_vm.ov_metric_ids,
        scalars_enabled=summary_vm.ov_scalars_enabled,
        remove_outliers=summary_vm.ov_remove_outliers,
        editable=False,
        key="summary-overview-iteration-metric-table",
    )


__all__ = ["overview"]
