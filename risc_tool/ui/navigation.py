"""Page navigation configuration for the RISC Tool Streamlit application."""

import streamlit as st

from risc_tool.ui.config import config_page
from risc_tool.ui.data_explorer.data_explorer import data_explorer_page
from risc_tool.ui.data_importer.data_importer import data_importer_page
from risc_tool.ui.documentation import documentation_page
from risc_tool.ui.export import export_page
from risc_tool.ui.filters import filter_page
from risc_tool.ui.home import home_page
from risc_tool.ui.iterations import iterations_page
from risc_tool.ui.metrics import metrics_page
from risc_tool.ui.summary import summary_page


def set_page_navigation():
    """Configure and run the Streamlit page navigation.

    Organizes pages into three sections:
    - Home: Home page and documentation
    - Tools: Data importer, explorer, metrics, filters, config, iterations
    - Results: Summary and export
    """
    pg = st.navigation({
        "Home": [
            home_page,
            documentation_page,
        ],
        "Tools": [
            data_importer_page,
            data_explorer_page,
            metrics_page,
            filter_page,
            config_page,
            iterations_page,
        ],
        "Results": [
            summary_page,
            export_page,
        ],
    })

    pg.run()
