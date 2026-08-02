"""Empty state placeholder for summary dashboard when no iterations exist."""

import streamlit as st

from risc_tool.data.models.asset_path import AssetPath
from risc_tool.ui.iterations.iterations import iterations_page


def no_summary_placeholder(key: int = 0) -> None:
    """Render placeholder informing user to create iterations first."""
    with st.container(horizontal_alignment="center"):
        st.space("large")

        st.image(str(AssetPath.NO_ITERATION_ICON), width=250)

        st.subheader(
            "No Iterations Created Yet",
            anchor=False,
            width="content",
            text_alignment="center",
        )

        st.space("small")

        if st.button(
            "Create Iteration",
            key=key,
            width="content",
            type="primary",
            icon=":material/add:",
        ):
            st.switch_page(iterations_page)


__all__ = ["no_summary_placeholder"]
