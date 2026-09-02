import streamlit as st

from risc_tool_v2.data.core.utils.logging import get_logger
from risc_tool_v2.ui.core.components.load_data_prompt import load_data_prompt
from risc_tool_v2.ui.core.session import get_session
from risc_tool_v2.ui.filter.filter_editor.filter_editor import filter_editor
from risc_tool_v2.ui.filter.filter_list.filter_list import filter_list

logger = get_logger(__name__)


def filters():
    session = get_session()
    filter_editor_vm = session.filter_editor_view_model

    if not filter_editor_vm.data_loaded:
        load_data_prompt()
        return

    logger.debug("Filters page in mode: %s", filter_editor_vm.mode)
    if filter_editor_vm.mode == "view":
        filter_list()
    else:
        filter_editor()


filter_page = st.Page(
    page=filters,
    title="Filters",
    icon=":material/filter_alt:",
    url_path="/filters",
)

__all__ = ["filter_page", "filters"]
