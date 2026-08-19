"""Repository for managing risk segment details and global application options."""

from risc_tool.data.models.config import OptionsConfig, RiskSegment, RiskSegmentConfig
from risc_tool.data.models.enums import LossRateTypes, Signature
from risc_tool.data.models.json_models import OptionsRepositoryJSON
from risc_tool.data.models.object_id import RiskSegmentID
from risc_tool.data.models.types import ChangeIDs
from risc_tool.data.repositories.base import BaseRepository
from risc_tool.utils.logging import get_logger

logger = get_logger(__name__)


class OptionRepository(BaseRepository):
    """Repository managing risk segment tiers, boundary parameters, and iteration thresholds."""

    @property
    def signature(self) -> Signature:
        """Get the component signature for change tracking.

        Returns:
            Signature.OPTION_REPOSITORY
        """
        return Signature.OPTION_REPOSITORY

    def __init__(self) -> None:
        """Initialize the OptionRepository with default configs."""
        super().__init__()
        self.__risk_segment_config = RiskSegmentConfig()
        self.__options_config = OptionsConfig()

    def on_dependency_update(self, change_ids: ChangeIDs) -> None:
        """Handle dependency update notifications (no-op as options has no upstream repo)."""

    @property
    def risk_segments(self):
        """The RiskSegmentConfig with all defined risk segments."""
        return self.__risk_segment_config

    @property
    def segments(self):
        """The mapping of RiskSegmentID to RiskSegment."""
        return self.risk_segments.segments

    @property
    def max_categorical_unique(self) -> int:
        """Maximum allowed unique categorical values before a warning is shown."""
        return self.__options_config.max_categorical_unique

    def get_color(self, segment_id: RiskSegmentID) -> tuple[str, str]:
        """Get (font_color, bg_color) for a risk segment name. Default (#FFFFFF, #3D8F3D) if not found."""
        segment = self.segments.get(segment_id)

        if segment is None:
            return ("#FFFFFF", "#3D8F3D")

        return (segment.font_color, segment.bg_color)

    def add_risk_seg_row(self) -> None:
        """Add a new empty risk segment row and recalculate bounds."""
        logger.info("Adding new risk segment row")
        new_seg = RiskSegment(
            name="",
            lower_rate=0.0,
            upper_rate=float("inf"),
            bg_color="#000000",
            font_color="#FFFFFF",
            maf_dlr=1.0,
            maf_ulr=1.0,
        )
        seg_id = RiskSegmentID(self._get_new_id(self.segments.keys()))
        self.__risk_segment_config.segments[seg_id] = new_seg
        self.__risk_segment_config.recalculate_lower_bounds()
        self.notify_subscribers()

    def delete_selected_risk_seg_rows(self, segment_ids: list[RiskSegmentID]) -> None:
        """Delete risk segment rows at given indices and recalculate bounds."""
        logger.info("Deleting risk segment rows with IDs: %s", segment_ids)

        for seg_id in segment_ids:
            self.__risk_segment_config.segments.pop(seg_id, None)

        self.__risk_segment_config.recalculate_lower_bounds()
        self.notify_subscribers()

    def set_risk_seg_name(self, segment_id: RiskSegmentID, name: str) -> None:
        """Update risk segment name at specified index."""
        segment = self.segments.get(segment_id)
        if segment is not None:
            logger.info("Setting risk segment name for ID %s to '%s'", segment_id, name)
            segment.name = name
            self.notify_subscribers()

    def set_risk_seg_upper_rate(
        self, segment_id: RiskSegmentID, upper_rate: float
    ) -> None:
        """Update risk segment upper rate bound for specified segment ID and recalculate bounds."""
        segment = self.segments.get(segment_id)
        if segment is not None:
            logger.info(
                "Setting risk segment upper rate for ID %s to %s",
                segment_id,
                upper_rate,
            )
            segment.upper_rate = upper_rate
            self.__risk_segment_config.recalculate_lower_bounds()
            self.notify_subscribers()

    def set_risk_seg_font_color(
        self, segment_ids: list[RiskSegmentID], color: str
    ) -> None:
        """Update font color for risk segments with given IDs."""
        logger.debug("Setting font color for segment IDs %s to %s", segment_ids, color)
        for seg_id in segment_ids:
            segment = self.segments.get(seg_id)
            if segment is not None:
                segment.font_color = color
        self.notify_subscribers()

    def set_risk_seg_bg_color(
        self, segment_ids: list[RiskSegmentID], color: str
    ) -> None:
        """Update background color for risk segments with given IDs."""
        logger.debug(
            "Setting background color for segment IDs %s to %s", segment_ids, color
        )
        for seg_id in segment_ids:
            segment = self.segments.get(seg_id)
            if segment is not None:
                segment.bg_color = color
        self.notify_subscribers()

    def set_risk_seg_maf(
        self, segment_id: RiskSegmentID, maf: float, loss_rate_type: LossRateTypes
    ) -> None:
        """Update Maturity Adjustment Factor (MAF) for segment with specified ID."""
        segment = self.segments.get(segment_id)

        if segment is not None:
            logger.info(
                "Setting MAF for ID %s (%s) to %f", segment_id, loss_rate_type, maf
            )
            if loss_rate_type == LossRateTypes.DLR:
                segment.maf_dlr = maf
            else:
                segment.maf_ulr = maf

            self.notify_subscribers()

    def reset_risk_seg_defaults(self) -> None:
        """Reset risk segments to default values."""
        logger.warning("Resetting risk segment config to defaults")
        self.__risk_segment_config = RiskSegmentConfig()
        self.notify_subscribers()

    def to_dict(self):
        """Serialize repository state to OptionsRepositoryJSON Pydantic model."""
        return OptionsRepositoryJSON(
            risk_segments=self.__risk_segment_config,
            options_config=self.__options_config,
        )

    @classmethod
    def from_dict(cls, data: OptionsRepositoryJSON):
        """Deserialize repository state from OptionsRepositoryJSON Pydantic model or dict."""
        repo = cls()
        repo.__risk_segment_config = data.risk_segments
        repo.__options_config = data.options_config
        return repo


__all__ = ["OptionRepository"]
