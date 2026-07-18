from risc_tool.config.page_config import set_page_config
from risc_tool.config.session_state import set_session_state
from risc_tool.ui.navigation import set_page_navigation


def run_app(log_level: int, log_file: bool) -> None:
    set_page_config()
    set_session_state(log_level=log_level, log_file=log_file)
    set_page_navigation()


__all__ = ["run_app"]
