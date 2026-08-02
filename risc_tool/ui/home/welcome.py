"""Welcome landing page for Home feature."""

import streamlit as st

from risc_tool.data.session import Session
from risc_tool.ui.data_importer.data_importer import data_importer_page


def welcome_page() -> None:
    """Render welcome landing view."""
    session: Session = st.session_state["session"]
    home_vm = session.home_view_model

    st.title("Risk Identifier and Segmentation Creation Tool")

    st.write("")
    st.write("")

    with st.container(border=True):
        st.markdown("### Import Data to get started")
        st.write('Supported file formats: `".csv"`')
        st.write("")
        if st.button(
            "Go to Data Importer", icon=":material/file_upload:", type="primary"
        ):
            st.switch_page(data_importer_page)

    st.write("")
    st.write("")

    with st.container(border=True):
        st.markdown("### Import a `.json` file to continue working on it")
        st.write("")
        if st.button(
            label="Import JSON File",
            icon=":material/open_in_new:",
        ):
            home_vm.set_home_page_view("import-json")
            st.rerun()


__all__ = ["welcome_page"]
