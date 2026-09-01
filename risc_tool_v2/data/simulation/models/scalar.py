"""Scalar rate models for annualization and risk scalar factor computation."""

import json
from uuid import NAMESPACE_URL, uuid5

import polars as pl
from pydantic import BaseModel, ConfigDict, Field

from risc_tool_v2.data.core.enums import LossRateTypes
from risc_tool_v2.data.simulation.json.simulation_json import (
    LossRateScalarJSON,
    ScalarConfigJSON,
)


class LossRateScalar(BaseModel, frozen=True):
    """Scalar rates for annualization and risk scalar factor computation.

    Attributes:
        loss_rate_type: Type of loss rate ($ Bad Rate or # Bad Rate).
        current_rate: Current MOB loss rate as a decimal (or None if unconfigured).
        lifetime_rate: Lifetime MOB loss rate as a decimal (or None if unconfigured).
    """

    model_config = ConfigDict(extra="forbid")

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

    def create_hash(self) -> str:
        """Return a content hash string for this scalar's rate fields.

        Returns:
            A UUIDv5 hash string derived from the loss rate type and rates.
        """
        payload = json.dumps(
            {
                "loss_rate_type": self.loss_rate_type.value,
                "current_rate": self.current_rate,
                "lifetime_rate": self.lifetime_rate,
            },
            sort_keys=True,
            default=str,
        )
        return str(uuid5(NAMESPACE_URL, payload))

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

    def to_dict(self) -> LossRateScalarJSON:
        return LossRateScalarJSON(
            loss_rate_type=self.loss_rate_type,
            current_rate=self.current_rate,
            lifetime_rate=self.lifetime_rate,
        )

    @classmethod
    def from_dict(cls, data: LossRateScalarJSON) -> "LossRateScalar":
        return cls(
            loss_rate_type=data.loss_rate_type,
            current_rate=data.current_rate,
            lifetime_rate=data.lifetime_rate,
        )


class ScalarConfig(BaseModel, frozen=True):
    """Configuration for both ULR and DLR scalar rates."""

    model_config = ConfigDict(extra="forbid")

    ulr_scalar: LossRateScalar = Field(
        default_factory=lambda: LossRateScalar(loss_rate_type=LossRateTypes.ULR)
    )
    dlr_scalar: LossRateScalar = Field(
        default_factory=lambda: LossRateScalar(loss_rate_type=LossRateTypes.DLR)
    )

    def get_scalar(self, loss_rate_type: LossRateTypes) -> LossRateScalar:
        if loss_rate_type == LossRateTypes.DLR:
            return self.dlr_scalar
        elif loss_rate_type == LossRateTypes.ULR:
            return self.ulr_scalar
        else:
            raise ValueError(f"Unsupported loss rate type: {loss_rate_type}")

    def create_hash(self) -> str:
        """Return a content hash string for both ULR and DLR scalar rates.

        Returns:
            A UUIDv5 hash string derived from the two LossRateScalar hashes.
        """
        payload = json.dumps(
            {
                "ulr_scalar": self.ulr_scalar.create_hash(),
                "dlr_scalar": self.dlr_scalar.create_hash(),
            },
            sort_keys=True,
        )
        return str(uuid5(NAMESPACE_URL, payload))

    def to_dict(self) -> ScalarConfigJSON:
        return ScalarConfigJSON(
            ulr_scalar=self.ulr_scalar.to_dict(),
            dlr_scalar=self.dlr_scalar.to_dict(),
        )

    @classmethod
    def from_dict(cls, data: ScalarConfigJSON) -> "ScalarConfig":
        return cls(
            ulr_scalar=LossRateScalar.from_dict(data.ulr_scalar),
            dlr_scalar=LossRateScalar.from_dict(data.dlr_scalar),
        )


__all__ = [
    "LossRateScalar",
    "ScalarConfig",
]
