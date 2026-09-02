"""Empty-state placeholder shown when no metrics exist."""

import streamlit as st

from risc_tool_v2.data.data_source.models.asset_path import AssetPath
from risc_tool_v2.data.session import Session


def no_metric_placeholder(key: int = 0):
    """Render an empty-state with a button to create the first metric.

    Args:
        key: The widget key for the create button.
    """
    session: Session = st.session_state["session"]
    metric_editor_vm = session.metric_editor_view_model

    with st.container(horizontal_alignment="center"):
        st.space("large")

        st.image(AssetPath.NO_METRIC_ICON, width=250)

        st.subheader(
            body="No Metrics Created Yet",
            anchor=False,
            width="content",
            text_alignment="center",
        )

        st.space("small")

        if st.button(
            label="Create Metric",
            key=key,
            width="content",
            type="primary",
            icon=":material/add:",
        ):
            metric_editor_vm.set_mode("edit")
            st.rerun()


__all__ = [
    "no_metric_placeholder",
]
