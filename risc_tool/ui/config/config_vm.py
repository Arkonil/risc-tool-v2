"""View model for the Configuration UI page."""

import typing as t
from collections import OrderedDict

import numpy as np
import pandas as pd
from pandas.io.formats.style import Styler

from risc_tool.data.models.changes import ChangeTracker
from risc_tool.data.models.config import LossRateScalar
from risc_tool.data.models.enums import (
    LossRateTypes,
    RSDetCol,
    ScalarTableColumn,
    Signature,
)
from risc_tool.data.models.types import ChangeIDs, RiskSegmentID
from risc_tool.data.repositories.metric import MetricRepository
from risc_tool.data.repositories.options import OptionRepository
from risc_tool.data.repositories.scalar import ScalarRepository
from risc_tool.utils.logging import get_logger

logger = get_logger(__name__)


def _coerce_to_float(value: object) -> float:
    """Convert data editor scalar values to a plain Python float."""
    if value is None:
        raise ValueError("Cannot convert None to float")

    if isinstance(value, bool):
        return float(int(value))

    if isinstance(value, np.bool_):
        return float(int(t.cast(bool, value)))

    if isinstance(value, (int, float, np.integer, np.floating)):
        numeric_value = t.cast(float | int, value)
        return float(numeric_value)

    if isinstance(value, str):
        text = value.strip()
        if not text:
            raise ValueError("Cannot convert empty string to float")
        return float(text)

    if hasattr(value, "__float__"):
        return float(t.cast(t.Any, value))

    raise TypeError(f"Cannot convert {type(value).__name__} to float")


class ConfigViewModel(ChangeTracker):
    """View model coordinating risk segment configuration and scalar calculations."""

    @property
    def signature(self) -> Signature:
        return Signature.CONFIG_VIEW_MODEL

    def __init__(
        self,
        option_repository: OptionRepository,
        scalar_repository: ScalarRepository,
        metric_repository: MetricRepository,
    ) -> None:
        super().__init__(
            dependencies=[option_repository, scalar_repository, metric_repository]
        )
        self._option_repository = option_repository
        self._scalar_repository = scalar_repository
        self._metric_repository = metric_repository

    def on_dependency_update(self, change_ids: ChangeIDs) -> None:
        """Handle updates from repositories (no-op as UI queries fresh properties)."""

    # Risk Segment Details
    @property
    def segments(self):
        return self._option_repository.segments

    @property
    def risk_segment_details_styler(self) -> Styler:
        """Generate preconfigured pandas Styler for risk segment details table."""
        return self._option_repository.risk_segments.to_pandas_styler()

    def validate_risk_segments(self, edited_df: pd.DataFrame) -> list[str]:
        """Validate risk segment names and upper bad rate monotonicity in edited DataFrame.

        Returns:
            List of error messages if validation fails.
        """
        errors: list[str] = []
        names: list[str] = (
            edited_df[RSDetCol.RISK_SEGMENT].astype(str).str.strip().tolist()
        )

        if any(name == "" for name in names):
            errors.append("Risk Segment Names cannot be empty.")

        seen: set[str] = set()
        duplicates: set[str] = set()
        for name in names:
            if name in seen:
                duplicates.add(name)
            seen.add(name)

        if duplicates:
            errors.append(
                f"Risk Segment Names must be unique. Repeated: {sorted(duplicates)}"
            )

        # Monotonicity validation for Upper Bad Rate
        def get_upper_rate_val(val: t.Any) -> float:
            if pd.isna(val) or val is None:
                return float("inf")
            try:
                return float(val)
            except (ValueError, TypeError):
                return float("inf")

        rates = [
            get_upper_rate_val(edited_df.at[idx, RSDetCol.UPPER_RATE])
            for idx in range(len(edited_df))
        ]

        for idx in range(1, len(edited_df)):
            prev_rate = rates[idx - 1]
            curr_rate = rates[idx]
            if curr_rate < prev_rate:
                prev_name = str(edited_df.at[idx - 1, RSDetCol.RISK_SEGMENT]).strip()
                curr_name = str(edited_df.at[idx, RSDetCol.RISK_SEGMENT]).strip()

                prev_str = "None" if prev_rate == float("inf") else f"{prev_rate:.2f}%"
                curr_str = "None" if curr_rate == float("inf") else f"{curr_rate:.2f}%"

                errors.append(
                    f"Upper Bad Rate of segment '{curr_name}' ({curr_str}) "
                    f"cannot be lower than that of segment '{prev_name}' ({prev_str})."
                )

        return errors

    def process_risk_segment_edits(self, edited_df: pd.DataFrame) -> bool:
        """Process edits from Streamlit data editor and update OptionRepository.

        Args:
            edited_df: Edited DataFrame returned by st.data_editor.

        Returns:
            True if state was changed, requiring a rerun.
        """
        needs_rerun = False
        for idx in range(len(edited_df)):
            if idx >= len(self.segments):
                break

            orig_seg = self.segments.get(RiskSegmentID(idx))
            if orig_seg is None:
                continue

            new_name = str(edited_df.at[idx, RSDetCol.RISK_SEGMENT]).strip()
            if new_name != orig_seg.name:
                self.set_risk_seg_name(RiskSegmentID(idx), new_name)
                needs_rerun = True

            new_upper_val = edited_df.at[idx, RSDetCol.UPPER_RATE]
            if pd.isna(new_upper_val):
                new_upper = float("inf")
            else:
                new_upper = _coerce_to_float(new_upper_val) / 100.0

            if new_upper != orig_seg.upper_rate:
                self.set_risk_seg_upper_rate(RiskSegmentID(idx), new_upper)
                needs_rerun = True

        return needs_rerun

    def add_risk_seg_row(self) -> None:
        self._option_repository.add_risk_seg_row()

    def delete_selected_risk_seg_rows(self, segment_ids: list[RiskSegmentID]) -> None:
        self._option_repository.delete_selected_risk_seg_rows(segment_ids)

    def set_risk_seg_font_color(
        self, segment_ids: list[RiskSegmentID], color: str
    ) -> None:
        self._option_repository.set_risk_seg_font_color(segment_ids, color)

    def set_risk_seg_bg_color(
        self, segment_ids: list[RiskSegmentID], color: str
    ) -> None:
        self._option_repository.set_risk_seg_bg_color(segment_ids, color)

    def set_risk_seg_default_values(self) -> None:
        self._option_repository.reset_risk_seg_defaults()

    def set_risk_seg_name(self, segment_id: RiskSegmentID, name: str) -> None:
        self._option_repository.set_risk_seg_name(segment_id, name)

    def set_risk_seg_upper_rate(
        self, segment_id: RiskSegmentID, upper_rate: float
    ) -> None:
        self._option_repository.set_risk_seg_upper_rate(segment_id, upper_rate)

    def set_risk_seg_maf(
        self, segment_id: RiskSegmentID, maf: float, loss_rate_type: LossRateTypes
    ) -> None:
        self._option_repository.set_risk_seg_maf(segment_id, maf, loss_rate_type)

    def get_color(self, segment_id: RiskSegmentID) -> tuple[str, str]:
        return self._option_repository.get_color(segment_id)

    # Scalars & MOB
    @property
    def current_rate_mob(self) -> int:
        return self._metric_repository.current_rate_mob

    @property
    def lifetime_rate_mob(self) -> int:
        return self._metric_repository.lifetime_rate_mob

    def get_scalar(self, loss_rate_type: LossRateTypes) -> LossRateScalar:
        return self._scalar_repository.get_scalar(loss_rate_type)

    def get_current_rate(self, loss_rate_type: LossRateTypes) -> float | None:
        return self.get_scalar(loss_rate_type).current_rate

    def get_lifetime_rate(self, loss_rate_type: LossRateTypes) -> float | None:
        return self.get_scalar(loss_rate_type).lifetime_rate

    def set_current_rate(
        self, loss_rate_type: LossRateTypes, rate: float | None
    ) -> None:
        self._scalar_repository.set_current_rate(loss_rate_type, rate)

    def set_lifetime_rate(
        self, loss_rate_type: LossRateTypes, rate: float | None
    ) -> None:
        self._scalar_repository.set_lifetime_rate(loss_rate_type, rate)

    # Annualization Factor Table
    def get_annualization_df(self, loss_rate_type: LossRateTypes) -> pd.DataFrame:
        """Generate DataFrame for annualization rate editing."""
        curr_rate = self.get_current_rate(loss_rate_type)
        life_rate = self.get_lifetime_rate(loss_rate_type)
        return pd.DataFrame({
            "Loss Rate Description": ["Current Rate", "Lifetime Rate"],
            "MOB": [
                f"{self.current_rate_mob} MOB",
                f"{self.lifetime_rate_mob} MOB",
            ],
            "Loss Rates": [
                (curr_rate * 100.0) if curr_rate is not None else 0.0,
                (life_rate * 100.0) if life_rate is not None else 0.0,
            ],
        })

    def process_annualization_edits(
        self, loss_rate_type: LossRateTypes, edited_df: pd.DataFrame
    ) -> bool:
        """Process edits on annualization rate DataFrame and update ScalarRepository."""
        needs_rerun = False
        new_curr = _coerce_to_float(edited_df.at[0, "Loss Rates"]) / 100.0
        new_life = _coerce_to_float(edited_df.at[1, "Loss Rates"]) / 100.0

        if new_curr != self.get_current_rate(loss_rate_type):
            self.set_current_rate(loss_rate_type, new_curr)
            needs_rerun = True

        if new_life != self.get_lifetime_rate(loss_rate_type):
            self.set_lifetime_rate(loss_rate_type, new_life)
            needs_rerun = True

        return needs_rerun

    # Risk Scalar Factor Table
    def get_risk_scalar_factor_styler(self, loss_rate_type: LossRateTypes) -> Styler:
        """Generate preconfigured pandas Styler for Risk Scalar Factor table."""
        scalar = self.get_scalar(loss_rate_type)

        records: OrderedDict[RiskSegmentID, dict[ScalarTableColumn, t.Any]] = (
            OrderedDict()
        )

        for seg_id, seg in self.segments.items():
            maf = seg.maf_dlr if loss_rate_type == LossRateTypes.DLR else seg.maf_ulr
            rsf = max(maf * scalar.portfolio_scalar, 1.0)
            records[seg_id] = {
                ScalarTableColumn.RISK_SEGMENT: seg.name,
                ScalarTableColumn.MAF: maf * 100.0,
                ScalarTableColumn.RISK_SCALAR_FACTOR: rsf,
            }

        df = pd.DataFrame.from_dict(records, orient="index")
        styler = df.style

        for row_idx in df.index:
            font_color, bg_color = self.get_color(RiskSegmentID(row_idx))
            styler = styler.set_properties(
                subset=(
                    slice(row_idx, row_idx),
                    slice(
                        ScalarTableColumn.RISK_SEGMENT,
                        ScalarTableColumn.RISK_SEGMENT,
                    ),
                ),
                **{
                    "color": str(font_color),
                    "background-color": str(bg_color),
                },
            )

        return styler

    def process_maf_edits(
        self, loss_rate_type: LossRateTypes, edited_df: pd.DataFrame
    ) -> bool:
        """Process edits on MAF values and update OptionRepository."""
        needs_rerun = False
        for idx in range(len(edited_df)):
            if idx >= len(self.segments):
                break

            orig_seg = self.segments.get(RiskSegmentID(idx))
            if orig_seg is None:
                continue

            curr_maf = (
                orig_seg.maf_dlr
                if loss_rate_type == LossRateTypes.DLR
                else orig_seg.maf_ulr
            )
            new_maf = _coerce_to_float(edited_df.at[idx, ScalarTableColumn.MAF]) / 100.0

            if abs(new_maf - curr_maf) > 1e-6:
                self.set_risk_seg_maf(RiskSegmentID(idx), new_maf, loss_rate_type)
                needs_rerun = True

        return needs_rerun


__all__ = ["ConfigViewModel"]
