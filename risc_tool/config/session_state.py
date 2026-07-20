"""Session state initialization and logging configuration for Streamlit."""

import logging
from datetime import datetime
from pathlib import Path

import streamlit as st

from risc_tool.data.session import Session
from risc_tool.utils.logging import configure_logging

LOGS_DIR = Path(__file__).resolve().parent.parent.parent / "logs"


def _build_session_log_file_path() -> Path:
    """Build the log file path for the current session.

    Returns:
        The log file path for the current session with a timestamp.
    """
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    return LOGS_DIR / f"session_{timestamp}.log"


def set_session_state(log_level: int = logging.INFO, log_file: bool = True) -> None:
    """Initialize or retrieve the session state and configure logging.

    Creates a Session object in st.session_state if it doesn't exist,
    sets up a log file path, and configures the logging system.

    Args:
        log_level: The minimum logging level to display. Defaults to logging.INFO.
        log_file: Whether to write logs to a file. Defaults to True.
    """
    if "session" not in st.session_state:
        session: Session = Session()
        st.session_state["session"] = session

    if "session_log_file" not in st.session_state:
        st.session_state["session_log_file"] = _build_session_log_file_path()

    configure_logging(
        log_level=log_level,
        log_file=st.session_state["session_log_file"] if log_file else None,
    )
