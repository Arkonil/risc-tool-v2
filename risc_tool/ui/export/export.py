"""Export feature router and page entrypoint."""

import streamlit as st

from risc_tool.data.models.enums import ExportTabName
from risc_tool.data.session import Session
from risc_tool.ui.export.code_generator import iteration_code_generator
from risc_tool.ui.export.session_archive import session_archive_download


def export_view() -> None:
    """Render Export feature view based on active tab."""
    session: Session = st.session_state["session"]
    export_vm = session.export_view_model

    st.title("Export")

    if export_vm.no_iteration:
        session_archive_download()
        return

    key = "export-page-tabs"

    def on_tab_change() -> None:
        export_vm.current_tab_name = ExportTabName(st.session_state[key])

    st.tabs(
        export_vm.tab_names,
        default=export_vm.current_tab_name,
        on_change=on_tab_change,
        key=key,
    )

    selected_tab = export_vm.current_tab_name

    if selected_tab == ExportTabName.SESSION_ARCHIVE:
        session_archive_download()
    elif selected_tab == ExportTabName.PYTHON_CODE:
        iteration_code_generator(language="python")
    elif selected_tab == ExportTabName.SAS_CODE:
        iteration_code_generator(language="sas")


export_page = st.Page(
    page=export_view,
    title="Export",
    icon=":material/file_download:",
)

__all__ = ["export_page"]
