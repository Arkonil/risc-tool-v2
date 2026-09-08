"""Simulation iteration model.

An iteration is a single-variable analysis derived from one simulation
output. It stores only references (``simulation_id``, ``scg_id``, ``sc_id``,
``so_id``) into the simulation repository's cache; banding and configuration
resolve from the referenced outputs and configs at render time.

Unlike content-addressed models, an iteration's identity is a simple unique
integer assigned sequentially by the simulation repository (mirroring v1's
iteration ids), and the object itself is deliberately mutable.
"""

import typing as t

from pydantic import BaseModel, ConfigDict

from risc_tool_v2.data.core.enums import VariableType
from risc_tool_v2.data.core.uid import (
    IterationID,
    SimulationConfigGeneratorID,
    SimulationConfigID,
    SimulationID,
    SimulationOutputID,
)
from risc_tool_v2.data.simulation.json.simulation_json import IterationJSON


class SimulationIteration(BaseModel):
    """A single-variable iteration wrapper around one simulation output.

    Attributes:
        uid: Sequential integer identity assigned by the repository.
        name: Human-readable label (auto-generated at creation).
        simulation_id: The parent simulation whose output this derives from.
        scg_id: The simulation's config generator (risk segments, scalars, bad rates).
        sc_id: The simulation config that produced the output (content hash).
        so_id: The simulation output whose groups define this iteration's bands.
        variable_name: The banded variable's column name.
        variable_type: Whether the variable is numerical or categorical.
    """

    model_config = ConfigDict(extra="forbid")

    uid: IterationID = IterationID.UNSET
    name: str
    simulation_id: SimulationID
    scg_id: SimulationConfigGeneratorID
    sc_id: SimulationConfigID
    so_id: SimulationOutputID
    variable_name: str
    variable_type: VariableType

    def to_dict(self) -> IterationJSON:
        """Serialize this iteration to its JSON model."""
        return IterationJSON(
            uid=self.uid,
            name=self.name,
            simulation_id=self.simulation_id,
            scg_id=self.scg_id,
            sc_id=self.sc_id,
            so_id=self.so_id,
            variable_name=self.variable_name,
            variable_type=self.variable_type,
        )

    @classmethod
    def from_dict(cls, data: IterationJSON) -> t.Self:
        """Reconstruct an iteration from its JSON model."""
        return cls(
            uid=data.uid,
            name=data.name,
            simulation_id=data.simulation_id,
            scg_id=data.scg_id,
            sc_id=data.sc_id,
            so_id=data.so_id,
            variable_name=data.variable_name,
            variable_type=data.variable_type,
        )


__all__ = ["SimulationIteration"]
