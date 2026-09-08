"""Simulation view page: read-only details, results and run/edit/delete actions.

The page renders one Simulation's configuration and (if produced) its
SimulationOutputs as band-definition tables. Sidebar actions mutate state
through the SimulationViewModel only; nothing here reads repositories
directly.
"""

import math
import typing as t

import pandas as pd
import streamlit as st

from risc_tool_v2.data.core.uid import DataSourceID, RiskSegmentID
from risc_tool_v2.data.simulation.models.groups import NumericalGroup
from risc_tool_v2.data.simulation.models.risk_segment import RiskSegment
from risc_tool_v2.data.simulation.models.simulation import Simulation, SimulationStatus
from risc_tool_v2.data.simulation.models.simulation_config import (
    BadRateConfig,
    SimulationConfigGenerator,
    SimulationOutput,
)
from risc_tool_v2.ui.core.session import get_session
from risc_tool_v2.ui.simulation.simulation_vm import SimulationViewModel

_EMPTY = "—"
_MAF_FORMAT = "{:.2f}"
_BOUND_FORMAT = "{:.4f}"

_SEGMENT = "Risk Segment"
_LOWER = "Lower Bound"
_UPPER = "Upper Bound"
_CATEGORIES = "Categories"
_MAF_DLR = "MAF (DLR)"
_MAF_ULR = "MAF (ULR)"

_BadgeColor = t.Literal[
    "red", "orange", "yellow", "blue", "green", "violet", "gray", "grey", "primary"
]

_STATUS_COLORS: dict[SimulationStatus, _BadgeColor] = {
    SimulationStatus.PENDING: "gray",
    SimulationStatus.RUNNING: "blue",
    SimulationStatus.COMPLETED: "green",
    SimulationStatus.FAILED: "red",
}


def _fmt(value: float | None) -> str:
    if value is None:
        return _EMPTY
    if math.isinf(value):
        return "∞"
    return _BOUND_FORMAT.format(value)


def _fmt_maf(value: float) -> str:
    return _MAF_FORMAT.format(value)


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


def _sidebar(simulation_vm: SimulationViewModel, sim: Simulation) -> None:
    st.sidebar.button(
        label="Back to Graph",
        icon=":material/arrow_back:",
        width="stretch",
        type="secondary",
        on_click=lambda: simulation_vm.set_mode("graph"),
    )

    st.sidebar.divider()
    st.sidebar.markdown(f"**Selected: Simulation #{sim.uid}**")

    def _run() -> None:
        simulation_vm.run_simulation(sim.uid)

    st.sidebar.button(
        label="Run Simulation",
        icon=":material/play_arrow:",
        width="stretch",
        type="primary",
        on_click=_run,
    )

    st.sidebar.button(
        label="Edit Simulation",
        icon=":material/edit:",
        width="stretch",
        type="secondary",
        on_click=lambda: simulation_vm.begin_edit_draft(sim.uid),
    )

    if st.sidebar.button(
        label="Delete Simulation",
        icon=":material/delete:",
        width="stretch",
        type="secondary",
    ):
        simulation_vm.remove_simulation(sim.uid)
        st.rerun()


def _metrics(scg: SimulationConfigGenerator) -> None:
    n_segments = len(scg.risk_segment_config.segments)
    values = {
        "Variable": scg.variable_name or _EMPTY,
        "Type": scg.variable_type.value,
        "Bad Rate": scg.bad_rate_type.value,
        "Segments": str(n_segments),
        "Filters": str(len(scg.filter_ids)),
    }
    columns = st.columns(len(values))
    for column, (label, value) in zip(columns, values.items()):
        column.metric(label, value)


def _output_table(
    so: SimulationOutput, segments: dict[RiskSegmentID, RiskSegment]
) -> None:
    st.caption(f"Output · variable **{so.variable_name}**")

    if not so.groups:
        st.caption("No groups produced for this output.")
        return

    rows: list[dict[str, str]] = []
    row_segments: list[RiskSegment | None] = []
    for seg_id, group in so.groups.items():
        seg = segments.get(seg_id)
        row_segments.append(seg)
        if isinstance(group, NumericalGroup):
            lower, upper = _fmt(group.lower_bound), _fmt(group.upper_bound)
            categories = _EMPTY
        else:
            lower, upper = _EMPTY, _EMPTY
            categories = ", ".join(sorted(group.categories)) or _EMPTY

        rows.append({
            _SEGMENT: seg.name if seg else str(seg_id),
            _LOWER: lower,
            _UPPER: upper,
            _CATEGORIES: categories,
            _MAF_DLR: _fmt_maf(seg.maf_dlr) if seg else _EMPTY,
            _MAF_ULR: _fmt_maf(seg.maf_ulr) if seg else _EMPTY,
        })

    df = pd.DataFrame(
        rows, columns=[_SEGMENT, _LOWER, _UPPER, _CATEGORIES, _MAF_DLR, _MAF_ULR]
    )
    styled = df.style
    for index, seg in enumerate(row_segments):
        if seg is not None:
            styled = _row_style(styled, index, seg)
    st.dataframe(styled, width="stretch", hide_index=True)

    if not so.is_valid:
        st.warning("Output is flagged invalid.", icon=":material/warning:")
    for warning in so.validation_warnings:
        st.caption(f"⚠ {warning}")


def _results(
    simulation_vm: SimulationViewModel, scg: SimulationConfigGenerator, sim: Simulation
) -> None:
    st.subheader("Results")
    outputs = simulation_vm.get_simulation_outputs(sim.uid)

    if not outputs:
        if sim.status == SimulationStatus.FAILED:
            st.error(sim.error_message or "Simulation failed.", icon=":material/error:")
        elif sim.status == SimulationStatus.PENDING:
            st.info(
                "This simulation has not been run yet. Use **Run Simulation** "
                "in the sidebar to produce output.",
                icon=":material/science:",
            )
        else:
            st.info("No output available.", icon=":material/science:")
        return

    st.caption(f"{len(outputs)} output(s) generated.")
    segments = scg.risk_segment_config.segments
    for so in outputs:
        _output_table(so, segments)
        _iteration_actions(simulation_vm, sim, so)


def _iteration_actions(
    simulation_vm: SimulationViewModel, sim: Simulation, so: SimulationOutput
) -> None:
    """Offer a New/Open Iteration control for one simulation output."""
    existing = next(
        (
            iteration
            for iteration in simulation_vm.iterations_for_sim(sim.uid)
            if iteration.so_id == so.uid
        ),
        None,
    )
    if existing is not None:
        if st.button(
            label=f"Open Iteration #{existing.uid}",
            icon=":material/timeline:",
            key=f"open_iteration_{so.uid}",
        ):
            simulation_vm.open_iteration(existing.uid)
            st.rerun()
    else:
        if st.button(
            label="New Iteration",
            icon=":material/add_chart:",
            key=f"new_iteration_{so.uid}",
        ):
            simulation_vm.open_iteration_from_output(sim.uid, so.uid)
            st.rerun()


def _risk_segments(scg: SimulationConfigGenerator) -> None:
    config = scg.risk_segment_config
    segments = config.get_segments(list(config.segments.keys()), normalize=False)
    rows: list[dict[str, str]] = []
    for seg in segments.values():
        upper = "∞" if math.isinf(seg.upper_rate) else f"{seg.upper_rate * 100:.2f} %"
        rows.append({
            _SEGMENT: seg.name,
            "Upper Rate (%)": upper,
            _MAF_DLR: _fmt_maf(seg.maf_dlr),
            _MAF_ULR: _fmt_maf(seg.maf_ulr),
            "Use in Simulation": "Yes" if seg.selected else "No",
        })

    if not rows:
        st.caption("No risk segments configured.")
        return

    df = pd.DataFrame(
        rows,
        columns=[_SEGMENT, "Upper Rate (%)", _MAF_DLR, _MAF_ULR, "Use in Simulation"],
    )
    styled = df.style
    for index, seg in enumerate(segments.values()):
        styled = _row_style(styled, index, seg)
    st.dataframe(styled, width="stretch", hide_index=True)


def _bad_rate_row(
    label: str, br: BadRateConfig | None, ds_labels: dict[DataSourceID, str]
) -> dict[str, str]:
    if br is None:
        return {
            "Group": label,
            "Data Sources": _EMPTY,
            "Numerator": _EMPTY,
            "Denominator": _EMPTY,
            "MOB": _EMPTY,
            "Annualized": _EMPTY,
        }
    sources = (
        ", ".join(ds_labels.get(dsid, str(dsid)) for dsid in br.data_source_ids)
        or _EMPTY
    )
    return {
        "Group": label,
        "Data Sources": sources,
        "Numerator": br.numerator_col or _EMPTY,
        "Denominator": br.denominator_col or _EMPTY,
        "MOB": str(br.current_rate_mob),
        "Annualized": "Yes" if br.is_annualized else "No",
    }


def _bad_rates(
    simulation_vm: SimulationViewModel, scg: SimulationConfigGenerator
) -> None:
    ds_labels = simulation_vm.data_source_labels
    rows = [
        _bad_rate_row("Dev · Unit", scg.dev_unit_bad_rate, ds_labels),
        _bad_rate_row("Dev · Dollar", scg.dev_dollar_bad_rate, ds_labels),
        _bad_rate_row("Test · Unit", scg.test_unit_bad_rate, ds_labels),
        _bad_rate_row("Test · Dollar", scg.test_dollar_bad_rate, ds_labels),
    ]
    df = pd.DataFrame(
        rows,
        columns=[
            "Group",
            "Data Sources",
            "Numerator",
            "Denominator",
            "MOB",
            "Annualized",
        ],
    )
    st.dataframe(df, width="stretch", hide_index=True)


def _scalars(scg: SimulationConfigGenerator) -> None:
    scalar_config = scg.scalar_config
    rows: list[dict[str, str]] = []
    for scalar in (scalar_config.ulr_scalar, scalar_config.dlr_scalar):
        rows.append({
            "Rate Type": scalar.loss_rate_type.value,
            "Current Rate": _fmt(scalar.current_rate),
            "Lifetime Rate": _fmt(scalar.lifetime_rate),
            "Portfolio Scalar": _fmt_maf(scalar.portfolio_scalar),
        })
    df = pd.DataFrame(
        rows, columns=["Rate Type", "Current Rate", "Lifetime Rate", "Portfolio Scalar"]
    )
    st.dataframe(df, width="stretch", hide_index=True)


def _flags_and_filters(
    simulation_vm: SimulationViewModel, scg: SimulationConfigGenerator
) -> None:
    flags = {
        "Auto-Band": scg.auto_band,
        "Use Scalars": scg.use_scalars,
        "Remove Outliers": scg.remove_outliers,
    }
    st.markdown("**Flags**")
    for label, enabled in flags.items():
        icon = ":material/check_circle:" if enabled else ":material/cancel:"
        color = "green" if enabled else "grey"
        st.markdown(f"{icon} :{color}[{label}]: {'On' if enabled else 'Off'}")
    st.markdown(f"Lifetime Rate MOB: **{scg.lifetime_rate_mob}**")

    st.markdown("**Filters**")
    if not scg.filter_ids:
        st.caption("No filters applied.")
        return
    filters = simulation_vm.filters
    for filter_id in scg.filter_ids:
        flt = filters.get(filter_id)
        label = flt.name if flt is not None else str(filter_id)
        st.markdown(f"- {label}")


def _configuration(
    simulation_vm: SimulationViewModel, scg: SimulationConfigGenerator
) -> None:
    st.subheader("Configuration")
    with st.expander("Risk Segments", expanded=False):
        _risk_segments(scg)
    with st.expander("Bad Rates", expanded=False):
        _bad_rates(simulation_vm, scg)
    with st.expander("Scalars", expanded=False):
        _scalars(scg)
    with st.expander("Flags & Filters", expanded=False):
        _flags_and_filters(simulation_vm, scg)


def simulation_view() -> None:
    """Render the simulation view page for the currently selected simulation."""
    session = get_session()
    simulation_vm = session.simulation_view_model

    sim = simulation_vm.current_simulation
    if sim is None:
        simulation_vm.set_mode("graph")
        st.rerun()
        return

    _sidebar(simulation_vm, sim)

    scg = simulation_vm.scg_for(sim)

    st.title(f"Simulation #{sim.uid}")
    st.caption(f"**{scg.name}** · variable **{scg.variable_name}**")

    st.badge(
        sim.status.value,
        icon=":material/circle:",
        color=_STATUS_COLORS[sim.status],
    )

    _metrics(scg)

    st.divider()
    _results(simulation_vm, scg, sim)

    st.divider()
    _configuration(simulation_vm, scg)


__all__ = ["simulation_view"]
