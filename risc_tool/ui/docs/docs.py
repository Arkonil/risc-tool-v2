"""Documentation page view route for displaying interactive documentation."""

import streamlit as st

from risc_tool.data.models.docs_path import DocPage
from risc_tool.data.session import Session
from risc_tool.ui.docs.component import documentation_viewer
from risc_tool.ui.docs.utils import load_documentation_pages


def documentation() -> None:
    """Entry point for rendering Documentation page with custom viewer."""
    session: Session = st.session_state["session"]
    docs_vm = session.docs_view_model

    doc_pages: list[DocPage] = load_documentation_pages()

    if not doc_pages:
        st.error("No documentation files found.", icon=":material/error:")
        return

    current_idx: int = docs_vm.documentation_page_idx
    if current_idx >= len(doc_pages):
        current_idx = 0
        docs_vm.set_page_index(0)

    new_idx: int = documentation_viewer(pages=doc_pages, active_index=current_idx)

    if new_idx != current_idx:
        docs_vm.set_page_index(new_idx)
        st.rerun()


docs_page = st.Page(
    page=documentation,
    title="Documentation",
    icon=":material/menu_book:",
)

__all__ = ["docs_page", "documentation"]
