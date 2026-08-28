"""Empty-state placeholder shown when no filters exist."""

import streamlit as st

from risc_tool_v2.data.session import Session


def no_filter_placeholder(key: int = 0):
    session: Session = st.session_state["session"]
    filter_editor_vm = session.filter_editor_view_model

    with st.container(horizontal_alignment="center"):
        st.space("large")

        st.subheader(
            "No Filters Created Yet",
            anchor=False,
            width="content",
            text_alignment="center",
        )

        st.space("small")

        if st.button(
            "Create Filter",
            key=key,
            width="content",
            type="primary",
            icon=":material/add:",
        ):
            filter_editor_vm.set_mode("edit")
            st.rerun()


__all__ = ["no_filter_placeholder"]
