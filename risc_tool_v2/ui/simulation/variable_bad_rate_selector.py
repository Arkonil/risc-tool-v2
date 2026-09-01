"""Bad rate variable selectors for the simulation creator.

Renders the Target (dev) and Early (test) bad rate sections, each using a
single shared data-source selector applied to both the unit (#) and dollar ($)
bad rates, and returns the four resulting BadRateConfigs.
"""

from dataclasses import dataclass

import streamlit as st
from streamlit.delta_generator import DeltaGenerator

from risc_tool_v2.data.core.enums import LossRateTypes
from risc_tool_v2.data.core.uid import DataSourceID
from risc_tool_v2.data.session import Session
from risc_tool_v2.data.simulation.models.simulation_config import BadRateConfig


@dataclass(frozen=True)
class BadRateSelection:
    """The four bad rate configs selected for a simulation."""

    dev_unit_bad_rate: BadRateConfig
    dev_dollar_bad_rate: BadRateConfig
    test_unit_bad_rate: BadRateConfig
    test_dollar_bad_rate: BadRateConfig


def _metric_text_widget(column: DeltaGenerator, text: str) -> None:
    column.html(
        f"""
        <div style="display: flex; justify-content: center; font-size: 1.5em; font-weight: bold;">
            <span>{text}</span>
        </div>
        """
    )


def _ds_label(ds_id: DataSourceID) -> str:
    session: Session = st.session_state["session"]
    return session.data_repository.data_sources[ds_id].label


def _data_source_ids(session: Session) -> list[DataSourceID]:
    return list(session.data_repository.data_sources.keys())


def _data_source_selector(
    key: str,
    default_ids: tuple[DataSourceID, ...],
) -> tuple[DataSourceID, ...]:
    session: Session = st.session_state["session"]
    options = _data_source_ids(session)

    col1, col2, col3 = st.columns([4, 1, 11], gap=None)
    _metric_text_widget(col1, "Data Sources")
    _metric_text_widget(col2, "=")
    with col3:
        selected = st.multiselect(
            label="Select Data Sources",
            options=options,
            default=list(default_ids),
            format_func=_ds_label,
            key=key,
            width="stretch",
            label_visibility="collapsed",
            placeholder="Select Data Sources",
        )
    return tuple(selected)


def _column_selector(
    key: str,
    placeholder: str,
    current: str | None,
) -> str | None:
    session: Session = st.session_state["session"]
    columns = session.simulation_view_model.common_columns

    selected = st.selectbox(
        label=key,
        options=columns,
        index=columns.index(current) if current in columns else None,
        label_visibility="collapsed",
        key=key,
        placeholder=placeholder,
    )
    return selected


def _unit_bad_rate_row(
    label: str,
    key: str,
    numerator: str | None,
) -> str | None:
    col1, col2, col3, col4, col5 = st.columns([4, 1, 5, 1, 5], gap=None)
    _metric_text_widget(col1, label)
    _metric_text_widget(col2, "=")
    with col3:
        unt_bad = _column_selector(
            key=f"{key}_unt_bad", placeholder="# Bad Count", current=numerator
        )
    _metric_text_widget(col4, "/")
    _metric_text_widget(col5, "# Accounts")
    return unt_bad


def _dollar_bad_rate_row(
    label: str,
    key: str,
    numerator: str | None,
    denominator: str | None,
) -> tuple[str | None, str | None]:
    col1, col2, col3, col4, col5 = st.columns([4, 1, 5, 1, 5], gap=None)
    _metric_text_widget(col1, label)
    _metric_text_widget(col2, "=")
    with col3:
        dlr_bad = _column_selector(
            key=f"{key}_dlr_bad", placeholder="$ Bad Amount", current=numerator
        )
    _metric_text_widget(col4, "/")
    with col5:
        avg_bal = _column_selector(
            key=f"{key}_avg_bal", placeholder="$ Avg Balance", current=denominator
        )
    return dlr_bad, avg_bal


def _mob_selector(key: str, default_mob: int) -> int:
    col1, col2, col3, _ = st.columns([4, 1, 5, 6], gap=None)
    _metric_text_widget(col1, "MOB")
    _metric_text_widget(col2, "=")
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


def bad_rate_config_selector(
    dev_unit_bad_rate: BadRateConfig | None,
    dev_dollar_bad_rate: BadRateConfig | None,
    test_unit_bad_rate: BadRateConfig | None,
    test_dollar_bad_rate: BadRateConfig | None,
) -> BadRateSelection:
    """Render the Target and Early bad rate sections; return all four configs."""

    # --- Target Bad Rates (dev) ---
    st.markdown("#### Target Bad Rates", text_alignment="center")

    dev_ids = dev_unit_bad_rate.data_source_ids if dev_unit_bad_rate is not None else ()
    dev_selected_ids = _data_source_selector("sim_dev_data_sources", dev_ids)

    dev_unt_num = (
        dev_unit_bad_rate.numerator_col if dev_unit_bad_rate is not None else None
    )
    dev_dlr_num = (
        dev_dollar_bad_rate.numerator_col if dev_dollar_bad_rate is not None else None
    )
    dev_dlr_den = (
        dev_dollar_bad_rate.denominator_col if dev_dollar_bad_rate is not None else None
    )
    dev_mob = (
        dev_unit_bad_rate.current_rate_mob if dev_unit_bad_rate is not None else 12
    )

    dev_unt_bad = _unit_bad_rate_row("# Bad Rate", "sim_dev_unt", dev_unt_num)
    dev_dlr_bad, dev_avg_bal = _dollar_bad_rate_row(
        "$ Bad Rate", "sim_dev_dlr", dev_dlr_num, dev_dlr_den
    )
    mob = _mob_selector("sim_dev_mob", dev_mob)

    dev_unit = BadRateConfig(
        loss_rate_type=LossRateTypes.ULR,
        numerator_col=dev_unt_bad,
        denominator_col=None,
        current_rate_mob=mob,
        data_source_ids=dev_selected_ids,
        is_annualized=True,
    )
    dev_dollar = BadRateConfig(
        loss_rate_type=LossRateTypes.DLR,
        numerator_col=dev_dlr_bad,
        denominator_col=dev_avg_bal,
        current_rate_mob=mob,
        data_source_ids=dev_selected_ids,
        is_annualized=True,
    )

    st.info(
        """
        Final annualized bad rates are calculated as: ```'Bad Rate %' * (12 / MOB)```
        """,
        icon=":material/info:",
    )

    # --- Early Bad Rates (test) ---
    st.divider()
    st.markdown("#### Early Bad Rates", text_alignment="center")

    test_ids = (
        test_unit_bad_rate.data_source_ids if test_unit_bad_rate is not None else ()
    )
    test_selected_ids = _data_source_selector("sim_test_data_sources", test_ids)

    test_unt_num = (
        test_unit_bad_rate.numerator_col if test_unit_bad_rate is not None else None
    )
    test_dlr_num = (
        test_dollar_bad_rate.numerator_col if test_dollar_bad_rate is not None else None
    )
    test_dlr_den = (
        test_dollar_bad_rate.denominator_col
        if test_dollar_bad_rate is not None
        else None
    )

    test_unt_bad = _unit_bad_rate_row("# Bad Rate", "sim_test_unt", test_unt_num)
    test_dlr_bad, test_avg_bal = _dollar_bad_rate_row(
        "$ Bad Rate", "sim_test_dlr", test_dlr_num, test_dlr_den
    )

    test_unit = BadRateConfig(
        loss_rate_type=LossRateTypes.ULR,
        numerator_col=test_unt_bad,
        denominator_col=None,
        current_rate_mob=12,
        data_source_ids=test_selected_ids,
        is_annualized=False,
    )
    test_dollar = BadRateConfig(
        loss_rate_type=LossRateTypes.DLR,
        numerator_col=test_dlr_bad,
        denominator_col=test_avg_bal,
        current_rate_mob=12,
        data_source_ids=test_selected_ids,
        is_annualized=False,
    )

    return BadRateSelection(
        dev_unit_bad_rate=dev_unit,
        dev_dollar_bad_rate=dev_dollar,
        test_unit_bad_rate=test_unit,
        test_dollar_bad_rate=test_dollar,
    )


__all__ = ["BadRateSelection", "bad_rate_config_selector"]
