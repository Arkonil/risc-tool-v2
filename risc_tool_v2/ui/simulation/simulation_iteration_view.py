"""Iteration view page: per-band metric tables and double-variable grids.

An iteration reuses its simulation output's banding verbatim. Fixed iterations
are read-only; editable clones expose an editable working copy of the bands
(and, for double-variable iterations, an editable risk segment grid) layered
over the family's pinned default bands. All controls live in the sidebar
(metrics, filters, scalars, remove-outliers, and the band/group editors);
only tables are rendered in the main body, between a top-of-page breadcrumb
and the iteration header.
"""

import math
import typing as t
from collections import OrderedDict

import pandas as pd
import streamlit as st

from risc_tool_v2.data.core.enums import VariableType
from risc_tool_v2.data.core.uid import RiskSegmentID, short_id
from risc_tool_v2.data.metric.models.metric import Metric
from risc_tool_v2.data.simulation.models.groups import (
    CategoricalGroup,
    NumericalGroup,
)
from risc_tool_v2.data.simulation.models.iteration import SimulationIteration
from risc_tool_v2.data.simulation.services.iterate import MetricGridResult
from risc_tool_v2.ui.core.session import get_session
from risc_tool_v2.ui.simulation.iteration_components import (
    group_display_labels,
    iteration_navigation,
    metric_selector_button,
    previous_iteration_details_checkbox,
    rename_iteration_button,
    split_view_segmented,
)
from risc_tool_v2.ui.simulation.simulation_vm import SimulationViewModel
from risc_tool_v2.ui.simulation.widgets import filter_selector

_SEGMENT = "Risk Segment"
_BAND = "Band"
_ACTIVE = "Active"
_EMPTY = "—"
_TOTAL = "Total"
_LOWER = "Lower Bound"
_UPPER = "Upper Bound"
_CATEGORIES = "Categories"


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


def _fmt_bound(value: float | None) -> str:
    if value is None:
        return _EMPTY
    if math.isinf(value):
        return "-∞" if value < 0 else "∞"
    return f"{value:.4f}".rstrip("0").rstrip(".")


def _group_label(gid: RiskSegmentID) -> str:
    return f"Band {int(gid)}"


def _sidebar(
    simulation_vm: SimulationViewModel, iteration: SimulationIteration
) -> None:
    """Render every iteration control in the sidebar (tables-only main body)."""
    with st.sidebar:
        metadata = simulation_vm.iteration_metadata(iteration.uid)

        st.markdown(f"**Selected: Iteration #{int(iteration.uid)}**")
        rename_iteration_button(simulation_vm, iteration.uid)

        if st.button(
            label="Clone as Editable",
            icon=":material/content_copy:",
            width="stretch",
            type="secondary",
            key=f"clone_iteration_{int(iteration.uid)}",
        ):
            simulation_vm.create_editable_clone(iteration.uid)
            st.rerun()

        if not iteration.is_double_var:
            st.button(
                label="Create Double-Variable",
                icon=":material/add_chart:",
                width="stretch",
                type="primary",
                key=f"open_creator_{int(iteration.uid)}",
                on_click=lambda: simulation_vm.begin_iteration_create(iteration.uid),
            )

        st.divider()
        metric_selector_button(simulation_vm, iteration.uid)
        filter_ids = filter_selector(
            metadata.filter_ids, key=f"iteration_filters_{int(iteration.uid)}"
        )
        scalars_enabled = st.checkbox(
            "Use Scalars",
            value=metadata.scalars_enabled,
            key=f"iteration_scalars_{int(iteration.uid)}",
        )
        remove_outliers = st.checkbox(
            "Remove Outliers",
            value=metadata.remove_outliers,
            key=f"iteration_outliers_{int(iteration.uid)}",
        )
        if iteration.is_double_var:
            split_view_enabled = split_view_segmented(
                metadata.split_view_enabled,
                key=f"iteration_split_view_{int(iteration.uid)}",
            )
            show_prev = (
                simulation_vm.iteration_graph.iteration_depth(iteration.uid) == 2
            )
            show_prev_iter_details = (
                previous_iteration_details_checkbox(
                    metadata.show_prev_iter_details,
                    key=f"iteration_prev_details_{int(iteration.uid)}",
                )
                if show_prev
                else False
            )
        else:
            split_view_enabled = False
            show_prev_iter_details = False

        simulation_vm.update_iteration_metadata(
            iteration.uid,
            filter_ids=filter_ids,
            scalars_enabled=scalars_enabled,
            remove_outliers=remove_outliers,
            split_view_enabled=split_view_enabled,
            show_prev_iter_details=show_prev_iter_details,
        )

        st.divider()
        if iteration.is_editable:
            st.markdown("**Editable Bands**")
            if st.button(
                label="Add Band",
                icon=":material/add:",
                width="stretch",
                type="secondary",
                key=f"add_band_{int(iteration.uid)}",
            ):
                simulation_vm.add_new_group(iteration.uid)
                st.rerun()
            if not iteration.is_double_var:
                if st.button(
                    label="Reset Bands to Default",
                    icon=":material/restart_alt:",
                    width="stretch",
                    type="secondary",
                    key=f"reset_bands_{int(iteration.uid)}",
                ):
                    simulation_vm.set_controls(iteration.uid, iteration.default_groups)
                    st.rerun()
            else:
                if st.button(
                    label="Reset Grid to Default",
                    icon=":material/restart_alt:",
                    width="stretch",
                    type="secondary",
                    key=f"reset_grid_{int(iteration.uid)}",
                ):
                    simulation_vm.set_risk_segment_grid(
                        iteration.uid, dict(iteration.default_risk_segment_grid)
                    )
                    st.rerun()
                if st.button(
                    label="Apply Bands",
                    icon=":material/done:",
                    width="stretch",
                    type="secondary",
                    key=f"apply_active_bands_{int(iteration.uid)}",
                ):
                    default_groups = iteration.default_groups
                    base_df = st.session_state[
                        f"active_bands_{int(iteration.uid)}"
                    ]
                    mask = {
                        gid: bool(base_df.at[position, _ACTIVE])
                        for position, gid in enumerate(default_groups)
                    }
                    simulation_vm.select_groups(iteration.uid, mask=mask)
                    st.rerun()
        st.divider()

        if st.button(
            label="Delete Iteration",
            icon=":material/delete:",
            width="stretch",
            type="secondary",
            key=f"delete_iteration_{int(iteration.uid)}",
        ):
            simulation_vm.remove_iteration(iteration.uid)
            st.rerun()


def _fill_band_definition(
    row: dict[str, t.Any],
    group: NumericalGroup | CategoricalGroup | None,
    is_numerical: bool,
    *,
    editable_values: bool,
) -> None:
    """Populate a band's definition cells (bounds or categories).

    Args:
        row: The row dict to mutate.
        group: The band group or None when missing.
        is_numerical: Whether the variable is numerical.
        editable_values: When True store raw numeric bounds for a data editor;
            otherwise formatted display strings for a dataframe.
    """
    if not is_numerical:
        cat = t.cast(CategoricalGroup, group) if group is not None else None
        row[_CATEGORIES] = (
            ", ".join(sorted(cat.categories))
            if cat is not None and cat.categories
            else ""
        )
        return
    num = t.cast(NumericalGroup, group) if group is not None else None
    if editable_values:
        row[_LOWER] = (
            num.lower_bound if num is not None and not math.isinf(num.lower_bound) else None
        )
        row[_UPPER] = (
            num.upper_bound if num is not None and not math.isinf(num.upper_bound) else None
        )
    else:
        row[_LOWER] = _fmt_bound(num.lower_bound) if num is not None else _EMPTY
        row[_UPPER] = _fmt_bound(num.upper_bound) if num is not None else _EMPTY


def _combined_band_table(
    simulation_vm: SimulationViewModel,
    iteration: SimulationIteration,
    *,
    default: bool,
    editable: bool,
    key_suffix: str,
) -> None:
    """Render one combined single-var table: band controls + metrics + Total row.

    Mirrors v1's ``iteration_metric_table``: band definition columns and the
    computed metric columns share a single table with a Total row. In the
    default view every column is non-editable; only an editable iteration's
    "Editable Range" allows the band definition columns to be edited.
    """
    result = simulation_vm.get_iteration_table(
        iteration.uid, show_total_row=True, default=default
    )
    if result.errors:
        for error in result.errors:
            st.error(error, icon=":material/error:")
        return
    for warning in result.warnings:
        st.caption(f"⚠ {warning}")

    is_numerical = iteration.variable_type == VariableType.NUMERICAL
    groups = iteration.effective_groups(default=default)
    control_columns = [_LOWER, _UPPER] if is_numerical else [_CATEGORIES]
    metric_columns = [name for name, _ in result.columns]

    rows: list[dict[str, t.Any]] = []
    for seg_id, seg in result.segments.items():
        row: dict[str, t.Any] = {_SEGMENT: seg.name}
        _fill_band_definition(row, groups.get(seg_id), is_numerical, editable_values=True)
        for column_name, metric in result.columns:
            row[column_name] = _format_value(
                metric, result.values.get(seg_id, {}).get(column_name)
            )
        rows.append(row)

    total_row: dict[str, t.Any] = {_SEGMENT: _TOTAL}
    _fill_band_definition(total_row, None, is_numerical, editable_values=True)
    for column_name, metric in result.columns:
        total_row[column_name] = _format_value(metric, result.total.get(column_name))
    rows.append(total_row)

    columns = [_SEGMENT, *control_columns, *metric_columns]
    base_df = pd.DataFrame(rows, columns=columns)

    column_config: dict[str, t.Any] = {
        _SEGMENT: st.column_config.TextColumn(label=_SEGMENT, disabled=True),
    }
    if is_numerical:
        column_config[_LOWER] = st.column_config.NumberColumn(
            label=_LOWER, format="compact", disabled=not editable
        )
        column_config[_UPPER] = st.column_config.NumberColumn(
            label=_UPPER, format="compact", disabled=not editable
        )
    else:
        column_config[_CATEGORIES] = st.column_config.TextColumn(
            label=_CATEGORIES, disabled=not editable
        )
    for column_name in metric_columns:
        column_config[column_name] = st.column_config.TextColumn(
            label=column_name, disabled=True
        )

    if not editable:
        st.dataframe(base_df, width="stretch", hide_index=True)
        return

    editor_key = f"range_editor_{key_suffix}_{int(iteration.uid)}"

    def on_change() -> None:
        edited_rows: dict[int, dict[str, t.Any]] = st.session_state[editor_key].get(
            "edited_rows", {}
        )
        frame = base_df.copy()
        for row_pos, row_change in edited_rows.items():
            if row_pos >= len(groups):
                continue
            for column, change in row_change.items():
                if column in control_columns:
                    frame.at[row_pos, column] = change

        new_groups: OrderedDict[RiskSegmentID, NumericalGroup | CategoricalGroup] = (
            OrderedDict()
        )
        for i, gid in enumerate(groups):
            row = frame.iloc[i]
            if is_numerical:
                original = t.cast(NumericalGroup, groups[gid])
                lower = row[_LOWER]
                upper = row[_UPPER]
                if pd.isna(lower):
                    lower = original.lower_bound
                if pd.isna(upper):
                    upper = original.upper_bound
                new_groups[gid] = NumericalGroup(
                    lower_bound=float(lower), upper_bound=float(upper)
                )
            else:
                new_groups[gid] = CategoricalGroup(
                    categories=frozenset(_parse_categories(row[_CATEGORIES]))
                )
        simulation_vm.set_controls(iteration.uid, new_groups)

    st.data_editor(
        base_df,
        column_config=column_config,
        hide_index=True,
        num_rows="fixed",
        width="stretch",
        key=editor_key,
        on_change=on_change,
    )


def _parse_categories(text: t.Any) -> list[str]:
    if not isinstance(text, str) or not text.strip():
        return []
    separators = [",", ";"]
    cleaned_text = text
    for separator in separators:
        cleaned_text = cleaned_text.replace(separator, ",")
    return [part.strip() for part in cleaned_text.split(",") if part.strip()]


def _grid_control_table(
    simulation_vm: SimulationViewModel,
    iteration: SimulationIteration,
    result: MetricGridResult,
    *,
    default: bool,
    editable: bool,
    key_suffix: str,
) -> None:
    """Render a double-var control table: band definitions + grid cell values.

    The first columns carry the row band definitions; the remaining columns are
    the parent-segment target-band cells (v1-style selectboxes) that define the
    risk segment grid. The default view is fully non-editable; an editable
    iteration's working grid exposes the band definitions and grid cells.
    """
    is_numerical = iteration.variable_type == VariableType.NUMERICAL
    control_columns = [_LOWER, _UPPER] if is_numerical else [_CATEGORIES]
    groups = iteration.effective_groups(default=default)
    grid = iteration.effective_risk_segment_grid(default=default)
    parent_segments = result.parent_segments
    headers = [seg.name for seg in parent_segments.values()]

    rows: list[dict[str, t.Any]] = []
    for row_gid in result.row_groups:
        row: dict[str, t.Any] = {_BAND: _group_label(row_gid)}
        _fill_band_definition(row, groups.get(row_gid), is_numerical, editable_values=True)
        for parent_gid, seg in parent_segments.items():
            target_id = grid.get(row_gid, {}).get(parent_gid, parent_gid)
            target_seg = parent_segments.get(target_id)
            row[seg.name] = target_seg.name if target_seg is not None else str(target_id)
        rows.append(row)

    columns = [_BAND, *control_columns, *headers]
    base_df = pd.DataFrame(rows, columns=columns)

    column_config: dict[str, t.Any] = {
        _BAND: st.column_config.TextColumn(label=_BAND, disabled=True),
    }
    if is_numerical:
        column_config[_LOWER] = st.column_config.NumberColumn(
            label=_LOWER, format="compact", disabled=not editable
        )
        column_config[_UPPER] = st.column_config.NumberColumn(
            label=_UPPER, format="compact", disabled=not editable
        )
    else:
        column_config[_CATEGORIES] = st.column_config.TextColumn(
            label=_CATEGORIES, disabled=not editable
        )
    for header in headers:
        column_config[header] = st.column_config.SelectboxColumn(
            label=header, options=headers, required=True, disabled=not editable
        )

    if not editable:
        st.dataframe(base_df, width="stretch", hide_index=True)
        return

    editor_key = f"grid_editor_{key_suffix}_{int(iteration.uid)}"

    def on_change() -> None:
        edited_rows: dict[int, dict[str, t.Any]] = st.session_state[editor_key].get(
            "edited_rows", {}
        )
        frame = base_df.copy()
        for row_pos, row_change in edited_rows.items():
            for column, change in row_change.items():
                frame.at[row_pos, column] = change

        new_groups: OrderedDict[RiskSegmentID, NumericalGroup | CategoricalGroup] = (
            OrderedDict()
        )
        for i, gid in enumerate(groups):
            row = frame.iloc[i]
            if is_numerical:
                original = t.cast(NumericalGroup, groups[gid])
                lower = row[_LOWER]
                upper = row[_UPPER]
                if pd.isna(lower):
                    lower = original.lower_bound
                if pd.isna(upper):
                    upper = original.upper_bound
                new_groups[gid] = NumericalGroup(
                    lower_bound=float(lower), upper_bound=float(upper)
                )
            else:
                new_groups[gid] = CategoricalGroup(
                    categories=frozenset(_parse_categories(row[_CATEGORIES]))
                )

        name_to_id = {seg.name: seg_id for seg_id, seg in parent_segments.items()}
        new_grid: dict[RiskSegmentID, dict[RiskSegmentID, RiskSegmentID]] = {}
        for i, gid in enumerate(groups):
            row = frame.iloc[i]
            row_map: dict[RiskSegmentID, RiskSegmentID] = {}
            for header, parent_gid in zip(headers, parent_segments):
                row_map[parent_gid] = name_to_id.get(row[header], parent_gid)
            new_grid[gid] = row_map

        simulation_vm.set_controls(iteration.uid, new_groups)
        simulation_vm.set_risk_segment_grid(iteration.uid, new_grid)

    st.data_editor(
        base_df,
        column_config=column_config,
        hide_index=True,
        num_rows="fixed",
        width="stretch",
        key=editor_key,
        on_change=on_change,
    )


def _active_bands_editor(
    simulation_vm: SimulationViewModel, iteration: SimulationIteration
) -> None:
    """Render an active-bands (group mask) table for a double-variable iteration.

    The Apply action lives in the sidebar; only the editable table is shown here.
    """
    key = f"active_bands_{int(iteration.uid)}"
    default_groups = iteration.default_groups
    rows = [
        {
            _BAND: _group_label(gid),
            _ACTIVE: iteration.groups_mask.get(gid, True),
        }
        for gid in default_groups
    ]
    base_df = pd.DataFrame(rows, columns=[_BAND, _ACTIVE])
    st.data_editor(
        base_df,
        column_config={
            _BAND: st.column_config.TextColumn(label=_BAND, disabled=True),
            _ACTIVE: st.column_config.CheckboxColumn(label=_ACTIVE, required=True),
        },
        hide_index=True,
        num_rows="fixed",
        width="stretch",
        key=key,
    )


def _render_grid_metric_tables(
    simulation_vm: SimulationViewModel,
    iteration: SimulationIteration,
    result: MetricGridResult,
    *,
    default: bool,
    parent_labels: dict[RiskSegmentID, str] | None = None,
) -> None:
    """Render one non-editable metric table per column in the grid result.

    Each table shares the control table's dimensions (band definitions plus a
    parent-segment column per grid cell) and appends a Total row and Total
    column. All cells are non-editable display values.
    """
    if not result.columns:
        st.caption("Set metrics in the sidebar to populate the metric grids.")
        return

    is_numerical = iteration.variable_type == VariableType.NUMERICAL
    control_columns = [_LOWER, _UPPER] if is_numerical else [_CATEGORIES]
    groups = iteration.effective_groups(default=default)

    parent_items = list(result.parent_segments.items())
    display_headers: list[str] = []
    for parent_gid, seg in parent_items:
        header = (
            f"{parent_labels[parent_gid]} · {seg.name}"
            if parent_labels and parent_gid in parent_labels
            else seg.name
        )
        display_headers.append(header)
    columns = [_BAND, *control_columns, *display_headers, _TOTAL]

    for column_name, metric in result.columns:
        st.markdown(f"##### {column_name}")
        rows: list[dict[str, str]] = []
        for row_gid in result.row_groups:
            row: dict[str, str] = {_BAND: _group_label(row_gid)}
            _fill_band_definition(
                row, groups.get(row_gid), is_numerical, editable_values=False
            )
            for i, (parent_gid, _seg) in enumerate(parent_items):
                row[display_headers[i]] = _format_value(
                    metric, result.cell(row_gid, parent_gid, column_name)
                )
            row[_TOTAL] = _format_value(
                metric, result.total_column.get(column_name, {}).get(row_gid)
            )
            rows.append(row)

        total_row: dict[str, str] = {_BAND: _TOTAL}
        for control_column in control_columns:
            total_row[control_column] = ""
        for i, (parent_gid, _seg) in enumerate(parent_items):
            total_row[display_headers[i]] = _format_value(
                metric, result.total_row.get(column_name, {}).get(parent_gid)
            )
        total_row[_TOTAL] = _format_value(metric, result.corner_total.get(column_name))
        rows.append(total_row)

        st.dataframe(
            pd.DataFrame(rows, columns=columns),
            width="stretch",
            hide_index=True,
        )


def _double_var_body(
    simulation_vm: SimulationViewModel,
    iteration: SimulationIteration,
) -> None:
    metadata = simulation_vm.iteration_metadata(iteration.uid)
    parent_labels: dict[RiskSegmentID, str] | None = None
    if metadata.show_prev_iter_details:
        labels = group_display_labels(simulation_vm, iteration.uid)
        parent_labels = labels if labels else None

    default_result = simulation_vm.get_iteration_grid(
        iteration.uid, show_total_row=True, show_total_column=True, default=True
    )
    if default_result.errors:
        for error in default_result.errors:
            st.error(error, icon=":material/error:")
        return
    for warning in default_result.warnings:
        st.caption(f"⚠ {warning}")

    st.markdown("##### Default Risk Segment Grid")
    _grid_control_table(
        simulation_vm,
        iteration,
        default_result,
        default=True,
        editable=False,
        key_suffix="default",
    )
    st.markdown("##### Default Metric Grids")
    _render_grid_metric_tables(
        simulation_vm,
        iteration,
        default_result,
        default=True,
        parent_labels=parent_labels,
    )

    if not iteration.is_editable:
        return

    st.divider()
    working_result = simulation_vm.get_iteration_grid(
        iteration.uid, show_total_row=True, show_total_column=True, default=False
    )
    if working_result.errors:
        for error in working_result.errors:
            st.error(error, icon=":material/error:")
        return
    for warning in working_result.warnings:
        st.caption(f"⚠ {warning}")

    st.markdown("##### Editable Risk Segment Grid")
    _grid_control_table(
        simulation_vm,
        iteration,
        working_result,
        default=False,
        editable=True,
        key_suffix="editable",
    )
    st.markdown("##### Active Bands")
    _active_bands_editor(simulation_vm, iteration)
    st.markdown("##### Editable Metric Grids")
    _render_grid_metric_tables(
        simulation_vm,
        iteration,
        working_result,
        default=False,
        parent_labels=parent_labels,
    )


def _single_var_body(
    simulation_vm: SimulationViewModel,
    iteration: SimulationIteration,
) -> None:
    st.markdown("##### Default Range")
    _combined_band_table(
        simulation_vm, iteration, default=True, editable=False, key_suffix="default"
    )
    st.divider()
    st.markdown("##### Editable Range")
    _combined_band_table(
        simulation_vm,
        iteration,
        default=False,
        editable=iteration.is_editable,
        key_suffix="editable",
    )


def simulation_iteration_view() -> None:
    """Render the iteration page for the currently selected iteration."""
    session = get_session()
    simulation_vm = session.simulation_view_model

    iteration = simulation_vm.current_iteration
    if iteration is None:
        simulation_vm.set_mode("graph")
        st.rerun()
        return

    iteration_navigation(simulation_vm, iteration.uid)

    _sidebar(simulation_vm, iteration)

    for error in simulation_vm.errors:
        st.error(error, icon=":material/error:")
    simulation_vm.clear_errors()

    scg = simulation_vm.scg_for(simulation_vm.simulations[iteration.simulation_id])

    if iteration.is_double_var and iteration.is_editable:
        badge, color = "Double-Variable · Editable", "green"
    elif iteration.is_double_var:
        badge, color = "Double-Variable", "orange"
    elif iteration.is_editable:
        badge, color = "Single-Variable · Editable", "blue"
    else:
        badge, color = "Single-Variable", "violet"

    st.title(f"Iteration #{int(iteration.uid)}")
    st.badge(badge, icon=":material/timeline:", color=color)
    st.caption(
        f"**{scg.name}** · derived from Simulation "
        f"**#{short_id(iteration.simulation_id)}** · variable **{iteration.variable_name}**"
    )

    chain = simulation_vm.iteration_chain(iteration.uid)
    if len(chain) > 1:
        lineage = " → ".join(f"Iteration #{int(it.uid)}" for it in chain)
        st.caption(f"Lineage: **{lineage}**")

    st.divider()

    if iteration.is_double_var:
        _double_var_body(simulation_vm, iteration)
    else:
        _single_var_body(simulation_vm, iteration)


__all__ = ["simulation_iteration_view"]