"""Data viewer component for the Data Importer UI.

This module renders a tabbed preview of the currently selected data source,
showing a sample of the data as a Streamlit dataframe.
"""

import streamlit as st

from risc_tool.data.session import Session
from risc_tool.utils.logging import get_logger

logger = get_logger(__name__)


def data_viewer():
    """Render the data preview section.

    Shows a tabbed interface with one tab per data source. The currently
    selected data source's tab is active by default. Displays a sample
    of the data as an interactive Polars LazyFrame via st.dataframe.

    Returns early if no data sources exist or none is selected.
    """
    session: Session = st.session_state["session"]
    data_importer_view_model = session.data_importer_view_model

    if data_importer_view_model.is_empty:
        logger.debug("Data viewer skipped: no data sources")
        return

    current_ds_id = data_importer_view_model.current_ds_id

    if current_ds_id is None:
        logger.debug("Data viewer skipped: no data source selected")
        return

    data_source_views = data_importer_view_model.data_source_views
    ds_ids = [ds_id for ds_id in data_source_views]
    current_ds_label = data_source_views[current_ds_id].data_source.label

    st.subheader("Preview Data")

    tabs = st.tabs(
        tabs=[dsv.data_source.label for dsv in data_source_views.values()],
        default=current_ds_label,
        key="data-viewer-tabs",
        on_change="rerun",
    )

    for ds_id, tab in zip(ds_ids, tabs):
        if tab.open:
            logger.debug("Showing data preview for source ID %s", ds_id)
            sample_df = data_source_views[ds_id].data_source.lazyframe
            st.dataframe(sample_df, key="data-viewer-dataframe")
            break


__all__ = ["data_viewer"]
