from risc_tool_v2.config.page_config import set_page_config
from risc_tool_v2.config.session_state import set_session_state
from risc_tool_v2.ui.core.navigation import set_page_navigation


def run_app(log_level: int, log_file: bool) -> None:
    """Entry point for the RISC Tool Streamlit application.

    Configures the page settings, initializes session state with logging,
    and sets up page navigation. Called from the main CLI entry point.

    Args:
        log_level: The minimum logging level to use (e.g., logging.INFO).
        log_file: Whether to write logs to a timestamped file.
    """
    set_page_config()
    set_session_state(log_level=log_level, log_file=log_file)
    set_page_navigation()


__all__ = ["run_app"]
