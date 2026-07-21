"""Repository for managing annualization rates and loss rate scalars."""

import typing as t

from risc_tool.data.models.config import LossRateScalar
from risc_tool.data.models.enums import LossRateTypes, Signature
from risc_tool.data.models.types import ChangeIDs
from risc_tool.data.repositories.base import BaseRepository
from risc_tool.utils.logging import get_logger

logger = get_logger(__name__)


class ScalarRepository(BaseRepository):
    """Repository managing current and lifetime bad rates for ULR and DLR metrics."""

    @property
    def signature(self) -> Signature:
        return Signature.SCALAR_REPOSITORY

    def __init__(self) -> None:
        super().__init__()
        self._scalars = {
            LossRateTypes.ULR: LossRateScalar(loss_rate_type=LossRateTypes.ULR),
            LossRateTypes.DLR: LossRateScalar(loss_rate_type=LossRateTypes.DLR),
        }

    def on_dependency_update(self, change_ids: ChangeIDs) -> None:
        """Handle dependency updates (no-op as scalars has no upstream repo dependencies)."""
        pass

    def get_scalar(self, loss_rate_type: LossRateTypes) -> LossRateScalar:
        """Get the LossRateScalar configuration for ULR or DLR."""
        return self._scalars[loss_rate_type]

    def set_current_rate(
        self, loss_rate_type: LossRateTypes, current_rate: float | None
    ) -> None:
        """Set the current bad rate for the specified loss rate type."""
        logger.info("Setting current rate for %s to %s", loss_rate_type, current_rate)
        self._scalars[loss_rate_type].current_rate = current_rate
        self.notify_subscribers()

    def set_lifetime_rate(
        self, loss_rate_type: LossRateTypes, lifetime_rate: float | None
    ) -> None:
        """Set the lifetime bad rate for the specified loss rate type."""
        logger.info("Setting lifetime rate for %s to %s", loss_rate_type, lifetime_rate)
        self._scalars[loss_rate_type].lifetime_rate = lifetime_rate
        self.notify_subscribers()

    def to_dict(self) -> dict[str, t.Any]:
        """Serialize repository state to dictionary."""
        return {"scalars": {k.value: v.model_dump() for k, v in self._scalars.items()}}

    @classmethod
    def from_dict(cls, data: dict[str, t.Any]) -> "ScalarRepository":
        """Deserialize repository state from dictionary."""
        repo = cls()
        if "scalars" in data:
            for k_str, val in data["scalars"].items():
                loss_rate_type = LossRateTypes(k_str)
                repo._scalars[loss_rate_type] = LossRateScalar.model_validate(val)
        return repo


__all__ = ["ScalarRepository"]
