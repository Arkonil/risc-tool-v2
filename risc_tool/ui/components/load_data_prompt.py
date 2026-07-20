"""UI component to prompt the user to load data when no data sources are active."""

import streamlit as st

from risc_tool.data.models.asset_path import AssetPath
from risc_tool.ui.data_importer.data_importer import data_importer_page
from risc_tool.utils.logging import get_logger

logger = get_logger(__name__)


def load_data_prompt(key: int = 0):
    """Render a prompt container asking the user to load data.

    Displays an error icon, message, and a button that switches to the Data Importer page.

    Args:
        key: Unique key for the Streamlit button widget.
    """
    with st.container(horizontal_alignment="center"):
        st.space("large")

        # Display the custom SVG error icon
        st.image(str(AssetPath.NO_DATA_ERROR_ICON), width=250)

        st.subheader(
            "No Data Loaded",
            anchor=False,
            width="content",
            text_alignment="center",
        )

        if st.button(
            "Load Data",
            key=key,
            type="primary",
        ):
            logger.info("User requested to load data from prompt")
            st.switch_page(data_importer_page)


__all__ = ["load_data_prompt"]
