from risc_tool.data.models.enums import Signature
from risc_tool.data.models.types import ChangeIDs
from risc_tool.data.repositories.base import BaseRepository


class SimulationRepository(BaseRepository):
    @property
    def signature(self):
        return Signature.SIMULATION_REPOSITORY

    def __init__(self):
        super().__init__(dependencies=[])

    def on_dependency_update(self, change_ids: ChangeIDs) -> None:
        return
