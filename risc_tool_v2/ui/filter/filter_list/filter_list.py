"""UI components for the Filter List view in the Filters module."""

import streamlit as st

from risc_tool_v2.data.core.uid import FilterID
from risc_tool_v2.data.core.utils.logging import get_logger
from risc_tool_v2.data.filter.models.outlier import OutlierRule
from risc_tool_v2.ui.core.session import get_session
from risc_tool_v2.ui.filter.no_filter_placeholder import no_filter_placeholder

logger = get_logger(__name__)


def sidebar_widgets():
    session = get_session()
    filter_editor_vm = session.filter_editor_view_model

    if st.button(
        label="Create Filter",
        width="stretch",
        type="primary",
        icon=":material/add:",
    ):
        filter_editor_vm.set_mode("edit")
        st.rerun()


@st.dialog("Confirm Deletion")
def delete_confirmation_dialog(filter_id: FilterID):
    session = get_session()
    filter_editor_vm = session.filter_editor_view_model

    filter_obj = filter_editor_vm.filters[filter_id]
    st.write(f"Delete Filter `{filter_obj.name}`?")

    col1, col2 = st.columns(2)
    with col1:
        if st.button("Delete", type="primary"):
            logger.info(
                "User confirmed deletion of filter ID %s ('%s')",
                filter_id,
                filter_obj.name,
            )
            filter_editor_vm.remove_filter(filter_id)
            st.rerun()
    with col2:
        if st.button("Cancel", type="secondary"):
            logger.debug("User cancelled deletion of filter ID %s", filter_id)
            st.rerun()


def filter_list():
    session = get_session()
    filter_editor_vm = session.filter_editor_view_model
    logger.debug(
        "Rendering filter list with %d filters", len(filter_editor_vm.get_filters())
    )

    if not filter_editor_vm.get_filters():
        no_filter_placeholder()
        return

    st.title("Filters")

    with st.sidebar:
        sidebar_widgets()

    show_outliers = st.sidebar.checkbox("Show Outlier Filters", value=False)

    for filter_id, filter_obj in filter_editor_vm.filters.items():
        if isinstance(filter_obj, OutlierRule) and not show_outliers:
            continue

        with st.container(key=f"filter_{filter_id}_container", border=True):
            col1, col2 = st.columns([6, 1.5], vertical_alignment="center", gap="medium")

            with col1:
                st.subheader(f"{filter_obj.name}", anchor=False, width="content")
                st.code(filter_obj.query, language="python")

            with col2:
                toggle_container = st.container()
                col21, col22, col23 = st.columns(3)

                col21.button(
                    label="",
                    key=f"filter_{filter_id}_edit_btn",
                    type="primary",
                    icon=":material/edit:",
                    on_click=filter_editor_vm.set_mode,
                    args=("edit", filter_id),
                    help="Edit",
                )

                col22.button(
                    label="",
                    key=f"filter_{filter_id}_create_duplicate_btn",
                    type="secondary",
                    icon=":material/content_copy:",
                    on_click=filter_editor_vm.duplicate_filter,
                    args=(filter_id,),
                    help="Create Duplicate",
                )

                col23.button(
                    label="",
                    key=f"filter_{filter_id}_delete_btn",
                    type="secondary",
                    icon=":material/delete:",
                    on_click=delete_confirmation_dialog,
                    args=(filter_id,),
                    help="Delete",
                )

                show_object = toggle_container.pills(
                    label="Show Object",
                    options=["Show Filter Object"],
                    key=f"filter_{filter_id}_show_object_toggle_pill",
                    label_visibility="collapsed",
                    width="stretch",
                )

            if show_object:
                st.write(filter_obj.to_dict())
                st.write(filter_obj.filter_expr)


__all__ = ["filter_list"]
