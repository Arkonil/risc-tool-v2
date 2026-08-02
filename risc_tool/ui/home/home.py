"""Home feature router and page entrypoint."""

import streamlit as st

from risc_tool.data.session import Session
from risc_tool.ui.home.import_json import import_json_page
from risc_tool.ui.home.welcome import welcome_page


def home_view() -> None:
    """Render Home feature view based on active sub-view."""
    session: Session = st.session_state["session"]
    home_vm = session.home_view_model

    if home_vm.home_page_view == "welcome":
        welcome_page()
    elif home_vm.home_page_view == "import-json":
        import_json_page()


home_page = st.Page(
    page=home_view,
    title="Home",
    icon=":material/home:",
    default=True,
)

__all__ = ["home_page"]
