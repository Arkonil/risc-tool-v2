import streamlit as st

from risc_tool.utils.logging import get_logger

logger = get_logger(__name__)


def data_importer_view():
    logger.info("Rendering Data Importer view")
    st.title("Data Importer")
    st.write(
        "Import multiple CSV and Excel datasets simultaneously. "
        "Supports auto-alignment of schemas and variable mapping to standardize KPIs."
    )


data_importer_page = st.Page(
    page=data_importer_view,
    title="Data Importer",
    icon=":material/upload:",
)


__all__ = ["data_importer_page"]
