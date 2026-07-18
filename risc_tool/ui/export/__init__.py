import streamlit as st

from risc_tool.utils.logging import get_logger

logger = get_logger(__name__)


def export_view():
    logger.info("Rendering Export view")
    st.title("Export")
    st.write(
        "Export your finalized strategy directly to production-ready Python or SAS code, "
        "or download a session archive to restore later."
    )


export_page = st.Page(
    page=export_view,
    title="Export",
    icon=":material/file_download:",
)


__all__ = ["export_page"]
