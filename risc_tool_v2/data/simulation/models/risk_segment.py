"""Risk segment models for simulation configuration."""

import json
import math
import re
import typing as t
from collections import OrderedDict
from itertools import pairwise
from uuid import NAMESPACE_URL, uuid5

import numpy as np
import polars as pl
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from risc_tool_v2.data.core.enums import LossRateTypes
from risc_tool_v2.data.core.uid import RiskSegmentID
from risc_tool_v2.data.simulation.json.simulation_json import (
    RiskSegmentConfigJSON,
    RiskSegmentJSON,
)


def is_valid_hex_color(color: str) -> bool:
    """Validate hex color string format (e.g. #3D8F3D or #FFFFFF)."""
    return bool(re.match(r"^#(?:[0-9a-fA-F]{3}){1,2}$", color))


class RiskSegment(BaseModel, frozen=True):
    """Represents a single risk tier/segment configuration.

    Attributes:
        uid: Content-addressed unique identifier for the segment.
        name: Name of the risk segment (e.g. "1A", "1B").
        upper_rate: Upper bad rate bound as a decimal, or infinity for no upper bound.
        bg_color: Background hex color code for UI styling.
        font_color: Font hex color code for UI styling.
        maf_dlr: Maturity Adjustment Factor for Dollar Bad Rate ($).
        maf_ulr: Maturity Adjustment Factor for Unit Bad Rate (#).
        selected: Whether this segment is selected for a simulation.
    """

    model_config = ConfigDict(extra="forbid")

    uid: RiskSegmentID = RiskSegmentID.UNSET
    name: str = Field(min_length=1)
    upper_rate: float = Field(gt=0.0)
    bg_color: str = "#3D8F3D"
    font_color: str = "#FFFFFF"
    maf_dlr: float = Field(default=1.0, ge=0.0)
    maf_ulr: float = Field(default=1.0, ge=0.0)
    selected: bool = True

    @field_validator("bg_color", "font_color")
    @classmethod
    def validate_hex_color(cls, v: str) -> str:
        """Ensure color strings are uppercase hex colors."""
        if not v.startswith("#"):
            v = "#" + v
        if not is_valid_hex_color(v):
            raise ValueError(f"Invalid hex color format: {v}")
        return v.upper()

    @model_validator(mode="after")
    def _derive_uid(self) -> "RiskSegment":
        """Derive the content-addressed uid when it is left unset.

        An explicitly provided uid is preserved, which allows the
        EMPTY/TEMPORARY sentinels and deserialized identities to survive
        construction.

        Returns:
            This instance with the uid derived if none was set.
        """
        if self.uid is RiskSegmentID.UNSET:
            # Frozen model: bypass immutability to fill in the derived uid.
            object.__setattr__(self, "uid", self.create_hash())
        return self

    def create_hash(self) -> RiskSegmentID:
        """Return a content-addressed RiskSegmentID derived from this content.

        The ID hashes all content fields (including selected) except the uid
        itself, so identical content always produces the same identity.

        Returns:
            A RiskSegmentID whose value is a UUIDv5 hash of the content.
        """
        payload = json.dumps(
            {
                "name": self.name,
                "upper_rate": self.upper_rate,
                "bg_color": self.bg_color,
                "font_color": self.font_color,
                "maf_dlr": self.maf_dlr,
                "maf_ulr": self.maf_ulr,
                "selected": self.selected,
            },
            sort_keys=True,
            default=str,
        )
        return RiskSegmentID(uuid5(NAMESPACE_URL, payload))

    def with_updates(self, **updates: t.Any) -> "RiskSegment":
        """Return a copy of this segment with updated fields.

        The copy re-derives its content-addressed identity when any content
        field changes; an unchanged content keeps this segment's identity.

        Args:
            **updates: Field values to override on the copy.

        Returns:
            A new RiskSegment instance with the updates applied.
        """
        fields: dict[str, t.Any] = {
            "name": self.name,
            "upper_rate": self.upper_rate,
            "bg_color": self.bg_color,
            "font_color": self.font_color,
            "maf_dlr": self.maf_dlr,
            "maf_ulr": self.maf_ulr,
            "selected": self.selected,
        }
        content_changed = any(
            key in updates and updates[key] != fields[key] for key in fields
        )
        fields.update(updates)

        uid: RiskSegmentID | None
        if "uid" in updates:
            uid = fields.pop("uid")
        elif content_changed and self.uid not in (
            RiskSegmentID.EMPTY,
            RiskSegmentID.TEMPORARY,
        ):
            uid = None  # Re-derive from the new content.
        else:
            uid = self.uid

        return RiskSegment(**({"uid": uid} if uid is not None else {}), **fields)

    def maf(self, loss_rate_type: LossRateTypes) -> float:
        """Return the appropriate MAF based on the loss rate type."""
        if loss_rate_type == LossRateTypes.DLR:
            return self.maf_dlr
        elif loss_rate_type == LossRateTypes.ULR:
            return self.maf_ulr
        else:
            raise ValueError(f"Unsupported loss rate type: {loss_rate_type}")


def get_default_risk_segments() -> OrderedDict[RiskSegmentID, RiskSegment]:
    """Generate default list of risk segments.

    Each segment's OrderedDict key is its content-addressed RiskSegmentID
    (a UUIDv5 hash of the segment content, including the selected flag).

    Returns:
        An ordered mapping of RiskSegmentID to RiskSegment, in band order.
    """
    segments = [
        RiskSegment(
            name="1A",
            upper_rate=0.02,
            bg_color="#3D8F3D",
            font_color="#FFFFFF",
            maf_dlr=1.3,
            maf_ulr=1.3,
        ),
        RiskSegment(
            name="1B",
            upper_rate=0.02,
            bg_color="#3D8F3D",
            font_color="#FFFFFF",
            maf_dlr=1.3,
            maf_ulr=1.3,
        ),
        RiskSegment(
            name="2A",
            upper_rate=0.04,
            bg_color="#7D9438",
            font_color="#FFFFFF",
            maf_dlr=1.15,
            maf_ulr=1.15,
        ),
        RiskSegment(
            name="2B",
            upper_rate=0.04,
            bg_color="#7D9438",
            font_color="#FFFFFF",
            maf_dlr=1.15,
            maf_ulr=1.15,
        ),
        RiskSegment(
            name="3A",
            upper_rate=0.07,
            bg_color="#948238",
            font_color="#FFFFFF",
            maf_dlr=1.0,
            maf_ulr=1.0,
        ),
        RiskSegment(
            name="3B",
            upper_rate=0.07,
            bg_color="#948238",
            font_color="#FFFFFF",
            maf_dlr=1.0,
            maf_ulr=1.0,
        ),
        RiskSegment(
            name="4A",
            upper_rate=0.10,
            bg_color="#8F663D",
            font_color="#FFFFFF",
            maf_dlr=0.9,
            maf_ulr=0.9,
        ),
        RiskSegment(
            name="4B",
            upper_rate=0.10,
            bg_color="#8F663D",
            font_color="#FFFFFF",
            maf_dlr=0.9,
            maf_ulr=0.9,
        ),
        RiskSegment(
            name="5A",
            upper_rate=float("inf"),
            bg_color="#8F3D3D",
            font_color="#FFFFFF",
            maf_dlr=0.8,
            maf_ulr=0.8,
        ),
        RiskSegment(
            name="5B",
            upper_rate=float("inf"),
            bg_color="#8F3D3D",
            font_color="#FFFFFF",
            maf_dlr=0.8,
            maf_ulr=0.8,
        ),
    ]
    return OrderedDict((seg.uid, seg) for seg in segments)


class RiskSegmentConfig(BaseModel, frozen=True):
    """Collection of risk segments with boundary integrity and Polars expression support.

    Lower bounds are derived from upper bounds: each segment's lower bound is the
    previous segment's upper bound (or 0.0 for the first segment). Segments with
    the same upper bound share the same lower bound.
    """

    model_config = ConfigDict(extra="forbid")

    segments: OrderedDict[RiskSegmentID, RiskSegment] = Field(
        default_factory=get_default_risk_segments
    )

    def _compute_raw_lower_bounds(self) -> dict[RiskSegmentID, float]:
        """Compute lower bounds directly from configured upper bounds.

        Segments sharing the same upper bound share the same (unsplit) lower bound.
        This is only used as the group starting point for `_normalize_upper_rates`.

        Returns:
            Mapping of segment ID to its raw (unnormalized) lower bound.
        """
        lower_bounds: dict[RiskSegmentID, float] = {}
        segment_items = list(self.segments.items())

        for i, (seg_id, segment) in enumerate(segment_items):
            if i == 0:
                lower_bounds[seg_id] = 0.0
            else:
                prev_segment = segment_items[i - 1][1]
                if segment.upper_rate == prev_segment.upper_rate:
                    lower_bounds[seg_id] = lower_bounds[segment_items[i - 1][0]]
                else:
                    lower_bounds[seg_id] = prev_segment.upper_rate

        return lower_bounds

    def _normalize_upper_rates(self) -> dict[RiskSegmentID, float]:
        """Spread segments sharing an upper bound into distinct, ascending sub-bounds.

        Segments with duplicate upper rates are split evenly across their shared
        range so each one becomes independently reachable (e.g. in `to_polars_expr`).
        Infinite upper rates are treated as `lower bound + largest observed finite
        span` for splitting purposes, except for the very last segment overall,
        which always keeps a true infinite upper bound so no values go unmatched.

        Returns:
            Mapping of segment ID to its normalized upper bound.
        """
        segment_items = list(self.segments.items())
        if not segment_items:
            return {}

        raw_lower_bounds = self._compute_raw_lower_bounds()
        last_seg_id = segment_items[-1][0]

        common_upper_rate_map: OrderedDict[float, list[RiskSegmentID]] = OrderedDict()
        for seg_id, segment in segment_items:
            common_upper_rate_map.setdefault(segment.upper_rate, []).append(seg_id)

        normalized: dict[RiskSegmentID, float] = {}
        max_diff = 0.0

        for upper_rate, seg_ids in common_upper_rate_map.items():
            lower_rate = raw_lower_bounds[seg_ids[0]]
            finite_upper = (
                upper_rate if math.isfinite(upper_rate) else lower_rate + max_diff
            )

            splits = pairwise(
                np.linspace(lower_rate, finite_upper, num=len(seg_ids) + 1)
            )
            for seg_id, (_, seg_upper) in zip(seg_ids, splits):
                normalized[seg_id] = float(seg_upper)

            if not math.isfinite(upper_rate) and last_seg_id in seg_ids:
                normalized[last_seg_id] = float("inf")

            max_diff = max(max_diff, finite_upper - lower_rate)

        return normalized

    def _compute_lower_bounds(self) -> dict[RiskSegmentID, float]:
        """Compute lower bounds for all segments from normalized upper bounds.

        Returns:
            Mapping of segment ID to its computed lower bound.
        """
        normalized_upper = self._normalize_upper_rates()
        lower_bounds: dict[RiskSegmentID, float] = {}
        segment_items = list(self.segments.items())

        for i, (seg_id, _) in enumerate(segment_items):
            if i == 0:
                lower_bounds[seg_id] = 0.0
            else:
                prev_seg_id = segment_items[i - 1][0]
                lower_bounds[seg_id] = normalized_upper[prev_seg_id]

        return lower_bounds

    def get_segments(
        self,
        segment_ids: list[RiskSegmentID] | None = None,
        *,
        normalize: bool,
        selected: bool = True,
    ) -> OrderedDict[RiskSegmentID, RiskSegment]:
        """Return the requested risk segments, optionally normalized to distinct bounds.

        Args:
            segment_ids: Optional list of segment IDs to include. If None, the
                segments are filtered by the ``selected`` flag instead.
            normalize: If False, return the original segment objects unchanged.
                If True, return copies whose upper_rate is spread across shared
                and/or infinite ranges so duplicate segments become distinct.
            selected: When ``segment_ids`` is None, only return segments whose
                ``selected`` flag matches this value. Ignored when
                ``segment_ids`` is provided.

        Returns:
            An ordered dictionary of RiskSegmentID to RiskSegment matching the
            requested criteria.
        """
        if segment_ids is None:
            segment_ids = [
                seg_id
                for seg_id, seg in self.segments.items()
                if seg.selected == selected
            ]

        if not normalize:
            return OrderedDict(
                (seg_id, self.segments[seg_id])
                for seg_id in segment_ids
                if seg_id in self.segments
            )

        normalized_upper = self._normalize_upper_rates()

        result: OrderedDict[RiskSegmentID, RiskSegment] = OrderedDict()
        for seg_id in segment_ids:
            if seg_id not in self.segments:
                continue
            seg = self.segments[seg_id]
            result[seg_id] = seg.model_copy(
                update={"upper_rate": normalized_upper[seg_id]}
            )

        return result

    def has_finite_upper_bound_segment(
        self, segment_ids: list[RiskSegmentID] | None = None
    ) -> bool:
        """Return True if at least one selected segment has a finite upper rate bound."""
        selected_segments = self.get_segments(segment_ids, normalize=False)
        return any(math.isfinite(seg.upper_rate) for seg in selected_segments.values())

    def get_duplicate_names(self) -> list[str]:
        """Return list of duplicate segment names if any exist."""
        seen: set[str] = set()
        duplicates: set[str] = set()
        for seg in self.segments.values():
            if seg.name in seen:
                duplicates.add(seg.name)
            seen.add(seg.name)
        return sorted(duplicates)

    def create_hash(self) -> str:
        """Return a content hash string for this config's risk segments.

        The hash composes each segment's content-addressed identity in
        insertion order, since segment order is semantically meaningful for
        derived band bounds.

        Returns:
            A UUIDv5 hash string derived from the ordered segments.
        """
        payload = json.dumps({
            str(seg_id): str(seg.create_hash()) for seg_id, seg in self.segments.items()
        })
        return str(uuid5(NAMESPACE_URL, payload))

    def to_polars_expr(self, loss_rate_col: str) -> pl.Expr:
        """Build Polars expression mapping loss_rate_col values to risk segment names.

        Args:
            loss_rate_col: Column name containing numerical loss rates.

        Returns:
            A Polars expression resulting in segment names.
        """
        lower_bounds = self._compute_lower_bounds()
        upper_bounds = self._normalize_upper_rates()
        expr: pl.Expr | None = None
        col_expr = pl.col(loss_rate_col)

        for seg_id, seg in self.segments.items():
            lower = lower_bounds[seg_id]
            upper = upper_bounds[seg_id]
            cond = (col_expr >= lower) & (col_expr < upper)

            if expr is None:
                expr = pl.when(cond).then(pl.lit(seg.name))
            else:
                expr = expr.when(cond).then(pl.lit(seg.name))

        if expr is None:
            return pl.lit(None)

        return expr.otherwise(None)

    def to_dict(self) -> RiskSegmentConfigJSON:
        return RiskSegmentConfigJSON(
            segments=OrderedDict(
                (
                    seg_id,
                    RiskSegmentJSON(
                        name=seg.name,
                        upper_rate=seg.upper_rate,
                        bg_color=seg.bg_color,
                        font_color=seg.font_color,
                        maf_dlr=seg.maf_dlr,
                        maf_ulr=seg.maf_ulr,
                        selected=seg.selected,
                    ),
                )
                for seg_id, seg in self.segments.items()
            )
        )

    @classmethod
    def from_dict(cls, data: RiskSegmentConfigJSON) -> "RiskSegmentConfig":
        segments: OrderedDict[RiskSegmentID, RiskSegment] = OrderedDict()
        for seg_id, seg_json in data.segments.items():
            seg = RiskSegment(
                uid=seg_id,
                name=seg_json.name,
                upper_rate=seg_json.upper_rate,
                bg_color=seg_json.bg_color,
                font_color=seg_json.font_color,
                maf_dlr=seg_json.maf_dlr,
                maf_ulr=seg_json.maf_ulr,
                selected=seg_json.selected,
            )

            if seg.uid in (
                RiskSegmentID.UNSET,
                RiskSegmentID.EMPTY,
                RiskSegmentID.TEMPORARY,
            ):
                seg = seg.with_updates(uid=seg.uid)
            segments[seg.uid] = seg
        return RiskSegmentConfig(segments=segments)

    def with_updates(
        self, seg_id: RiskSegmentID, **updates: t.Any
    ) -> "RiskSegmentConfig":
        """Return a copy of this config with one segment updated and re-keyed.

        The updated segment's content is mutated via ``RiskSegment.with_updates``
        and, because its content-addressed identity may change, it is re-keyed in
        the new OrderedDict under its derived uid while preserving instantiation
        order.

        Args:
            seg_id: The ID of the segment to update.
            **updates: Field values to override on that segment.

        Returns:
            A new RiskSegmentConfig with the updated, re-keyed segment.

        Raises:
            ValueError: If ``seg_id`` is not present in this config.
        """
        if seg_id not in self.segments:
            raise ValueError(f"Risk segment not found: {seg_id}")
        new_segments: OrderedDict[RiskSegmentID, RiskSegment] = OrderedDict()
        for sid, seg in self.segments.items():
            if sid != seg_id:
                new_segments[sid] = seg
                continue
            updated = seg.with_updates(**updates)
            new_segments[updated.uid] = updated
        return RiskSegmentConfig(segments=new_segments)

    def with_selected(
        self, seg_id: RiskSegmentID, selected: bool
    ) -> "RiskSegmentConfig":
        """Return a copy of this config with a segment's selected flag toggled.

        Args:
            seg_id: The ID of the segment to toggle.
            selected: The new selected flag value for the segment.

        Returns:
            A new RiskSegmentConfig with the segment re-keyed under its new
            content-addressed identity.
        """
        return self.with_updates(seg_id, selected=selected)


__all__ = [
    "RiskSegment",
    "RiskSegmentConfig",
    "get_default_risk_segments",
    "is_valid_hex_color",
]
