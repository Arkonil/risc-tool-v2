"""Repository for managing risk segment details and global application options."""

import typing as t

from risc_tool.data.models.config import OptionsConfig, RiskSegment, RiskSegmentConfig
from risc_tool.data.models.enums import LossRateTypes, Signature
from risc_tool.data.models.types import ChangeIDs
from risc_tool.data.repositories.base import BaseRepository
from risc_tool.utils.logging import get_logger

logger = get_logger(__name__)


class OptionRepository(BaseRepository):
    """Repository managing risk segment tiers, boundary parameters, and iteration thresholds."""

    @property
    def signature(self) -> Signature:
        return Signature.OPTION_REPOSITORY

    def __init__(self) -> None:
        super().__init__()
        self._risk_segment_config = RiskSegmentConfig()
        self._options_config = OptionsConfig()

    def on_dependency_update(self, change_ids: ChangeIDs) -> None:
        """Handle dependency update notifications (no-op as options has no upstream repo)."""
        pass

    @property
    def risk_segment_config(self) -> RiskSegmentConfig:
        return self._risk_segment_config

    @property
    def segments(self) -> list[RiskSegment]:
        return self._risk_segment_config.segments

    @property
    def max_iteration_depth(self) -> int:
        return self._options_config.max_iteration_depth

    @property
    def max_categorical_unique(self) -> int:
        return self._options_config.max_categorical_unique

    def get_color(self, segment_name: str) -> tuple[str, str]:
        """Get (font_color, bg_color) for a risk segment name. Default (#FFFFFF, #3D8F3D) if not found."""
        for seg in self.segments:
            if seg.name == segment_name:
                return (seg.font_color, seg.bg_color)
        return ("#FFFFFF", "#3D8F3D")

    def add_risk_seg_row(self) -> None:
        """Add a new empty risk segment row and recalculate bounds."""
        logger.info("Adding new risk segment row")
        new_seg = RiskSegment(
            name="",
            lower_rate=0.0,
            upper_rate=None,
            bg_color="#000000",
            font_color="#FFFFFF",
            maf_dlr=1.0,
            maf_ulr=1.0,
        )
        self._risk_segment_config.segments.append(new_seg)
        self._risk_segment_config.recalculate_lower_bounds()
        self.notify_subscribers()

    def delete_selected_risk_seg_rows(self, indices: list[int]) -> None:
        """Delete risk segment rows at given indices and recalculate bounds."""
        logger.info("Deleting risk segment rows at indices: %s", indices)
        valid_indices = set(indices)
        self._risk_segment_config.segments = [
            seg
            for i, seg in enumerate(self._risk_segment_config.segments)
            if i not in valid_indices
        ]
        self._risk_segment_config.recalculate_lower_bounds()
        self.notify_subscribers()

    def set_risk_seg_name(self, index: int, name: str) -> None:
        """Update risk segment name at specified index."""
        if 0 <= index < len(self.segments):
            logger.info("Setting risk segment name at index %d to '%s'", index, name)
            self.segments[index].name = name
            self.notify_subscribers()

    def set_risk_seg_upper_rate(self, index: int, upper_rate: float | None) -> None:
        """Update risk segment upper rate bound at specified index and recalculate bounds."""
        if 0 <= index < len(self.segments):
            logger.info(
                "Setting risk segment upper rate at index %d to %s", index, upper_rate
            )
            self.segments[index].upper_rate = upper_rate
            self._risk_segment_config.recalculate_lower_bounds()
            self.notify_subscribers()

    def set_risk_seg_font_color(self, indices: list[int], color: str) -> None:
        """Update font color for risk segments at given indices."""
        logger.debug("Setting font color for indices %s to %s", indices, color)
        for idx in indices:
            if 0 <= idx < len(self.segments):
                self.segments[idx].font_color = color
        self.notify_subscribers()

    def set_risk_seg_bg_color(self, indices: list[int], color: str) -> None:
        """Update background color for risk segments at given indices."""
        logger.debug("Setting background color for indices %s to %s", indices, color)
        for idx in indices:
            if 0 <= idx < len(self.segments):
                self.segments[idx].bg_color = color
        self.notify_subscribers()

    def set_risk_seg_maf(
        self, index: int, maf: float, loss_rate_type: LossRateTypes
    ) -> None:
        """Update Maturity Adjustment Factor (MAF) for segment at specified index."""
        if 0 <= index < len(self.segments):
            logger.info(
                "Setting MAF for index %d (%s) to %f", index, loss_rate_type, maf
            )
            if loss_rate_type == LossRateTypes.DLR:
                self.segments[index].maf_dlr = maf
            else:
                self.segments[index].maf_ulr = maf
            self.notify_subscribers()

    def reset_risk_seg_defaults(self) -> None:
        """Reset risk segments to default values."""
        logger.warning("Resetting risk segment config to defaults")
        self._risk_segment_config = RiskSegmentConfig()
        self.notify_subscribers()

    def to_dict(self) -> dict[str, t.Any]:
        """Serialize repository state to dictionary."""
        return {
            "risk_segment_config": self._risk_segment_config.model_dump(),
            "options_config": self._options_config.model_dump(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, t.Any]) -> "OptionRepository":
        """Deserialize repository state from dictionary."""
        repo = cls()
        if "risk_segment_config" in data:
            repo._risk_segment_config = RiskSegmentConfig.model_validate(
                data["risk_segment_config"]
            )
        if "options_config" in data:
            repo._options_config = OptionsConfig.model_validate(data["options_config"])
        return repo


__all__ = ["OptionRepository"]
