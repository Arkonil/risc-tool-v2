"""Session Archive JSON export download component."""

import streamlit as st

from risc_tool.data.session import Session


def session_archive_download() -> None:
    """Render Session JSON archive download button."""
    session: Session = st.session_state["session"]

    st.markdown("### Download Session Archive as a `.json` File")
    st.write(
        "Exports full application state including data config, metrics, filters, and iterations."
    )
    st.write("")

    session_json = session.to_dict()
    json_bytes = session_json.model_dump_json(indent=2).encode("utf-8")

    st.download_button(
        label="Download session_archive.json",
        data=json_bytes,
        file_name="session_archive.json",
        mime="application/json",
        icon=":material/file_download:",
        type="primary",
    )


__all__ = ["session_archive_download"]
