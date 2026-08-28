"""Page navigation configuration for risc-tool-v2."""

import streamlit as st

from risc_tool_v2.ui.data_source.data_explorer.data_explorer import data_explorer_page
from risc_tool_v2.ui.data_source.data_importer.data_importer import data_importer_page
from risc_tool_v2.ui.filter.filters import filter_page
from risc_tool_v2.ui.metric.metrics import metrics_page


def set_page_navigation():
    pg = st.navigation({
        "Tools": [
            data_importer_page,
            data_explorer_page,
            filter_page,
            metrics_page,
        ],
    })

    pg.run()


__all__ = ["set_page_navigation"]
