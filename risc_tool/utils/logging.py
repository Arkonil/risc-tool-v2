"""Logging configuration and utilities for the RISC Tool.

This module provides a centralized logging setup with colored console output
and optional file logging. It includes formatters that extract class/method
names from the call stack for better debugging context.
"""

import inspect
import logging
import sys
from abc import abstractmethod
from pathlib import Path

import colorama

LEVEL_COLORS = {
    logging.DEBUG: colorama.Fore.CYAN,
    logging.INFO: colorama.Fore.GREEN,
    logging.WARNING: colorama.Fore.YELLOW,
    logging.ERROR: colorama.Fore.RED,
    logging.CRITICAL: colorama.Fore.RED + colorama.Style.BRIGHT,
}


class BaseFormatter(logging.Formatter):
    """Base formatter class for styling and structuring log records.

    This formatter extracts the caller's class and method name from the
    call stack to provide context in log messages.

    Attributes:
        SEPARATOR: String used to separate fields in the formatted output.
    """

    SEPARATOR = " | "

    @abstractmethod
    def colored(self, text: str, log_level: int) -> str:
        """Apply color styling to the specified text based on the log level.

        Args:
            text: The text to be styled.
            log_level: The logging level integer (e.g., logging.INFO).

        Returns:
            The styled text string.
        """
        raise NotImplementedError("Subclasses must implement the 'colored' method.")

    def _get_caller_name(self, record: logging.LogRecord) -> str:
        """Retrieve the class name and method name, or just the function name.

        Walks the call stack to find the frame matching the log record's
        function name, then extracts the qualified name.

        Args:
            record: The LogRecord instance.

        Returns:
            The qualified caller name (e.g., "ClassName.method_name").
        """
        try:
            # Walk up the call stack to find the frame matching the record's function name.
            # Start 2 frames up to skip this helper and the format method.
            frame = inspect.currentframe()

            for _ in range(8):
                if frame is None:
                    break
                frame = frame.f_back

            while frame:
                if frame.f_code.co_name == record.funcName:
                    qualname = getattr(frame.f_code, "co_qualname", None)
                    if qualname and "." in qualname and "<locals>" not in qualname:
                        return qualname

                    # Fallback to inspecting frame locals for instance/class methods
                    if "self" in frame.f_locals:
                        return (
                            f"{type(frame.f_locals['self']).__name__}.{record.funcName}"
                        )
                    elif "cls" in frame.f_locals:
                        cls_val = frame.f_locals["cls"]
                        if isinstance(cls_val, type):
                            return f"{cls_val.__name__}.{record.funcName}"
                    break
                frame = frame.f_back
        except Exception:
            pass
        return record.funcName

    def format(self, record: logging.LogRecord) -> str:
        """Format the specified log record as a text string.

        Args:
            record: The LogRecord instance to format.

        Returns:
            The formatted log message string.
        """
        # Format timestamp with millisecond resolution
        created_time = self.formatTime(record, "%Y-%m-%d %H:%M:%S")
        timestamp = f"{created_time}.{int(record.msecs):03d}"

        # Get the thread ID from the log record
        thread_id = record.thread

        # Log Level name with color based on the level
        levelname = self.colored(record.levelname, record.levelno)

        # Get classname.methodname or just funcname
        caller_name = f"{self._get_caller_name(record)}:{record.lineno}"

        # Format the actual message
        message = record.getMessage()
        if record.exc_info:
            # Cache the exception text if not already formatted
            if not record.exc_text:
                record.exc_text = self.formatException(record.exc_info)

        if record.exc_text:
            if message[-1:] != "\n":
                message += "\n"
            message += record.exc_text

        if record.stack_info:
            if message[-1:] != "\n":
                message += "\n"
            message += self.formatStack(record.stack_info)

        return (
            f"{timestamp} | {thread_id:<5} | {levelname:<8} | {caller_name} | {message}"
        )


class ColoredFormatter(BaseFormatter):
    """Formatter that applies ANSI colors to the log level name."""

    def colored(self, text: str, log_level: int) -> str:
        """Apply ANSI colors to text using colorama based on the log level.

        Args:
            text: The text to colorize.
            log_level: The logging level integer.

        Returns:
            The colorized text string with ANSI reset sequence.
        """
        color = LEVEL_COLORS.get(log_level, "")
        reset = colorama.Style.RESET_ALL if color else ""
        return f"{color}{text}{reset}"


class PlainFormatter(BaseFormatter):
    """Formatter that leaves the log level name as plain text."""

    def colored(self, text: str, log_level: int) -> str:
        """Return the text unchanged without any ANSI formatting.

        Args:
            text: The text to format.
            log_level: The logging level integer.

        Returns:
            The original unmodified text.
        """
        return text


_logging_configured = False


def configure_logging(
    log_level: int = logging.INFO, log_file: Path | None = None
) -> None:
    """Configure the logging system with optional color support.

    Sets up the root logger with a colored console handler and optional
    file handler. Only configures once; subsequent calls are no-ops.

    Args:
        log_level: The minimum logging level to display.
        log_file: The file path to log to. If provided, log records will also
            be written to this file without color formatting.
    """
    global _logging_configured
    if _logging_configured:
        return

    _logging_configured = True

    # Initialize colorama for cross-platform color support
    colorama.init(autoreset=False)

    # Create the root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)

    # Remove existing handlers to prevent duplicate messages
    if root_logger.handlers:
        for handler in root_logger.handlers[:]:
            root_logger.removeHandler(handler)

    # stdout Handler (with colors)
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(log_level)
    console_handler.setFormatter(ColoredFormatter())
    root_logger.addHandler(console_handler)

    if log_file:
        log_file.parent.mkdir(parents=True, exist_ok=True)

        # File Handler (without colors)
        file_handler = logging.FileHandler(log_file, mode="a", encoding="utf-8")
        file_handler.setLevel(log_level)
        file_handler.setFormatter(PlainFormatter())
        root_logger.addHandler(file_handler)


def get_logger(name: str, log_level: int | None = None) -> logging.Logger:
    """Get a logger instance with the root logger's configuration.

    Args:
        name: The name of the logger (usually the module name).
        log_level: Optional custom log level for this specific logger.

    Returns:
        A configured logging.Logger instance.
    """
    logger = logging.getLogger(name)

    if log_level is not None:
        logger.setLevel(log_level)

    return logger


__all__ = ["configure_logging", "get_logger"]
