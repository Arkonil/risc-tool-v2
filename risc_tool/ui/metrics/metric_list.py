"""Metric list view showing all metrics with edit/duplicate/delete actions."""

import streamlit as st

from risc_tool.data.models.types import MetricID
from risc_tool.data.session import Session
from risc_tool.ui.metrics.no_metric_placeholder import no_metric_placeholder


def sidebar_widgets():
    """Render sidebar widgets with a button to create a new metric."""
    session: Session = st.session_state["session"]
    metric_editor_vm = session.metric_editor_view_model

    if st.button(
        label="Create Metric",
        width="stretch",
        type="primary",
        icon=":material/add:",
    ):
        metric_editor_vm.set_mode("edit")
        st.rerun()


@st.dialog("Confirm Deletion")
def delete_confirmation_dialog(metric_id: MetricID):
    """Show a confirmation dialog before deleting a metric.

    Args:
        metric_id: The ID of the metric to delete.
    """
    session: Session = st.session_state["session"]
    metric_editor_vm = session.metric_editor_view_model

    metric_obj = metric_editor_vm.metrics[metric_id]

    st.write(f"Delete Metric `{metric_obj.name}` ?")

    col1, col2 = st.columns(2)

    with col1:
        if st.button("Delete", type="primary", width="stretch"):
            metric_editor_vm.remove_metric(metric_id)
            st.rerun()
    with col2:
        if st.button("Cancel", type="secondary", width="stretch"):
            st.rerun()


def metric_list():
    """Render the full metric list page."""
    session: Session = st.session_state["session"]
    metric_editor_vm = session.metric_editor_view_model

    if not metric_editor_vm.metrics:
        no_metric_placeholder()
        return

    st.title("Metrics")

    with st.sidebar:
        sidebar_widgets()

    for metric_id, metric_obj in metric_editor_vm.metrics.items():
        with st.container(key=f"metric_{metric_id}_container", border=True):
            col1, col2 = st.columns([6, 1.5], vertical_alignment="center", gap="medium")
            with col1:
                with st.container(
                    horizontal=True, width="stretch", vertical_alignment="bottom"
                ):
                    st.subheader(f"{metric_obj.name}", width="content", anchor=False)

                    st.space("stretch")

                    for ds_id in metric_obj.data_source_ids:
                        st.badge(
                            metric_editor_vm.get_data_source_label(ds_id),
                            width="content",
                        )

                    if metric_obj.use_thousand_sep:
                        st.badge(
                            "&nbsp;&nbsp;,&nbsp;&nbsp;", width="content", color="green"
                        )

                    if metric_obj.is_percentage:
                        st.badge("&nbsp;%&nbsp;", width="content", color="green")

                    st.badge(f"Decimals: {metric_obj.decimal_places}", color="yellow")

                    if metric_id.is_default:
                        st.badge("Default", color="red")

                st.code(metric_obj.query, language="python")

            with col2:
                toggle_container = st.container()
                col21, col22, col23 = st.columns(3)

                col21.button(
                    label="",
                    key=f"metric_{metric_id}_edit_btn",
                    type="primary",
                    icon=":material/edit:",
                    on_click=metric_editor_vm.set_mode,
                    args=("edit", metric_id),
                    help="Edit",
                    disabled=metric_id.is_default,
                )

                col22.button(
                    label="",
                    key=f"metric_{metric_id}_create_duplicate_btn",
                    type="secondary",
                    icon=":material/content_copy:",
                    on_click=metric_editor_vm.duplicate_metric,
                    args=(metric_id,),
                    help="Create Duplicate",
                )

                col23.button(
                    label="",
                    key=f"metric_{metric_id}_delete_btn",
                    type="secondary",
                    icon=":material/delete:",
                    on_click=delete_confirmation_dialog,
                    args=(metric_id,),
                    help="Delete",
                    disabled=metric_id.is_default,
                )

                show_object = toggle_container.pills(
                    label="Show Object",
                    options=["Show Metric Object"],
                    key=f"metric_{metric_id}_show_object_toggle_pill",
                    label_visibility="collapsed",
                    width="stretch",
                )

            if show_object:
                st.write(metric_obj.to_dict())


__all__ = ["metric_list"]
