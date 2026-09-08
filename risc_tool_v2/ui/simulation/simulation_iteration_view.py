"""Iteration view page: non-editable per-band metric table for one iteration.

An iteration reuses its simulation output's banding verbatim. Sidebar controls
(metrics, filters, scalars, remove-outliers) mutate the iteration's view
metadata through the SimulationViewModel; the body always shows the inherited
dev bad rate column plus the selected metrics.
"""

import math

import pandas as pd
import streamlit as st

from risc_tool_v2.data.metric.models.metric import Metric
from risc_tool_v2.data.simulation.models.iteration import SimulationIteration
from risc_tool_v2.data.simulation.models.risk_segment import RiskSegment
from risc_tool_v2.data.simulation.models.simulation_config import (
    SimulationConfigGenerator,
)
from risc_tool_v2.data.simulation.services.iterate import BandTableResult
from risc_tool_v2.ui.core.session import get_session
from risc_tool_v2.ui.simulation.simulation_vm import SimulationViewModel
from risc_tool_v2.ui.simulation.widgets import filter_selector, metric_selector

_SEGMENT = "Risk Segment"
_EMPTY = "—"


def _row_style(
    styled: pd.io.formats.style.Styler, row_index: int, seg: RiskSegment
) -> pd.io.formats.style.Styler:
    return styled.set_properties(
        subset=slice(row_index, row_index),
        **{
            "color": str(seg.font_color),
            "background-color": str(seg.bg_color),
        },
    )


def _sidebar(
    simulation_vm: SimulationViewModel, iteration: SimulationIteration
) -> None:
    st.sidebar.button(
        label="Back to Graph",
        icon=":material/arrow_back:",
        width="stretch",
        type="secondary",
        on_click=lambda: simulation_vm.set_mode("graph"),
    )

    st.sidebar.button(
        label="View Simulation",
        icon=":material/account_tree:",
        width="stretch",
        type="secondary",
        on_click=lambda: simulation_vm.set_mode("view", iteration.simulation_id),
    )

    st.sidebar.divider()
    st.sidebar.markdown(f"**Selected: Iteration #{iteration.uid}**")

    metadata = simulation_vm.iteration_metadata(iteration.uid)

    metric_ids = metric_selector(metadata.metric_ids, key="iteration_metrics")
    filter_ids = filter_selector(metadata.filter_ids)
    scalars_enabled = st.sidebar.checkbox(
        "Use Scalars",
        value=metadata.scalars_enabled,
        key="iteration_scalars",
    )
    remove_outliers = st.sidebar.checkbox(
        "Remove Outliers",
        value=metadata.remove_outliers,
        key="iteration_outliers",
    )

    simulation_vm.update_iteration_metadata(
        iteration.uid,
        metric_ids=metric_ids,
        filter_ids=filter_ids,
        scalars_enabled=scalars_enabled,
        remove_outliers=remove_outliers,
    )

    st.sidebar.divider()
    if st.sidebar.button(
        label="Delete Iteration",
        icon=":material/delete:",
        width="stretch",
        type="secondary",
    ):
        simulation_vm.remove_iteration(iteration.uid)
        st.rerun()


def _format_value(metric: Metric, value: float | None) -> str:
    """Format an aggregated value following the metric editor's conventions
    (percentages are shown multiplied by 100)."""
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return _EMPTY
    formatter = (
        f"{{:{',' if metric.use_thousand_sep else ''}.{metric.decimal_places}f}}"
        f"{'%' if metric.is_percentage else ''}"
    )
    return formatter.format(value * 100 if metric.is_percentage else value)


def _band_table(scg: SimulationConfigGenerator, result: BandTableResult) -> None:
    if result.errors:
        for error in result.errors:
            st.error(error, icon=":material/error:")
        return

    columns = [name for name, _ in result.columns]
    rows: list[dict[str, str]] = []
    row_segments: list[RiskSegment] = []
    for seg_id, seg in result.segments.items():
        row_segments.append(seg)
        values = result.values.get(seg_id, {})
        row: dict[str, str] = {_SEGMENT: seg.name}
        for column_name, metric in result.columns:
            row[column_name] = _format_value(metric, values.get(column_name))
        rows.append(row)

    df = pd.DataFrame(rows, columns=[_SEGMENT, *columns])
    styled = df.style
    for index, seg in enumerate(row_segments):
        styled = _row_style(styled, index, seg)
    st.dataframe(styled, width="stretch", hide_index=True)

    if not result.warnings:
        st.caption("Values are recomputed against the current data and filters.")
    else:
        for warning in result.warnings:
            st.caption(f"⚠ {warning}")


def simulation_iteration_view() -> None:
    """Render the iteration page for the currently selected iteration."""
    session = get_session()
    simulation_vm = session.simulation_view_model

    iteration = simulation_vm.current_iteration
    if iteration is None:
        simulation_vm.set_mode("graph")
        st.rerun()
        return

    _sidebar(simulation_vm, iteration)

    scg = simulation_vm.scg_for(simulation_vm.simulations[iteration.simulation_id])

    st.title(f"Iteration #{iteration.uid}")
    st.badge(
        "Single-Variable Iteration",
        icon=":material/timeline:",
        color="violet",
    )
    st.caption(
        f"**{scg.name}** · derived from Simulation "
        f"**#{iteration.simulation_id}** · variable **{iteration.variable_name}**"
    )

    st.divider()

    result = simulation_vm.get_iteration_table(iteration.uid)
    _band_table(scg, result)


__all__ = ["simulation_iteration_view"]
