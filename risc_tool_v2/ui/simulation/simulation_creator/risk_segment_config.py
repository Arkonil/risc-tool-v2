"""Risk Segment Details high-level section for the Simulation Creator.

Renders an editable risk-segment table with two distinct selection columns:

* ``Selected``: a transient working selection used to batch operations such as
  delete or apply color. It is read from the data editor on the same frame a
  control button is pressed and always resets to ``False`` after each rerun; it
  is never persisted.
* ``Use in Simulation``: maps to ``RiskSegment.selected``, is stored on the
  draft SCG, and therefore survives reruns.

No internal ``session_state`` row cache is used: the table and the rebuilt
config are always derived from the current draft on every rerun.
"""

import math
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Literal

import pandas as pd
import streamlit as st
from pandas.io.formats.style import Styler
from streamlit.delta_generator import DeltaGenerator

from risc_tool_v2.data.core.uid import RiskSegmentID
from risc_tool_v2.data.simulation.models.risk_segment import RiskSegmentConfig
from risc_tool_v2.data.simulation.models.simulation_config import (
    SimulationConfigGenerator,
)
from risc_tool_v2.ui.simulation.simulation_creator.base import reconcile, vm

_EDITOR_KEY = "sim_risk_seg_editor"

ColorField = Literal["bg_color", "font_color"]
Action = Literal["add", "delete", "color", "reset"]


class SegmentColumn(StrEnum):
    """Column names of the risk-segment data editor."""

    SELECTED = "Selected"
    USE_IN_SIMULATION = "Use in Simulation"
    NAME = "Risk Segment"
    UPPER_RATE = "Upper Rate (%)"
    BG_COLOR = "Background Color"
    FONT_COLOR = "Font Color"


@dataclass(frozen=True)
class ControlResult:
    """The action triggered by the risk-segment control buttons."""

    action: Action | None
    field: ColorField | None = None
    color: str | None = None


def _rows_from_config(config: RiskSegmentConfig) -> list[dict[str, Any]]:
    """Build editable row dicts from a config."""
    rows: list[dict[str, Any]] = []
    for seg_id, seg in config.segments.items():
        rows.append({
            "uid": seg_id,
            "selected_op": False,
            "selected": seg.selected,
            "name": seg.name,
            "upper_rate": (
                None if seg.upper_rate == float("inf") else seg.upper_rate * 100
            ),
            "bg_color": seg.bg_color,
            "font_color": seg.font_color,
        })
    return rows


def _dataframe_from_rows(rows: list[dict[str, Any]]) -> pd.DataFrame:
    return pd.DataFrame({
        SegmentColumn.SELECTED: [r["selected_op"] for r in rows],
        SegmentColumn.USE_IN_SIMULATION: [r["selected"] for r in rows],
        SegmentColumn.NAME: [r["name"] for r in rows],
        SegmentColumn.UPPER_RATE: [r["upper_rate"] for r in rows],
        SegmentColumn.FONT_COLOR: [r["font_color"] for r in rows],
        SegmentColumn.BG_COLOR: [r["bg_color"] for r in rows],
    })


def _styler_from_config(config: RiskSegmentConfig) -> Styler:
    """Build a Styler whose color cells render as live swatches.

    Streamlit applies Styler styles only to disabled columns, so the per-row
    font/background colors paint the read-only Font Color / Background Color
    cells.
    """
    styled = _dataframe_from_rows(_rows_from_config(config)).style
    for index, seg in enumerate(config.segments.values()):
        styled = styled.set_properties(
            subset=(
                slice(index, index),
                slice(SegmentColumn.FONT_COLOR, SegmentColumn.BG_COLOR),
            ),
            **{
                "color": str(seg.font_color),
                "background-color": str(seg.bg_color),
            },
        )
    return styled


def _parse_upper(value: Any) -> float:
    if value is None or (isinstance(value, str) and value.strip() == ""):
        return float("inf")
    try:
        parsed = float(value)
    except (ValueError, TypeError):
        return float("inf")
    if math.isnan(parsed) or math.isinf(parsed):
        return float("inf")
    return parsed / 100.0


def _apply_edits(
    config: RiskSegmentConfig, edited_df: pd.DataFrame
) -> RiskSegmentConfig:
    """Apply cell edits (name, upper rate, use-in-simulation) to a copy.

    Rows are matched to segments by position. Editing ``selected`` re-keys the
    affected segment through ``RiskSegmentConfig.with_updates``, which derives a
    fresh content-addressed identity. MAF and color fields are not edited here
    (colors go through the controls; MAF through the scalar section).
    """
    updated = config
    for i, seg in enumerate(config.segments.values()):
        if i >= len(edited_df):
            break
        df_row: Any = edited_df.iloc[i]
        updates: dict[str, Any] = {}

        new_name = str(df_row.get(SegmentColumn.NAME, "")).strip()
        if new_name and new_name != seg.name:
            updates["name"] = new_name

        new_upper = _parse_upper(df_row.get(SegmentColumn.UPPER_RATE))
        if new_upper != seg.upper_rate:
            updates["upper_rate"] = new_upper

        new_selected = bool(df_row.get(SegmentColumn.USE_IN_SIMULATION, seg.selected))
        if new_selected != seg.selected:
            updates["selected"] = new_selected

        if updates:
            updated = updated.with_updates(seg.uid, **updates)
    return updated


def _operation_selected_ids(
    config: RiskSegmentConfig, edited_df: pd.DataFrame
) -> tuple[RiskSegmentID, ...]:
    """Return the uids of rows checked in the transient ``Selected`` column."""
    ids: list[RiskSegmentID] = []
    for i, seg_id in enumerate(config.segments.keys()):
        if i >= len(edited_df):
            break
        if bool(edited_df.iloc[i].get(SegmentColumn.SELECTED, False)):
            ids.append(seg_id)
    return tuple(ids)


def _validate_upper_rates(edited_df: pd.DataFrame, config: RiskSegmentConfig) -> bool:
    """Validate monotonic non-decreasing upper rates; returns True if valid."""
    prev = 0.0
    for i, seg in enumerate(config.segments.values()):
        if i >= len(edited_df):
            break
        row: Any = edited_df.iloc[i]
        val = _parse_upper(row.get(SegmentColumn.UPPER_RATE))
        if val < prev:
            name = str(row.get(SegmentColumn.NAME, "")) or seg.name or "(unnamed)"
            vm().add_error(
                f"Upper Rate of segment '{name}' cannot be lower than the "
                "previous segment."
            )
            return False
        prev = val
    return True


def _controls(has_op_selection: bool, container: DeltaGenerator) -> ControlResult:
    """Render the risk-segment control buttons and color pickers.

    ``container`` is the column widget inside which the controls are drawn.
    """
    result = ControlResult(action=None)

    with container:
        if st.button(
            label="Add Row",
            width="stretch",
            type="secondary",
            icon=":material/add:",
            key="sim_btn_add_row",
        ):
            result = ControlResult(action="add")

        if st.button(
            label="Delete Selected",
            width="stretch",
            type="secondary",
            icon=":material/delete:",
            disabled=not has_op_selection,
            key="sim_btn_delete_row",
        ):
            result = ControlResult(action="delete")

        if st.button(
            label="Reset Defaults",
            width="stretch",
            type="secondary",
            icon=":material/restart_alt:",
            key="sim_btn_reset_risk_seg",
        ):
            result = ControlResult(action="reset")

        font_color = _color_selector(
            "font", "sim_color_picker_font", "sim_btn_color_font"
        )
        if font_color is not None:
            result = ControlResult(action="color", field="font_color", color=font_color)

        bg_color = _color_selector(
            "background",
            "sim_color_picker_background",
            "sim_btn_color_background",
        )
        if bg_color is not None:
            result = ControlResult(action="color", field="bg_color", color=bg_color)

    return result


def _color_selector(color_type: str, picker_key: str, button_key: str) -> str | None:
    col1, col2 = st.columns([1, 3])
    with col1:
        chosen = st.color_picker(
            label=f"{color_type.capitalize()} Color",
            label_visibility="collapsed",
            value="#FFFFFF" if color_type == "font" else "#3D8F3D",
            key=picker_key,
        )
    with col2:
        pressed = st.button(
            label=f"Use {color_type.capitalize()} Color",
            width="stretch",
            type="secondary",
            icon=":material/palette:",
            key=button_key,
        )
    return chosen if pressed else None


def risk_segment_config_section(draft: SimulationConfigGenerator) -> None:
    """Render the risk-segment table and controls; persist edits via the VM."""
    sim_vm = vm()
    config = draft.risk_segment_config
    st.subheader("Risk Segment Details")

    col_edit, col_ctrl = st.columns([4, 1])
    with col_edit:
        edited_df = st.data_editor(
            _styler_from_config(config),
            column_order=[
                SegmentColumn.SELECTED,
                SegmentColumn.USE_IN_SIMULATION,
                SegmentColumn.NAME,
                SegmentColumn.UPPER_RATE,
                SegmentColumn.FONT_COLOR,
                SegmentColumn.BG_COLOR,
            ],
            column_config={
                SegmentColumn.SELECTED: st.column_config.CheckboxColumn(
                    label="Selected", default=False
                ),
                SegmentColumn.USE_IN_SIMULATION: st.column_config.CheckboxColumn(
                    label="Use in Simulation", default=True
                ),
                SegmentColumn.NAME: st.column_config.TextColumn(label="Risk Segment"),
                SegmentColumn.UPPER_RATE: st.column_config.NumberColumn(
                    label="Upper Rate (%)",
                    format="%.2f %%",
                    min_value=0.0,
                    max_value=100.0,
                ),
                SegmentColumn.FONT_COLOR: st.column_config.TextColumn(
                    label="Font Color", disabled=True
                ),
                SegmentColumn.BG_COLOR: st.column_config.TextColumn(
                    label="Background Color", disabled=True
                ),
            },
            width="stretch",
            hide_index=True,
            key=_EDITOR_KEY,
            placeholder="∞",
        )

        has_op_selection = bool(_operation_selected_ids(config, edited_df))
        if not _validate_upper_rates(edited_df, config):
            st.caption(
                "A :blue-badge[`∞`] / empty value in **Upper Rate (%)** "
                "represents _+Infinity_."
            )
            return

    control = _controls(has_op_selection, col_ctrl)

    if control.action == "add":
        sim_vm.add_risk_segment()
        st.rerun()
    elif control.action == "delete":
        sim_vm.delete_risk_segments(_operation_selected_ids(config, edited_df))
        st.rerun()
    elif control.action == "color" and control.field is not None and control.color:
        sim_vm.apply_color_to_segments(
            control.color, control.field, _operation_selected_ids(config, edited_df)
        )
        st.rerun()
    elif control.action == "reset":
        sim_vm.reset_risk_segments()
        st.rerun()

    new_config = _apply_edits(config, edited_df)
    reconcile(
        config,
        new_config,
        lambda: sim_vm.update_draft_risk_segments(new_config),
    )

    st.caption(
        "A :blue-badge[`∞`] / empty value in **Upper Rate (%)** represents _+Infinity_."
    )


__all__ = ["SegmentColumn", "risk_segment_config_section"]
