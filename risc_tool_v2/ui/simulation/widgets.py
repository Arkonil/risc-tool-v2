"""Low-level, prop-driven widgets for the simulation creator.

Each widget renders a single control from its current value plus a stable
widget key, and returns the (possibly edited) value. Widgets may read option
lists (columns, filters, data sources) from the session, but they never read or
mutate the draft; the high-level section components in ``simulation_creator``
own session/SCG access, diff the returned value against the draft field, and
call the matching ViewModel update method.
"""

import typing as t
from enum import StrEnum

import pandas as pd
import streamlit as st
from pandas.io.formats.style import Styler
from streamlit.delta_generator import DeltaGenerator

from risc_tool_v2.data.core.enums import LossRateTypes, VariableType
from risc_tool_v2.data.core.uid import DataSourceID, FilterID
from risc_tool_v2.data.session import Session
from risc_tool_v2.data.simulation.models.risk_segment import RiskSegmentConfig
from risc_tool_v2.ui.core.session import get_session


class MafColumn(StrEnum):
    """Column names of the risk-scalar-factor (maturity-adjustment) data editor."""

    RISK_SEGMENT = "Risk Segment"
    MAF = "MAF"
    RISK_SCALAR_FACTOR = "Risk Scalar Factor"


def _session() -> Session:
    return get_session()


def metric_text_widget(column: DeltaGenerator, text: str) -> None:
    column.html(
        f"""
        <div style="display: flex; justify-content: center; font-size: 1.5em; font-weight: bold;">
            <span>{text}</span>
        </div>
        """
    )


def ds_label(ds_id: DataSourceID) -> str:
    return _session().data_repository.data_sources[ds_id].label


def data_source_ids() -> list[DataSourceID]:
    return list(_session().data_repository.data_sources.keys())


def data_source_selector(
    key: str,
    default_ids: tuple[DataSourceID, ...],
) -> tuple[DataSourceID, ...]:
    options = data_source_ids()

    col1, col2, col3 = st.columns([4, 1, 11], gap=None)
    metric_text_widget(col1, "Data Sources")
    metric_text_widget(col2, "=")
    with col3:
        selected = st.multiselect(
            label="Select Data Sources",
            options=options,
            default=list(default_ids),
            format_func=ds_label,
            key=key,
            width="stretch",
            label_visibility="collapsed",
            placeholder="Select Data Sources",
        )
    return tuple(selected)


def column_selector(
    key: str,
    placeholder: str,
    current: str | None,
    data_source_ids: tuple[DataSourceID, ...] | None = None,
) -> str | None:
    sim_vm = _session().simulation_view_model
    if data_source_ids is None:
        columns = sim_vm.common_columns
    else:
        columns = sim_vm.selected_common_columns(data_source_ids)

    selected = st.selectbox(
        label=key,
        options=columns,
        index=columns.index(current) if current in columns else None,
        label_visibility="collapsed",
        key=key,
        placeholder=placeholder,
    )
    return selected


def unit_bad_rate_row(
    label: str,
    key: str,
    numerator: str | None,
    data_source_ids: tuple[DataSourceID, ...] | None = None,
) -> str | None:
    col1, col2, col3, col4, col5 = st.columns([4, 1, 5, 1, 5], gap=None)
    metric_text_widget(col1, label)
    metric_text_widget(col2, "=")
    with col3:
        unt_bad = column_selector(
            key=f"{key}_unt_bad",
            placeholder="# Bad Count",
            current=numerator,
            data_source_ids=data_source_ids,
        )
    metric_text_widget(col4, "/")
    metric_text_widget(col5, "# Accounts")
    return unt_bad


def dollar_bad_rate_row(
    label: str,
    key: str,
    numerator: str | None,
    denominator: str | None,
    data_source_ids: tuple[DataSourceID, ...] | None = None,
) -> tuple[str | None, str | None]:
    col1, col2, col3, col4, col5 = st.columns([4, 1, 5, 1, 5], gap=None)
    metric_text_widget(col1, label)
    metric_text_widget(col2, "=")
    with col3:
        dlr_bad = column_selector(
            key=f"{key}_dlr_bad",
            placeholder="$ Bad Amount",
            current=numerator,
            data_source_ids=data_source_ids,
        )
    metric_text_widget(col4, "/")
    with col5:
        avg_bal = column_selector(
            key=f"{key}_avg_bal",
            placeholder="$ Avg Balance",
            current=denominator,
            data_source_ids=data_source_ids,
        )
    return dlr_bad, avg_bal


def mob_selector(key: str, default_mob: int, label: str = "MOB") -> int:
    col1, col2, col3, _ = st.columns([4, 1, 5, 6], gap=None)
    metric_text_widget(col1, label)
    metric_text_widget(col2, "=")
    with col3:
        return st.number_input(
            label="Current Rate MOB",
            value=default_mob,
            min_value=1,
            max_value=100,
            step=1,
            label_visibility="collapsed",
            format="%d",
            key=key,
        )


def name_input(current: str) -> str:
    st.markdown("##### Simulation Name")
    return st.text_input(
        label="Simulation Name",
        value=current,
        label_visibility="collapsed",
        key="sim_name",
        placeholder="Simulation Name",
    )


def variable_type_selector(current: VariableType) -> VariableType:
    st.markdown("##### Variable Type")
    options = [VariableType.NUMERICAL, VariableType.CATEGORICAL]
    return st.selectbox(
        label="Variable Type",
        options=options,
        index=options.index(current),
        label_visibility="collapsed",
        key="sim_variable_type",
    )


def loss_rate_type_selector(current: LossRateTypes) -> LossRateTypes:
    st.markdown("##### Loss Rate Type")
    return st.selectbox(
        label="Loss Rate Type",
        options=list(LossRateTypes),
        index=list(LossRateTypes).index(current),
        label_visibility="collapsed",
        key="sim_loss_rate_type",
    )


def variable_selector(current: str) -> str:
    columns = _session().simulation_view_model.common_columns
    st.markdown("##### Variable Name")
    return st.selectbox(
        label="Variable",
        options=columns,
        index=columns.index(current) if current in columns else 0,
        label_visibility="collapsed",
        key="sim_variable",
        placeholder="Select variable to band",
    )


def filter_selector(current: tuple[FilterID, ...]) -> tuple[FilterID, ...]:
    filters = _session().simulation_view_model.filters

    st.markdown("##### Select Filters")
    selected = st.multiselect(
        label="Select Filters",
        options=sorted(filters.keys()),
        default=list(current),
        label_visibility="collapsed",
        format_func=lambda fid: filters[fid].name,
        key="sim_filters",
        placeholder="Select Filters",
    )
    return tuple(selected)


def toggle_checkbox(label: str, current: bool, key: str) -> bool:
    return st.checkbox(label, value=current, key=key)


def numeric_input(
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


def _maf_df(
    config: RiskSegmentConfig,
    loss_rate_type: LossRateTypes,
    portfolio_scalar: float,
) -> pd.DataFrame:
    rows: list[dict[str, t.Any]] = []
    for seg in config.segments.values():
        maf = seg.maf(loss_rate_type)
        rows.append({
            MafColumn.RISK_SEGMENT: seg.name,
            MafColumn.MAF: maf * 100.0,
            MafColumn.RISK_SCALAR_FACTOR: max(maf * portfolio_scalar, 1.0),
        })
    return pd.DataFrame(rows)


def _maf_styler(config: RiskSegmentConfig, df: pd.DataFrame) -> Styler:
    styled = df.style
    for index, seg in enumerate(config.segments.values()):
        styled = styled.set_properties(
            subset=(
                slice(index, index),
                slice(MafColumn.RISK_SEGMENT, MafColumn.RISK_SEGMENT),
            ),
            **{
                "color": str(seg.font_color),
                "background-color": str(seg.bg_color),
            },
        )
    return styled


def _process_maf_edits(
    config: RiskSegmentConfig,
    edited_df: pd.DataFrame,
    loss_rate_type: LossRateTypes,
) -> RiskSegmentConfig:
    field = "maf_ulr" if loss_rate_type == LossRateTypes.ULR else "maf_dlr"
    updated = config
    for i, seg in enumerate(config.segments.values()):
        if i >= len(edited_df):
            break
        df_row: t.Any = edited_df.iloc[i]
        try:
            new_maf = (
                float(df_row.get(MafColumn.MAF, getattr(seg, field) * 100.0)) / 100.0
            )
        except (ValueError, TypeError):
            continue
        if abs(new_maf - getattr(seg, field)) > 1e-6:
            updated = updated.with_updates(seg.uid, **{field: new_maf})
    return updated


def risk_scalar_factor_editor(
    config: RiskSegmentConfig,
    loss_rate_type: LossRateTypes,
    portfolio_scalar: float,
) -> RiskSegmentConfig:
    symbol = "$" if loss_rate_type == LossRateTypes.DLR else "#"
    st.markdown(f"##### Maturity Adjustment Factor ({symbol})")
    df = _maf_df(config, loss_rate_type, portfolio_scalar)
    edited_df = st.data_editor(
        _maf_styler(config, df),
        column_config={
            MafColumn.RISK_SEGMENT: st.column_config.TextColumn(
                label="Risk Segment", disabled=True
            ),
            MafColumn.MAF: st.column_config.NumberColumn(
                label="MAF (%)", format="%.1f %%", min_value=0.0
            ),
            MafColumn.RISK_SCALAR_FACTOR: st.column_config.NumberColumn(
                label="Risk Scalar Factor", format="%.2f", disabled=True
            ),
        },
        hide_index=True,
        width="stretch",
        key=f"sim_maf_editor_{loss_rate_type.value}",
    )
    return _process_maf_edits(config, edited_df, loss_rate_type)


__all__ = [
    "MafColumn",
    "column_selector",
    "data_source_ids",
    "data_source_selector",
    "dollar_bad_rate_row",
    "ds_label",
    "filter_selector",
    "loss_rate_type_selector",
    "metric_text_widget",
    "mob_selector",
    "name_input",
    "numeric_input",
    "risk_scalar_factor_editor",
    "toggle_checkbox",
    "unit_bad_rate_row",
    "variable_selector",
    "variable_type_selector",
]
