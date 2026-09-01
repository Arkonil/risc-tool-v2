"""Full risk-segment editor for the simulation creator.

Renders an editable table (name, upper rate, colors) with add/delete/color
controls, mirroring the v1 configuration page but operating directly on a
SimulationConfigGenerator's RiskSegmentConfig.
"""

import typing as t
from collections import OrderedDict
from typing import Any

import pandas as pd
import streamlit as st

from risc_tool_v2.data.core.uid import RiskSegmentID
from risc_tool_v2.data.simulation.models.risk_segment import (
    RiskSegment,
    RiskSegmentConfig,
    is_valid_hex_color,
)

_EDITOR_KEY = "sim_risk_seg_editor"
_ROWS_KEY = "sim_risk_seg_rows"


def _rows_from_config(config: RiskSegmentConfig) -> list[dict[str, Any]]:
    """Build editable row dicts (with derived lower bound) from a config."""
    normalized = config.get_segments(normalize=True)
    rows: list[dict[str, Any]] = []
    lower = 0.0
    for seg_id, seg in config.segments.items():
        norm_upper = normalized[seg_id].upper_rate
        rows.append({
            "uid": seg_id,
            "name": seg.name,
            "lower_rate": lower,
            "upper_rate": (
                None if seg.upper_rate == float("inf") else seg.upper_rate * 100
            ),
            "upper_rate_inf": seg.upper_rate == float("inf"),
            "bg_color": seg.bg_color,
            "font_color": seg.font_color,
            "selected": False,
        })
        lower = norm_upper
    return rows


def _rows_to_config(rows: list[dict[str, Any]]) -> RiskSegmentConfig:
    """Rebuild a RiskSegmentConfig from edited row dicts."""
    segments: OrderedDict[RiskSegmentID, RiskSegment] = OrderedDict()
    for row in rows:
        seg_id: RiskSegmentID = row["uid"]
        if row.get("upper_rate_inf"):
            upper = float("inf")
        else:
            upper = float(row.get("upper_rate") or 0.0) / 100.0

        base: dict[str, t.Any] = {
            "name": str(row.get("name", "")).strip() or "Segment",
            "upper_rate": upper,
            "bg_color": str(row.get("bg_color", "#3D8F3D")),
            "font_color": str(row.get("font_color", "#FFFFFF")),
        }

        if seg_id in (
            RiskSegmentID.TEMPORARY,
            RiskSegmentID.EMPTY,
            RiskSegmentID.UNSET,
        ):
            seg = RiskSegment(**base)
            segments[seg.uid] = seg
        else:
            seg = RiskSegment(uid=seg_id, **base)
            segments[seg.uid] = seg

    return RiskSegmentConfig(segments=segments)


def _init_rows(config: RiskSegmentConfig) -> None:
    if _ROWS_KEY not in st.session_state:
        st.session_state[_ROWS_KEY] = _rows_from_config(config)


def _dataframe_from_rows(rows: list[dict[str, Any]]) -> pd.DataFrame:
    return pd.DataFrame({
        "Selected": [r["selected"] for r in rows],
        "Risk Segment": [r["name"] for r in rows],
        "Lower Rate": [f"{r['lower_rate'] * 100:.2f} %" for r in rows],
        "Upper Rate (%)": [
            "None" if r.get("upper_rate_inf") else f"{r['upper_rate']:.2f}"
            for r in rows
        ],
        "Background Color": [r["bg_color"] for r in rows],
        "Font Color": [r["font_color"] for r in rows],
    })


def _add_row() -> None:
    rows = st.session_state[_ROWS_KEY]
    rows.append({
        "uid": RiskSegmentID.TEMPORARY,
        "name": "",
        "lower_rate": 0.0,
        "upper_rate": None,
        "upper_rate_inf": True,
        "bg_color": "#3D8F3D",
        "font_color": "#FFFFFF",
        "selected": False,
    })
    st.session_state[_ROWS_KEY] = rows


def _delete_selected() -> None:
    rows = st.session_state[_ROWS_KEY]
    rows = [r for r in rows if not r["selected"]]
    st.session_state[_ROWS_KEY] = rows


def _apply_color(color: str, field: str) -> None:
    if not color or not is_valid_hex_color(color):
        return
    rows = st.session_state[_ROWS_KEY]
    for r in rows:
        if r["selected"]:
            r[field] = color.upper()
    st.session_state[_ROWS_KEY] = rows


def _reset_defaults() -> None:
    st.session_state[_ROWS_KEY] = _rows_from_config(RiskSegmentConfig())


def _sync_editor_to_rows(edited_df: pd.DataFrame) -> None:
    """Write edited dataframe values back into the row dicts, preserving order."""
    rows = st.session_state[_ROWS_KEY]
    for i, row in enumerate(rows):
        if i >= len(edited_df):
            break
        df_row: Any = edited_df.iloc[i]

        row["selected"] = bool(df_row.get("Selected", False))

        new_name = str(df_row.get("Risk Segment", "")).strip()
        if new_name:
            row["name"] = new_name

        upper_val = df_row.get("Upper Rate (%)")
        if upper_val is None or (
            isinstance(upper_val, str) and upper_val.strip() == ""
        ):
            row["upper_rate_inf"] = True
            row["upper_rate"] = None
        else:
            try:
                row["upper_rate"] = float(upper_val)
                row["upper_rate_inf"] = False
            except (ValueError, TypeError):
                row["upper_rate_inf"] = True
                row["upper_rate"] = None

        new_bg = str(df_row.get("Background Color", "")).strip().upper()
        if new_bg and new_bg.startswith("#"):
            row["bg_color"] = new_bg
        new_fg = str(df_row.get("Font Color", "")).strip().upper()
        if new_fg and new_fg.startswith("#"):
            row["font_color"] = new_fg

    st.session_state[_ROWS_KEY] = rows


def _validate_upper_rates(rows: list[dict[str, Any]]) -> bool:
    """Validate monotonic non-decreasing upper rates; returns True if valid."""
    prev = 0.0
    for row in rows:
        val = (
            float("inf")
            if row.get("upper_rate_inf")
            else float(row.get("upper_rate") or 0.0)
        )
        if val < prev:
            st.error(
                f"Upper Rate of segment '{row['name'] or '(unnamed)'}' cannot be "
                f"lower than the previous segment.",
                icon=":material/error:",
            )
            return False
        prev = val
    return True


def _color_selector(color_type: str, field: str) -> None:
    col1, col2 = st.columns([1, 3])
    with col1:
        chosen = st.color_picker(
            label=f"{color_type.capitalize()} Color",
            label_visibility="collapsed",
            value="#FFFFFF" if color_type == "font" else "#3D8F3D",
            key=f"sim_color_picker_{color_type}",
        )
    with col2:
        st.button(
            label=f"Use {color_type.capitalize()} Color",
            width="stretch",
            type="secondary",
            icon=":material/palette:",
            on_click=_apply_color,
            args=(chosen, field),
            key=f"sim_btn_color_{color_type}",
        )


def risk_segment_editor(config: RiskSegmentConfig) -> RiskSegmentConfig:
    """Render the risk segment table and controls; return the edited config."""
    st.subheader("Risk Segment Details")

    _init_rows(config)

    column_config = {
        "Selected": st.column_config.CheckboxColumn(label="Selected", default=False),
        "Risk Segment": st.column_config.TextColumn(label="Risk Segment"),
        "Lower Rate": st.column_config.TextColumn(
            label="Lower Rate", disabled=True, alignment="right"
        ),
        "Upper Rate (%)": st.column_config.TextColumn(
            label="Upper Rate (%)", alignment="right"
        ),
        "Background Color": st.column_config.TextColumn(
            label="Background Color", disabled=True
        ),
        "Font Color": st.column_config.TextColumn(label="Font Color", disabled=True),
    }

    col11, col12 = st.columns([4, 1], vertical_alignment="bottom")
    col21, col22 = st.columns([4, 1])

    with col11:
        st.markdown("##### Segments")

    with col21:
        edited_df = st.data_editor(
            _dataframe_from_rows(st.session_state[_ROWS_KEY]),
            column_order=[
                "Selected",
                "Risk Segment",
                "Lower Rate",
                "Upper Rate (%)",
                "Background Color",
                "Font Color",
            ],
            column_config=column_config,
            width="stretch",
            hide_index=True,
            key=_EDITOR_KEY,
        )

    # Write the editor's current contents into the persistent row state.
    _sync_editor_to_rows(edited_df)

    selected_count = sum(1 for r in st.session_state[_ROWS_KEY] if r["selected"])
    has_selection = selected_count > 0

    col12.write("#### Controls")
    with col22:
        st.button(
            label="Add Row",
            width="stretch",
            type="secondary",
            icon=":material/add:",
            on_click=_add_row,
            key="sim_btn_add_row",
        )
        st.button(
            label="Delete Selected",
            width="stretch",
            type="secondary",
            icon=":material/delete:",
            disabled=not has_selection,
            on_click=_delete_selected,
            key="sim_btn_delete_row",
        )

        _color_selector("font", "font_color")
        _color_selector("background", "bg_color")

        st.button(
            label="Reset Defaults",
            width="stretch",
            type="secondary",
            icon=":material/restart_alt:",
            on_click=_reset_defaults,
            key="sim_btn_reset_risk_seg",
        )

    st.caption(
        "A :blue-badge[`None`] / empty value in **Upper Rate (%)** represents "
        "_+Infinity_."
    )

    rows = st.session_state[_ROWS_KEY]
    if not _validate_upper_rates(rows):
        return _rows_to_config(rows)

    return _rows_to_config(rows)


__all__ = ["risk_segment_editor"]
