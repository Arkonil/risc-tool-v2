from risc_tool.data.models.data_source import DataSource


class DataImportError(Exception):
    """
    Exception raised when there is an error during data import.
    """

    def __init__(self, message: str, data_source: DataSource | None = None):
        self.message = message
        self.data_source = data_source
        super().__init__(self.message)
