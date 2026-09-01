"""Scalar editor for current/lifetime bad rates and per-segment MAF."""

import typing as t

import pandas as pd
import streamlit as st

from risc_tool_v2.data.core.enums import LossRateTypes
from risc_tool_v2.data.simulation.models.risk_segment import RiskSegmentConfig
from risc_tool_v2.data.simulation.models.scalar import (
    LossRateScalar,
    ScalarConfig,
)


def _numeric_input(
    label: str,
    key: str,
    value: float | None,
    help_text: str,
) -> float | None:
    if value is None:
        return (
            st.number_input(
                label=label,
                value=0.0,
                min_value=0.0,
                max_value=100.0,
                step=0.01,
                format="%.2f",
                label_visibility="collapsed",
                key=key,
                help=help_text,
            )
            or None
        )
    return st.number_input(
        label=label,
        value=value,
        min_value=0.0,
        max_value=100.0,
        step=0.01,
        format="%.2f",
        label_visibility="collapsed",
        key=key,
        help=help_text,
    )


def _rate_inputs_section(
    scalar: LossRateScalar,
    prefix: str,
) -> LossRateScalar:
    symbol = "$" if scalar.loss_rate_type == LossRateTypes.DLR else "#"
    st.markdown(f"#### {symbol} Bad Rate")

    current = _numeric_input(
        "Current Rate (%)",
        f"sim_{prefix}_current_rate",
        scalar.current_rate,
        "Current MOB bad rate used for scalar computation.",
    )
    lifetime = _numeric_input(
        "Lifetime Rate (%)",
        f"sim_{prefix}_lifetime_rate",
        scalar.lifetime_rate,
        "Lifetime MOB bad rate used for scalar computation.",
    )

    return LossRateScalar(
        loss_rate_type=scalar.loss_rate_type,
        current_rate=current,
        lifetime_rate=lifetime,
    )


def _maf_df(config: RiskSegmentConfig) -> pd.DataFrame:
    rows: list[dict[str, t.Any]] = []
    for seg in config.segments.values():
        rows.append({
            "Risk Segment": seg.name,
            "MAF #": seg.maf_ulr * 100.0,
            "MAF $": seg.maf_dlr * 100.0,
        })
    return pd.DataFrame(rows)


def _process_maf_edits(
    config: RiskSegmentConfig,
    edited_df: pd.DataFrame,
) -> RiskSegmentConfig:
    updated = config
    for i, seg in enumerate(config.segments.values()):
        if i >= len(edited_df):
            break
        df_row: t.Any = edited_df.iloc[i]
        try:
            new_ulr = float(df_row.get("MAF #", seg.maf_ulr * 100.0)) / 100.0
            new_dlr = float(df_row.get("MAF $", seg.maf_dlr * 100.0)) / 100.0
        except (ValueError, TypeError):
            continue
        seg_updates: dict[str, float] = {}
        if abs(new_ulr - seg.maf_ulr) > 1e-6:
            seg_updates["maf_ulr"] = new_ulr
        if abs(new_dlr - seg.maf_dlr) > 1e-6:
            seg_updates["maf_dlr"] = new_dlr
        if seg_updates:
            updated = updated.with_updates(seg.uid, **seg_updates)
    return updated


def _maf_editor(config: RiskSegmentConfig) -> RiskSegmentConfig:
    st.markdown("##### Maturity Adjustment Factor")
    edited_df = st.data_editor(
        _maf_df(config),
        column_config={
            "Risk Segment": st.column_config.TextColumn(
                label="Risk Segment", disabled=True
            ),
            "MAF #": st.column_config.NumberColumn(
                label="MAF # (%)", format="%.1f", min_value=0.0
            ),
            "MAF $": st.column_config.NumberColumn(
                label="MAF $ (%)", format="%.1f", min_value=0.0
            ),
        },
        hide_index=True,
        width="stretch",
        key="sim_maf_editor",
    )
    return _process_maf_edits(config, edited_df)


def scalar_editor(
    scalar_config: ScalarConfig,
    risk_segment_config: RiskSegmentConfig,
) -> tuple[ScalarConfig, RiskSegmentConfig]:
    """Render scalar inputs and per-segment MAF; return updated configs."""
    st.subheader("Scalars")

    ulr_col, dlr_col = st.columns(2)

    with ulr_col:
        ulr = _rate_inputs_section(scalar_config.ulr_scalar, "ulr")

    with dlr_col:
        dlr = _rate_inputs_section(scalar_config.dlr_scalar, "dlr")

    updated_rs = _maf_editor(risk_segment_config)

    st.info(
        ":blue-badge[`Portfolio Scalar`] = "
        ":blue-badge[`Lifetime Rate / Current Rate`] "
        "(defaults to 1.0 when either rate is unset).",
        icon=":material/info:",
    )

    return ScalarConfig(ulr_scalar=ulr, dlr_scalar=dlr), updated_rs


__all__ = ["scalar_editor"]
