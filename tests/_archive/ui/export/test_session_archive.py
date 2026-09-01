"""Lightweight tests for the session archive download component."""

from unittest.mock import patch

from risc_tool.data.models.json_models import SessionJSON
from risc_tool.data.session import Session
from risc_tool.ui.export.session_archive import session_archive_download


@patch("streamlit.download_button")
@patch("streamlit.markdown")
@patch("streamlit.write")
@patch("streamlit.session_state")
def test_session_archive_download_produces_valid_json(
    mock_session_state, mock_write, mock_markdown, mock_download_button
):
    session = Session()
    mock_session_state.__getitem__.return_value = session

    session_archive_download()

    mock_download_button.assert_called_once()
    json_bytes = mock_download_button.call_args.kwargs["data"]

    assert isinstance(json_bytes, bytes)
    assert SessionJSON.model_validate_json(json_bytes) == session.to_dict()


@patch("streamlit.download_button")
@patch("streamlit.markdown")
@patch("streamlit.write")
@patch("streamlit.session_state")
def test_session_archive_download_config(
    mock_session_state, mock_write, mock_markdown, mock_download_button
):
    session = Session()
    mock_session_state.__getitem__.return_value = session

    session_archive_download()

    kwargs = mock_download_button.call_args.kwargs
    assert kwargs["file_name"] == "session_archive.json"
    assert kwargs["mime"] == "application/json"
