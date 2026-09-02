"""UI component for the Information Value (IV) Analysis section."""

import altair as alt
import pandas as pd
import polars as pl
import streamlit as st

from risc_tool_v2.data.core.utils.logging import get_logger
from risc_tool_v2.ui.core.session import get_session

logger = get_logger(__name__)


def data_source_selector():
    session = get_session()
    data_explorer_vm = session.data_explorer_view_model

    current_data_source_ids = data_explorer_vm.iv_data_sources

    iv_data_sources = st.multiselect(
        label="Select Data Sources",
        options=data_explorer_vm.all_data_source_ids,
        default=current_data_source_ids,
        format_func=data_explorer_vm.get_data_source_label,
        key="select_data_source_ids",
        placeholder="Select Data Sources",
    )

    if set(iv_data_sources) == set(current_data_source_ids):
        return

    logger.debug("User selected data sources for IV: %s", iv_data_sources)
    data_explorer_vm.iv_data_sources = iv_data_sources
    st.rerun()


def iv_bar_chart(dataframe: pd.DataFrame):
    x = alt.X(
        "variable:N",
        sort=alt.EncodingSortField(field="iv", op="max", order="descending"),
        axis=alt.Axis(
            title="Variable",
            labelAngle=0,
        ),
    )

    y = alt.Y(
        "iv:Q",
        axis=alt.Axis(title="Information Value (IV)"),
    )

    tooltip = [
        alt.Tooltip("variable", title="Variable"),
        alt.Tooltip("iv", title="Information Value", format=".2f"),
    ]

    bars = (
        alt.Chart(dataframe).mark_bar(color="#44c1ca").encode(x=x, y=y, tooltip=tooltip)
    )

    text_labels = (
        alt
        .Chart(dataframe)
        .mark_text(
            align="center",
            dy=-15,
            color="white" if st.context.theme.get("type") == "dark" else "black",
        )
        .encode(x=x, y=y, text=alt.Text("iv:Q", format=".2f"))
    )

    chart = (bars + text_labels).configure_axis(grid=False).properties(height=500)  # type: ignore

    return chart


def iv_analysis():
    session = get_session()
    de_view_model = session.data_explorer_view_model

    chart_container, control_container = st.columns([2.5, 1])
    error_container = st.container()

    with control_container:
        data_source_selector()

        available_target_variables = [None] + de_view_model.available_target_columns
        current_target = de_view_model.iv_current_target
        current_target_index = (
            available_target_variables.index(current_target)
            if current_target in available_target_variables
            else 0
        )
        target_variable = st.selectbox(
            label="Target Variable",
            options=available_target_variables,
            index=current_target_index,
        )

        available_input_variables = de_view_model.available_input_columns
        input_variables = st.multiselect(
            label="Variables",
            options=available_input_variables,
            default=de_view_model.iv_current_variables,
        )

        all_filters = de_view_model.all_filters
        filter_ids = st.multiselect(
            label="Filters",
            options=list(all_filters.keys()),
            default=de_view_model.iv_current_filter_ids,
            format_func=lambda filter_uid: all_filters[filter_uid].name,
        )

        remove_outliers = st.checkbox(
            label="Remove Outliers",
            value=de_view_model.iv_remove_outliers,
            help="Remove all outlier instances from calculations",
        )

        if st.button(
            label="Save Config",
            width="stretch",
            type="primary",
            icon=":material/save:",
        ) and any([
            de_view_model.iv_current_target != target_variable,
            de_view_model.iv_current_variables != input_variables,
            de_view_model.iv_current_filter_ids != filter_ids,
            de_view_model.iv_remove_outliers != remove_outliers,
        ]):
            logger.info(
                "User saved IV configuration (target=%s, variables=%d, filters=%d)",
                target_variable,
                len(input_variables),
                len(filter_ids),
            )
            de_view_model.iv_current_target = target_variable
            de_view_model.iv_current_variables = input_variables
            de_view_model.iv_current_filter_ids = filter_ids
            de_view_model.iv_remove_outliers = remove_outliers
            st.rerun()

    with chart_container:
        iv_df: pl.DataFrame | None = de_view_model.get_iv_df(
            target_variable=de_view_model.iv_current_target,
            input_variables=de_view_model.iv_current_variables,
            filter_ids=de_view_model.iv_current_filter_ids,
            remove_outliers=de_view_model.iv_remove_outliers,
        )

        if iv_df is not None:
            pandas_df = iv_df.to_pandas()
            chart = iv_bar_chart(pandas_df)
            st.altair_chart(chart, width="stretch")

    with error_container:
        for error in de_view_model.iv_errors:
            st.error(str(error))

        for warning in de_view_model.iv_warnings:
            st.warning(warning)


__all__ = ["iv_analysis"]
