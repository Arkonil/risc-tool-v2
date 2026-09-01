from risc_tool.data.models.changes import ChangeTracker
from risc_tool.data.models.enums import Signature
from risc_tool.data.models.types import ChangeIDs
from risc_tool.data.repositories.simulation import SimulationRepository


class SimulationViewStatus:
    def __init__(self):
        self.__graph_open: bool = True
        self.__simulation_creator = False
        self.__simulation_viewer = False
        self.__iteration_viewer = False

    # def current_status(
    #     self,
    # ) -> (
    #     tuple[t.Literal["graph"], None]
    #     | tuple[t.Literal["simulation_creator"], SimulationID]
    #     | tuple[t.Literal["simulation_viewer"], SimulationID]
    #     | tuple[t.Literal["iteration_viewer"], IterationID]
    # ):
    #     return ("graph", None)


class SimulationViewModel(ChangeTracker):
    @property
    def signature(self) -> Signature:
        return Signature.SIMULATION_VIEW_MODEL

    def __init__(self, simulation_repository: SimulationRepository) -> None:
        super().__init__(dependencies=[simulation_repository])

        # dependencies
        self.__simulation_repository = simulation_repository

        # navigation
        # graph, simulation creator, simulation viewer, iteration viewer (single and double)
        self.__status = SimulationViewStatus()

    def on_dependency_update(self, change_ids: ChangeIDs) -> None:
        return


__all__ = ["SimulationViewModel"]
