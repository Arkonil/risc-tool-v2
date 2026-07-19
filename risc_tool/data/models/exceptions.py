"""Custom exceptions for the data import module."""

from risc_tool.data.models.data_source import DataSource


class DataImportError(Exception):
    """Exception raised when there is an error during data import.

    Attributes:
        message: The error message describing the import failure.
        data_source: The DataSource that caused the error, if available.
    """

    def __init__(self, message: str, data_source: DataSource | None = None):
        """Initialize the DataImportError.

        Args:
            message: A descriptive error message.
            data_source: The DataSource associated with the error, if any.
        """
        self.message = message
        self.data_source = data_source
        super().__init__(self.message)
