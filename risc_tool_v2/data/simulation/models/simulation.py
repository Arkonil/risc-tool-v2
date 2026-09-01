"""Top-level Simulation object model (the entity living in the repository)."""

import typing as t
from datetime import UTC, datetime
from enum import StrEnum
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator

from risc_tool_v2.data.core.uid import SimulationID
from risc_tool_v2.data.simulation.models.simulation_config import (
    SimulationConfigGenerator,
    SimulationOutput,
)


class SimulationStatus(StrEnum):
    """Execution status of a Simulation object."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class Simulation(BaseModel, frozen=True):
    """Top-level simulation entity stored in the repository.

    Every Simulation owns exactly one SimulationConfigGenerator. The status
    and timestamps track execution lifecycle, and ``output`` holds the
    optional SimulationOutput produced when the simulation has run.

    The ``uid`` is unique per creation event (not content-addressed): two
    simulations with identical SCGs are still distinct entities.
    """

    model_config = ConfigDict(extra="forbid")

    uid: SimulationID = SimulationID.UNSET
    simulation_config_generator: SimulationConfigGenerator

    status: SimulationStatus = SimulationStatus.PENDING
    output: SimulationOutput | None = None
    error_message: str | None = None

    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    run_started_at: datetime | None = None
    run_completed_at: datetime | None = None

    @model_validator(mode="after")
    def _derive_uid(self) -> "Simulation":
        """Generate a fresh unique uid when left unset.

        Unlike content-addressed identities, each Simulation is a distinct
        creation event, so unset uids are populated with a random UUID instead
        of a content hash.
        """
        if self.uid is SimulationID.UNSET:
            object.__setattr__(self, "uid", SimulationID(uuid4()))
        return self

    def with_updates(self, **updates: t.Any) -> "Simulation":
        """Return a copy of this simulation with updated fields."""
        fields: dict[str, t.Any] = {
            "simulation_config_generator": self.simulation_config_generator,
            "status": self.status,
            "output": self.output,
            "error_message": self.error_message,
            "created_at": self.created_at,
            "run_started_at": self.run_started_at,
            "run_completed_at": self.run_completed_at,
        }
        fields.update(updates)
        # A newly derived output/status should roll forward the timestamps.
        if updates.get("output") is not None and updates.get("output") != self.output:
            fields["run_completed_at"] = datetime.now(UTC)
        return Simulation(**fields)


__all__ = ["Simulation", "SimulationStatus"]
