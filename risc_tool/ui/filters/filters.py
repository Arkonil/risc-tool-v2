import streamlit as st

from risc_tool.data.session import Session
from risc_tool.ui.components.load_data_prompt import load_data_prompt
from risc_tool.ui.filters.filter_editor import filter_editor
from risc_tool.ui.filters.filter_list import filter_list


def filters():
    """Toggle between list view and edit view in the Filters page."""
    session: Session = st.session_state["session"]
    filter_editor_vm = session.filter_editor_view_model

    if not filter_editor_vm.data_loaded:
        load_data_prompt()
        return

    if filter_editor_vm.mode == "view":
        filter_list()
    else:
        filter_editor()


filter_page = st.Page(
    page=filters,
    title="Filters",
    icon=":material/filter_alt:",
)

__all__ = [
    "filter_page",
]
