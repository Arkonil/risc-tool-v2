"""Pydantic data models for application configuration.

This module defines models for risk segments, scalar options, and global application options,
providing strong type validation, serialization, and Polars expression generation.
"""

import math
import re
import typing as t
from collections import OrderedDict
from itertools import pairwise

import numpy as np
import pandas as pd
import polars as pl
from pandas.io.formats.style import Styler
from pydantic import BaseModel, Field, field_validator

from risc_tool.data.models.enums import LossRateTypes, RSDetCol
from risc_tool.data.models.object_id import RiskSegmentID


def is_valid_hex_color(color: str) -> bool:
    """Validate hex color string format (e.g. #3D8F3D or #FFFFFF)."""
    return bool(re.match(r"^#(?:[0-9a-fA-F]{3}){1,2}$", color))


class RiskSegment(BaseModel):
    """Represents a single risk tier/segment configuration.

    Attributes:
        name: Name of the risk segment (e.g. "1A", "1B").
        lower_rate: Lower bad rate bound as a decimal (0.0 to 1.0).
        upper_rate: Upper bad rate bound as a decimal, or None for infinity.
        bg_color: Background hex color code for UI styling.
        font_color: Font hex color code for UI styling.
        maf_dlr: Maturity Adjustment Factor for Dollar Bad Rate ($).
        maf_ulr: Maturity Adjustment Factor for Unit Bad Rate (#).
    """

    name: str
    lower_rate: float
    upper_rate: float
    bg_color: str = "#3D8F3D"
    font_color: str = "#FFFFFF"
    maf_dlr: float = 1.0
    maf_ulr: float = 1.0

    @field_validator("bg_color", "font_color")
    @classmethod
    def validate_hex_color(cls, v: str) -> str:
        """Ensure color strings are uppercase hex colors."""
        if not v.startswith("#"):
            v = "#" + v
        if not is_valid_hex_color(v):
            raise ValueError(f"Invalid hex color format: {v}")
        return v.upper()

    @field_validator("maf_dlr", "maf_ulr")
    @classmethod
    def validate_non_negative(cls, v: float) -> float:
        """Ensure MAF factors are non-negative."""
        if v < 0:
            raise ValueError("MAF value must be non-negative")
        return v

    def maf(self, loss_rate_type: LossRateTypes) -> float:
        """Return the appropriate MAF based on the loss rate type."""
        if loss_rate_type == LossRateTypes.DLR:
            return self.maf_dlr
        elif loss_rate_type == LossRateTypes.ULR:
            return self.maf_ulr
        else:
            raise ValueError(f"Unsupported loss rate type: {loss_rate_type}")


def get_default_risk_segments() -> OrderedDict[RiskSegmentID, RiskSegment]:
    """Generate default list of risk segments."""
    return OrderedDict([
        (
            RiskSegmentID(0),
            RiskSegment(
                name="1A",
                lower_rate=0.0,
                upper_rate=0.02,
                bg_color="#3D8F3D",
                font_color="#FFFFFF",
                maf_dlr=1.3,
                maf_ulr=1.3,
            ),
        ),
        (
            RiskSegmentID(1),
            RiskSegment(
                name="1B",
                lower_rate=0.0,
                upper_rate=0.02,
                bg_color="#3D8F3D",
                font_color="#FFFFFF",
                maf_dlr=1.3,
                maf_ulr=1.3,
            ),
        ),
        (
            RiskSegmentID(2),
            RiskSegment(
                name="2A",
                lower_rate=0.02,
                upper_rate=0.04,
                bg_color="#7D9438",
                font_color="#FFFFFF",
                maf_dlr=1.15,
                maf_ulr=1.15,
            ),
        ),
        (
            RiskSegmentID(3),
            RiskSegment(
                name="2B",
                lower_rate=0.02,
                upper_rate=0.04,
                bg_color="#7D9438",
                font_color="#FFFFFF",
                maf_dlr=1.15,
                maf_ulr=1.15,
            ),
        ),
        (
            RiskSegmentID(4),
            RiskSegment(
                name="3A",
                lower_rate=0.04,
                upper_rate=0.07,
                bg_color="#948238",
                font_color="#FFFFFF",
                maf_dlr=1.0,
                maf_ulr=1.0,
            ),
        ),
        (
            RiskSegmentID(5),
            RiskSegment(
                name="3B",
                lower_rate=0.04,
                upper_rate=0.07,
                bg_color="#948238",
                font_color="#FFFFFF",
                maf_dlr=1.0,
                maf_ulr=1.0,
            ),
        ),
        (
            RiskSegmentID(6),
            RiskSegment(
                name="4A",
                lower_rate=0.07,
                upper_rate=0.10,
                bg_color="#8F663D",
                font_color="#FFFFFF",
                maf_dlr=0.9,
                maf_ulr=0.9,
            ),
        ),
        (
            RiskSegmentID(7),
            RiskSegment(
                name="4B",
                lower_rate=0.07,
                upper_rate=0.10,
                bg_color="#8F663D",
                font_color="#FFFFFF",
                maf_dlr=0.9,
                maf_ulr=0.9,
            ),
        ),
        (
            RiskSegmentID(8),
            RiskSegment(
                name="5A",
                lower_rate=0.10,
                upper_rate=float("inf"),
                bg_color="#8F3D3D",
                font_color="#FFFFFF",
                maf_dlr=0.8,
                maf_ulr=0.8,
            ),
        ),
        (
            RiskSegmentID(9),
            RiskSegment(
                name="5B",
                lower_rate=0.10,
                upper_rate=float("inf"),
                bg_color="#8F3D3D",
                font_color="#FFFFFF",
                maf_dlr=0.8,
                maf_ulr=0.8,
            ),
        ),
    ])


class RiskSegmentConfig(BaseModel):
    """Collection of risk segments with boundary integrity and Polars expression support."""

    segments: OrderedDict[RiskSegmentID, RiskSegment] = Field(
        default_factory=get_default_risk_segments
    )

    def recalculate_lower_bounds(self) -> None:
        """Recalculate lower rate bounds to maintain contiguous risk tier boundaries."""
        for i, (_, segment) in enumerate(self.segments.items()):
            if i == 0:
                segment.lower_rate = 0.0
                continue

            prev_segment = self.segments[list(self.segments.keys())[i - 1]]
            if segment.upper_rate == prev_segment.upper_rate:
                segment.lower_rate = prev_segment.lower_rate
            else:
                segment.lower_rate = prev_segment.upper_rate

    def get_duplicate_names(self) -> list[str]:
        """Return list of duplicate segment names if any exist."""
        seen: set[str] = set()
        duplicates: set[str] = set()
        for seg in self.segments.values():
            if seg.name in seen:
                duplicates.add(seg.name)
            seen.add(seg.name)
        return sorted(duplicates)

    def has_finite_upper_bound_segment(
        self, segment_ids: list[RiskSegmentID] | None = None
    ) -> bool:
        """Return True if at least one selected segment has a finite upper rate bound."""
        selected_segments = self.get_segments(segment_ids, original=True)
        return any(math.isfinite(seg.upper_rate) for seg in selected_segments.values())

    def to_polars_expr(self, loss_rate_col: str) -> pl.Expr:
        """Build Polars expression mapping loss_rate_col values to risk segment names.

        Args:
            loss_rate_col: Column name containing numerical loss rates.

        Returns:
            A Polars expression resulting in segment names.
        """
        expr: pl.Expr | None = None
        col_expr = pl.col(loss_rate_col)

        for seg in self.segments.values():
            cond = (col_expr >= seg.lower_rate) & (col_expr < seg.upper_rate)

            if expr is None:
                expr = pl.when(cond).then(pl.lit(seg.name))
            else:
                expr = expr.when(cond).then(pl.lit(seg.name))

        if expr is None:
            return pl.lit(None)

        return expr.otherwise(None)

    def to_pandas_styler(
        self,
        apply_colors_to_name_col: bool = False,
        format_numbers: bool = False,
        all_selected: bool = False,
    ) -> Styler:
        """Build a pandas Styler table for editing risk segment details.

        Args:
            apply_colors_to_name_col: If True, also apply font/background colors
                to the risk segment name column.
            format_numbers: If True, format rate values as percentage strings
                with two decimals (and an infinity symbol for unbounded rates).
            all_selected: Initial value used for the SELECTED column of every row.

        Returns:
            A configured pandas Styler with per-row font/background colors applied.
        """
        records: OrderedDict[RiskSegmentID, dict[RSDetCol, t.Any]] = OrderedDict()

        for seg_id, seg in self.segments.items():
            records[seg_id] = {
                RSDetCol.SELECTED: all_selected,
                RSDetCol.RISK_SEGMENT: seg.name,
                RSDetCol.LOWER_RATE: seg.lower_rate * 100.0,
                RSDetCol.UPPER_RATE: seg.upper_rate * 100.0
                if seg.upper_rate != float("inf")
                else None,
                RSDetCol.FONT_COLOR: seg.font_color,
                RSDetCol.BG_COLOR: seg.bg_color,
            }

            if format_numbers:
                records[seg_id][RSDetCol.LOWER_RATE] = (
                    f"{records[seg_id][RSDetCol.LOWER_RATE]:.2f}%"
                )

                if records[seg_id][RSDetCol.UPPER_RATE] is not None and not np.isnan(
                    records[seg_id][RSDetCol.UPPER_RATE]
                ):
                    records[seg_id][RSDetCol.UPPER_RATE] = (
                        f"{records[seg_id][RSDetCol.UPPER_RATE]:.2f}%"
                    )
                else:
                    records[seg_id][RSDetCol.UPPER_RATE] = "∞"

        df = pd.DataFrame.from_dict(records, orient="index")
        styler = df.style

        for row_idx in df.index:
            font_color = df.loc[row_idx, RSDetCol.FONT_COLOR]
            bg_color = df.loc[row_idx, RSDetCol.BG_COLOR]

            # Apply text & background color styling to Font Color and Background Color cells
            styler = styler.set_properties(
                subset=(
                    slice(row_idx, row_idx),
                    slice(RSDetCol.FONT_COLOR.value, RSDetCol.BG_COLOR.value),
                ),
                **{
                    "color": str(font_color),
                    "background-color": str(bg_color),
                },
            )

            if apply_colors_to_name_col:
                # Apply text & background color styling to Risk Segment Name cells
                styler = styler.set_properties(
                    subset=(
                        slice(row_idx, row_idx),
                        slice(RSDetCol.RISK_SEGMENT.value, RSDetCol.RISK_SEGMENT.value),
                    ),
                    **{
                        "color": str(font_color),
                        "background-color": str(bg_color),
                    },
                )

        return styler

    def get_segments(
        self, segment_ids: list[RiskSegmentID] | None = None, original: bool = True
    ) -> OrderedDict[RiskSegmentID, RiskSegment]:
        """Return the requested risk segments, optionally re-distributed over their bounds.

        Args:
            segment_ids: Optional list of segment IDs to include. If None, all
                segments are considered.
            original: If True, return the original segment objects unchanged.
                If False, return copies whose lower/upper rates are evenly split
                across each shared upper-rate band.

        Returns:
            An ordered dictionary of RiskSegmentID to RiskSegment matching the
            requested criteria.
        """
        if segment_ids is None:
            segment_ids = list(self.segments.keys())

        if original:
            return OrderedDict(
                (seg_id, self.segments[seg_id])
                for seg_id in segment_ids
                if seg_id in self.segments
            )

        result: OrderedDict[RiskSegmentID, RiskSegment] = OrderedDict()

        common_upper_rate_map: OrderedDict[float, list[RiskSegmentID]] = OrderedDict()
        for seg_id in segment_ids:
            if seg_id not in self.segments:
                continue

            seg = self.segments[seg_id]
            common_upper_rate_map.setdefault(seg.upper_rate, []).append(seg_id)

        max_diff = 0.0

        for upper_rate, seg_ids in common_upper_rate_map.items():
            lower_rate = min(self.segments[seg_id].lower_rate for seg_id in seg_ids)

            pw = pairwise(
                np.linspace(
                    lower_rate,
                    upper_rate if upper_rate < float("inf") else lower_rate + max_diff,
                    num=len(seg_ids) + 1,
                    retstep=False,
                )
            )

            for seg_id, (lower_rate_1, upper_rate_1) in zip(seg_ids, pw):
                seg = self.segments[seg_id]
                result[seg_id] = seg.model_copy(
                    update={
                        "lower_rate": lower_rate_1,
                        "upper_rate": upper_rate_1,
                    }
                )

            max_diff = max(max_diff, upper_rate - lower_rate)

        return result


class LossRateScalar(BaseModel):
    """Scalar rates for annualization and risk scalar factor computation.

    Attributes:
        loss_rate_type: Type of loss rate ($ Bad Rate or # Bad Rate).
        current_rate: Current MOB loss rate as a decimal (or None if unconfigured).
        lifetime_rate: Lifetime MOB loss rate as a decimal (or None if unconfigured).
    """

    loss_rate_type: LossRateTypes
    current_rate: float | None = None
    lifetime_rate: float | None = None

    @property
    def portfolio_scalar(self) -> float:
        """Compute portfolio scalar (lifetime_rate / current_rate). Default 1.0 if unset."""
        if (
            self.current_rate is not None
            and self.current_rate > 0
            and self.lifetime_rate is not None
        ):
            return self.lifetime_rate / self.current_rate
        return 1.0

    def get_risk_scalar_factor_expr(self, maf_col_or_expr: str | pl.Expr) -> pl.Expr:
        """Build Polars expression for Risk Scalar Factor: max(maf * portfolio_scalar, 1.0).

        Args:
            maf_col_or_expr: Column name or Polars expression for Maturity Adjustment Factor.

        Returns:
            Polars expression evaluating risk scalar factor.
        """
        maf_expr = (
            pl.col(maf_col_or_expr)
            if isinstance(maf_col_or_expr, str)
            else maf_col_or_expr
        )
        scaled = maf_expr * self.portfolio_scalar
        return pl.when(scaled < 1.0).then(1.0).otherwise(scaled)


class OptionsConfig(BaseModel):
    """Global configuration options for iteration building.

    Attributes:
        max_categorical_unique: Maximum distinct unique values allowed for categorical splits.
    """

    max_categorical_unique: int = 20


__all__ = [
    "LossRateScalar",
    "OptionsConfig",
    "RiskSegment",
    "RiskSegmentConfig",
    "get_default_risk_segments",
    "is_valid_hex_color",
]
