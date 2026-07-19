from risc_tool.data.repositories.data import DataRepository
from risc_tool.ui.data_importer.data_importer_vm import DataImporterViewModel


class Session:
    def __init__(self):
        self.reset()

    def reset(self):
        self.data_repository = DataRepository()
        self.data_importer_view_model = DataImporterViewModel(self.data_repository)
