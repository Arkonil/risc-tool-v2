"""Pydantic data models for application configuration.

This module defines models for risk segments, scalar options, and global application options,
providing strong type validation, serialization, and Polars expression generation.
"""

import re

import polars as pl
from pydantic import BaseModel, Field, field_validator

from risc_tool.data.models.enums import LossRateTypes


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
    lower_rate: float = 0.0
    upper_rate: float | None = None
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


def get_default_risk_segments() -> list[RiskSegment]:
    """Generate default list of risk segments."""
    return [
        RiskSegment(
            name="1A",
            lower_rate=0.0,
            upper_rate=0.02,
            bg_color="#3D8F3D",
            font_color="#FFFFFF",
            maf_dlr=1.3,
            maf_ulr=1.3,
        ),
        RiskSegment(
            name="1B",
            lower_rate=0.0,
            upper_rate=0.02,
            bg_color="#3D8F3D",
            font_color="#FFFFFF",
            maf_dlr=1.3,
            maf_ulr=1.3,
        ),
        RiskSegment(
            name="2A",
            lower_rate=0.02,
            upper_rate=0.04,
            bg_color="#7D9438",
            font_color="#FFFFFF",
            maf_dlr=1.15,
            maf_ulr=1.15,
        ),
        RiskSegment(
            name="2B",
            lower_rate=0.02,
            upper_rate=0.04,
            bg_color="#7D9438",
            font_color="#FFFFFF",
            maf_dlr=1.15,
            maf_ulr=1.15,
        ),
        RiskSegment(
            name="3A",
            lower_rate=0.04,
            upper_rate=0.07,
            bg_color="#948238",
            font_color="#FFFFFF",
            maf_dlr=1.0,
            maf_ulr=1.0,
        ),
        RiskSegment(
            name="3B",
            lower_rate=0.04,
            upper_rate=0.07,
            bg_color="#948238",
            font_color="#FFFFFF",
            maf_dlr=1.0,
            maf_ulr=1.0,
        ),
        RiskSegment(
            name="4A",
            lower_rate=0.07,
            upper_rate=0.10,
            bg_color="#8F663D",
            font_color="#FFFFFF",
            maf_dlr=0.9,
            maf_ulr=0.9,
        ),
        RiskSegment(
            name="4B",
            lower_rate=0.07,
            upper_rate=0.10,
            bg_color="#8F663D",
            font_color="#FFFFFF",
            maf_dlr=0.9,
            maf_ulr=0.9,
        ),
        RiskSegment(
            name="5A",
            lower_rate=0.10,
            upper_rate=None,
            bg_color="#8F3D3D",
            font_color="#FFFFFF",
            maf_dlr=0.8,
            maf_ulr=0.8,
        ),
        RiskSegment(
            name="5B",
            lower_rate=0.10,
            upper_rate=None,
            bg_color="#8F3D3D",
            font_color="#FFFFFF",
            maf_dlr=0.8,
            maf_ulr=0.8,
        ),
    ]


class RiskSegmentConfig(BaseModel):
    """Collection of risk segments with boundary integrity and Polars expression support."""

    segments: list[RiskSegment] = Field(default_factory=get_default_risk_segments)

    def recalculate_lower_bounds(self) -> None:
        """Recalculate lower rate bounds to maintain contiguous risk tier boundaries."""
        for i, segment in enumerate(self.segments):
            if i == 0:
                segment.lower_rate = 0.0
                continue

            prev_segment = self.segments[i - 1]
            if segment.upper_rate == prev_segment.upper_rate:
                segment.lower_rate = prev_segment.lower_rate
            elif prev_segment.upper_rate is not None:
                segment.lower_rate = prev_segment.upper_rate
            else:
                segment.lower_rate = 0.0

    def get_duplicate_names(self) -> list[str]:
        """Return list of duplicate segment names if any exist."""
        seen: set[str] = set()
        duplicates: set[str] = set()
        for seg in self.segments:
            if seg.name in seen:
                duplicates.add(seg.name)
            seen.add(seg.name)
        return sorted(duplicates)

    def to_polars_expr(self, loss_rate_col: str) -> pl.Expr:
        """Build Polars expression mapping loss_rate_col values to risk segment names.

        Args:
            loss_rate_col: Column name containing numerical loss rates.

        Returns:
            A Polars expression resulting in segment names.
        """
        expr: pl.Expr | None = None
        col_expr = pl.col(loss_rate_col)

        for seg in self.segments:
            if seg.upper_rate is None:
                cond = col_expr >= seg.lower_rate
            else:
                cond = (col_expr >= seg.lower_rate) & (col_expr < seg.upper_rate)

            if expr is None:
                expr = pl.when(cond).then(pl.lit(seg.name))
            else:
                expr = expr.when(cond).then(pl.lit(seg.name))

        if expr is None:
            return pl.lit(None)

        return expr.otherwise(None)


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
        max_iteration_depth: Maximum tree depth for multi-variable iterations.
        max_categorical_unique: Maximum distinct unique values allowed for categorical splits.
    """

    max_iteration_depth: int = 10
    max_categorical_unique: int = 20


__all__ = [
    "is_valid_hex_color",
    "RiskSegment",
    "RiskSegmentConfig",
    "LossRateScalar",
    "OptionsConfig",
    "get_default_risk_segments",
]
