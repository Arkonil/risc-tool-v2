"""Scalar Config high-level section for the Simulation Creator."""

from enum import StrEnum

import pandas as pd
import streamlit as st

from risc_tool_v2.data.core.enums import LossRateTypes
from risc_tool_v2.data.simulation.models.simulation_config import (
    SimulationConfigGenerator,
)
from risc_tool_v2.ui.simulation import widgets
from risc_tool_v2.ui.simulation.simulation_creator.base import reconcile, vm
from risc_tool_v2.ui.simulation.simulation_vm import SimulationViewModel


class ScalarColumn(StrEnum):
    """Column names of the annualization-rate data editor."""

    DESCRIPTION = "Loss Rate Description"
    MOB = "MOB"
    LOSS_RATES = "Loss Rates"


def _annualization_df(
    draft: SimulationConfigGenerator,
    loss_rate_type: LossRateTypes,
) -> pd.DataFrame:
    scalar = draft.scalar_config.get_scalar(loss_rate_type)
    dev_rate = draft.dev_unit_bad_rate or draft.dev_dollar_bad_rate
    current_mob = dev_rate.current_rate_mob if dev_rate is not None else 12
    return pd.DataFrame({
        ScalarColumn.DESCRIPTION: ["Current Rate", "Lifetime Rate"],
        ScalarColumn.MOB: [
            f"{current_mob} MOB",
            f"{draft.lifetime_rate_mob} MOB",
        ],
        ScalarColumn.LOSS_RATES: [
            scalar.current_rate * 100.0 if scalar.current_rate is not None else 0.0,
            scalar.lifetime_rate * 100.0 if scalar.lifetime_rate is not None else 0.0,
        ],
    })


def _annualization_editor(
    sim_vm: SimulationViewModel,
    draft: SimulationConfigGenerator,
    loss_rate_type: LossRateTypes,
) -> None:
    scalar = draft.scalar_config.get_scalar(loss_rate_type)

    col_edit, col_metric = st.columns([3, 1])
    with col_edit:
        edited_df = st.data_editor(
            _annualization_df(draft, loss_rate_type),
            column_config={
                ScalarColumn.DESCRIPTION: st.column_config.TextColumn(
                    label="Loss Rate Description", disabled=True
                ),
                ScalarColumn.MOB: st.column_config.TextColumn(
                    label="MOB", disabled=True
                ),
                ScalarColumn.LOSS_RATES: st.column_config.NumberColumn(
                    label=(
                        "$ Bad Rate"
                        if loss_rate_type == LossRateTypes.DLR
                        else "# Bad Rate"
                    ),
                    required=True,
                    format="%.2f %%",
                    min_value=0.0,
                    max_value=100.0,
                ),
            },
            hide_index=True,
            width="stretch",
            key=f"sim_annual_editor_{loss_rate_type.value}",
        )

        new_current = float(edited_df.iloc[0][ScalarColumn.LOSS_RATES]) / 100.0
        new_lifetime = float(edited_df.iloc[1][ScalarColumn.LOSS_RATES]) / 100.0
        reconcile(
            scalar.current_rate,
            new_current,
            lambda lrt=loss_rate_type, v=new_current: sim_vm.update_draft_scalar_rate(
                lrt, "current_rate", v
            ),
        )
        reconcile(
            scalar.lifetime_rate,
            new_lifetime,
            lambda lrt=loss_rate_type, v=new_lifetime: sim_vm.update_draft_scalar_rate(
                lrt, "lifetime_rate", v
            ),
        )

    with col_metric:
        symbol = "$" if loss_rate_type == LossRateTypes.DLR else "#"
        st.metric(
            label=f"{symbol} Portfolio Scalar",
            value=f"{scalar.portfolio_scalar:.2f}",
            border=True,
        )


def scalar_config_section(draft: SimulationConfigGenerator) -> None:
    """Scalar rates (per loss-rate type) plus per-segment MAF."""
    sim_vm = vm()
    st.subheader("Scalars")

    ulr_col, dlr_col = st.columns(2)
    with ulr_col:
        st.markdown("#### # Bad Rate")
        _annualization_editor(sim_vm, draft, LossRateTypes.ULR)
        updated_ulr_rs = widgets.risk_scalar_factor_editor(
            draft.risk_segment_config,
            LossRateTypes.ULR,
            draft.scalar_config.ulr_scalar.portfolio_scalar,
        )
        reconcile(
            draft.risk_segment_config,
            updated_ulr_rs,
            lambda: sim_vm.update_draft_risk_segments(updated_ulr_rs),
        )

    with dlr_col:
        st.markdown("#### $ Bad Rate")
        _annualization_editor(sim_vm, draft, LossRateTypes.DLR)
        updated_dlr_rs = widgets.risk_scalar_factor_editor(
            draft.risk_segment_config,
            LossRateTypes.DLR,
            draft.scalar_config.dlr_scalar.portfolio_scalar,
        )
        reconcile(
            draft.risk_segment_config,
            updated_dlr_rs,
            lambda: sim_vm.update_draft_risk_segments(updated_dlr_rs),
        )

    st.info(
        ":blue-badge[`Portfolio Scalar`] = "
        ":blue-badge[`Lifetime Rate / Current Rate`] "
        "(defaults to 1.0 when either rate is unset).",
        icon=":material/info:",
    )
    st.info(
        ":blue-badge[`Risk Scalar Factor`] is calculated as "
        ":blue-badge[`max(portfolio_scalar * maturity_adjustment_factor, 1)`], "
        "as the loss rate at :blue-badge[`n + 1`] th MOB will be more than or equal to "
        "the loss rate of :blue-badge[`n`] th MOB.",
        icon=":material/info:",
    )


__all__ = ["ScalarColumn", "scalar_config_section"]
