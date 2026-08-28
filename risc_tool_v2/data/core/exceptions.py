"""Custom exceptions for the data import module."""

import textwrap
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from risc_tool_v2.data.data_source.models.data_source import DataSource


class MissingColumnError(Exception):
    """Exception raised when a specified column is not found in the data."""

    def __init__(self, column_name: str):
        """Initialize the error with the missing column name.

        Args:
            column_name: The name of the column that was not found.
        """
        super().__init__(f"Column '{column_name}' not found in data.")


class VariableNotNumericError(Exception):
    """Exception raised when a variable is expected to be numeric but is not."""

    def __init__(self, variable_name: str, actual_type: str):
        """Initialize the error with the variable name and its actual type.

        Args:
            variable_name: The name of the non-numeric variable.
            actual_type: The data type that was found instead of numeric.
        """
        super().__init__(
            f"Variable '{variable_name}' is not numeric. Found type: {actual_type}."
        )


class SampleDataNotLoadedError(Exception):
    """Exception raised when data sources are not loaded but are required."""

    def __init__(self, message: str = "Sample data is not loaded."):
        """Initialize the error with an optional custom message.

        Args:
            message: The error message to display. Defaults to a standard message.
        """
        self.message = message
        super().__init__(self.message)


class DataImportError(Exception):
    """Exception raised when there is an error during data import.

    Attributes:
        message: The error message describing the import failure.
        data_source: The DataSource that caused the error, if available.
    """

    def __init__(self, message: str, data_source: "DataSource | None" = None):
        """Initialize the DataImportError.

        Args:
            message: A descriptive error message.
            data_source: The DataSource associated with the error, if any.
        """
        self.message = message
        self.data_source = data_source
        super().__init__(self.message)


class InvalidFilterError(Exception):
    """Custom exception for invalid filter queries.

    Attributes:
        query: The raw filter query that failed validation.
        reason: A human-readable explanation of why the query is invalid.
    """

    def __init__(self, query: str, reason: str):
        """Initialize the error with the offending query and reason.

        Args:
            query: The filter query string that is invalid.
            reason: Description of the validation failure.
        """
        self.query = query
        self.reason = reason

    def __str__(self) -> str:
        """Return a markdown-formatted representation of the error.

        Returns:
            A dedented multi-line string with the reason and query, suitable
            for display in the UI.
        """
        return textwrap.dedent(f"""
            **InvalidFilterError**: {self.reason}
            Query: `{self.query}`
        """).replace("\n", "\n\n")


def format_error(error: Exception) -> str:
    """Format an exception into a human-readable markdown string for the UI."""
    if isinstance(error, SyntaxError):
        error_lines = [
            f"**SyntaxError**: {error.msg}",
            f"**Line**: {error.lineno}",
        ]

        if error.text:
            error_lines.append(error.text.rstrip())

        if error.offset is not None and error.end_offset is not None:
            error_lines.append(
                f"{' ' * (error.offset - 1)}{'^' * (error.end_offset - error.offset + 1)}"
            )

        return "\n\n".join(error_lines)

    if isinstance(error, ValueError):
        return textwrap.dedent(f"""
            **ValueError**: {error}
        """).replace("\n", "\n\n")

    return str(error)


__all__ = [
    "DataImportError",
    "InvalidFilterError",
    "MissingColumnError",
    "SampleDataNotLoadedError",
    "VariableNotNumericError",
    "format_error",
]
