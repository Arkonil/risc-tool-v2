import typing as t

import streamlit as st
from streamlit.delta_generator import DeltaGenerator
from streamlit.errors import StreamlitAPIException

from risc_tool.data.models.enums import DefaultMetricNames
from risc_tool.data.models.types import ColumnUsage, DataSourceType
from risc_tool.data.session import Session


def metric_text_widget(column: DeltaGenerator, text: str):
    column.html(
        f"""
            <div style="display: flex; justify-content: center; font-size: 1.5em; font-weight: bold;">
                <span>{text}</span>
            </div>
        """
    )


def data_source_selector(ds_type: DataSourceType) -> None:
    session: Session = st.session_state["session"]
    variable_selector_vm = session.variable_selector_view_model

    current_data_source_ids = variable_selector_vm.selected_data_source_ids(ds_type)
    options = variable_selector_vm.all_data_source_ids

    col1, col2, col3 = st.columns([4, 1, 11], gap=None)
    metric_text_widget(col1, "Data Sources")
    metric_text_widget(col2, "=")
    with col3:
        selected_data_source_ids = st.multiselect(
            label="Select Data Sources",
            options=options,
            default=current_data_source_ids,
            format_func=variable_selector_vm.get_data_source_label,
            key=f"select-data-source-ids-{ds_type}",
            width="stretch",
            label_visibility="collapsed",
            placeholder="Select Data Sources",
        )

    if set(selected_data_source_ids) == set(current_data_source_ids):
        return

    variable_selector_vm.set_data_source_ids(ds_type, selected_data_source_ids)

    try:
        st.rerun(scope="fragment")
    except StreamlitAPIException:
        st.rerun()


def column_selector(
    ds_type: DataSourceType,
    usage: ColumnUsage,
) -> None:
    session: Session = st.session_state["session"]
    variable_selector_vm = session.variable_selector_view_model

    options = variable_selector_vm.get_available_columns(ds_type)

    current_column = variable_selector_vm.get_variable(ds_type, usage)
    current_index = options.index(current_column)

    if current_index == 0:
        current_index = None

    if usage == "unt_bad":
        placeholder = r"# Bad Count"
    elif usage == "dlr_bad":
        placeholder = "$ Bad Amount"
    elif usage == "avg_bal":
        placeholder = "$ Avg Balance"
    else:
        placeholder = ""

    selected_column = st.selectbox(
        label=f"var-selector-{ds_type}-{usage}",
        options=options,
        label_visibility="collapsed",
        index=current_index,
        format_func=lambda v: "" if v is None else v,
        placeholder=placeholder,
    )

    if current_column == selected_column:
        return

    variable_selector_vm.set_variable(ds_type, usage, selected_column)

    try:
        st.rerun(scope="fragment")
    except StreamlitAPIException:
        st.rerun()


def mob_selector(mob_type: t.Literal["current", "lifetime"]) -> None:
    session: Session = st.session_state["session"]
    variable_selector_vm = session.variable_selector_view_model

    current_mob = variable_selector_vm.get_mob(mob_type)

    selected_mob = st.number_input(
        label=f"mob_selector_{mob_type}",
        value=current_mob,
        min_value=1,
        max_value=100,
        step=1,
        label_visibility="collapsed",
        format="%d",
        placeholder="Months on Book",
    )

    if current_mob == selected_mob:
        return

    variable_selector_vm.set_mob(mob_type, selected_mob)

    try:
        st.rerun(scope="fragment")
    except StreamlitAPIException:
        st.rerun()


def dev_unt_bad_selector() -> None:
    col1, col2, col3, col4, col5 = st.columns([4, 1, 5, 1, 5], gap=None)
    metric_text_widget(col1, DefaultMetricNames.DEV_UNT_BAD_RATE)
    metric_text_widget(col2, "=")
    with col3:
        column_selector(ds_type="dev", usage="unt_bad")
    metric_text_widget(col4, "/")
    metric_text_widget(col5, "# Accounts")


def tst_unt_bad_selector() -> None:
    col1, col2, col3, col4, col5 = st.columns([4, 1, 5, 1, 5], gap=None)
    metric_text_widget(col1, DefaultMetricNames.TST_UNT_BAD_RATE)
    metric_text_widget(col2, "=")
    with col3:
        column_selector(ds_type="tst", usage="unt_bad")
    metric_text_widget(col4, "/")
    metric_text_widget(col5, "# Accounts")


def dev_dlr_bad_selector() -> None:
    col1, col2, col3, col4, col5 = st.columns([4, 1, 5, 1, 5], gap=None)
    metric_text_widget(col1, DefaultMetricNames.DEV_DLR_BAD_RATE)
    metric_text_widget(col2, "=")
    with col3:
        column_selector(ds_type="dev", usage="dlr_bad")
    metric_text_widget(col4, "/")
    with col5:
        column_selector(ds_type="dev", usage="avg_bal")


def tst_dlr_bad_selector() -> None:
    col1, col2, col3, col4, col5 = st.columns([4, 1, 5, 1, 5], gap=None)
    metric_text_widget(col1, DefaultMetricNames.TST_DLR_BAD_RATE)
    metric_text_widget(col2, "=")
    with col3:
        column_selector(ds_type="tst", usage="dlr_bad")
    metric_text_widget(col4, "/")
    with col5:
        column_selector(ds_type="tst", usage="avg_bal")


def current_mob_selector() -> None:
    col1, col2, col3, _ = st.columns([4, 1, 5, 6], gap=None)
    metric_text_widget(col1, "MOB")
    metric_text_widget(col2, "=")
    with col3:
        mob_selector("current")


def lifetime_mob_selector() -> None:
    col1, col2, col3, _ = st.columns([4, 1, 5, 6], gap=None)
    metric_text_widget(col1, "Lifetime MOB")
    metric_text_widget(col2, "=")
    with col3:
        mob_selector("lifetime")


def variable_selector():
    st.markdown("#### Target Bad Rates", text_alignment="center")

    data_source_selector("dev")
    dev_unt_bad_selector()
    dev_dlr_bad_selector()
    current_mob_selector()
    lifetime_mob_selector()

    st.info(
        """
        Final annualized bad rates are calculated as: ```'Bad Rate %' * (12 / MOB)```
        """,
        icon=":material/info:",
    )

    st.divider()
    st.markdown("#### Early Bad Rates", text_alignment="center")

    data_source_selector("tst")
    tst_unt_bad_selector()
    tst_dlr_bad_selector()


@st.dialog("Set Variables", width="large", on_dismiss="rerun")
def variable_selector_dialog():
    with st.container(border=True):
        variable_selector()

    _, col = st.columns(2)

    with col:
        if st.button("Submit", type="primary", width="stretch"):
            st.rerun()


__all__ = ["variable_selector", "variable_selector_dialog"]
