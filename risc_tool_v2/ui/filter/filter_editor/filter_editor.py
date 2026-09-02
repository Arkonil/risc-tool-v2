"""UI components for the Filter Editor page in the Filters module."""

import math

import altair as alt
import pandas as pd
import streamlit as st

from risc_tool_v2.data.core.utils.logging import get_logger
from risc_tool_v2.data.data_source.models.completion import Completion
from risc_tool_v2.data.filter.models.filter import Filter
from risc_tool_v2.ui.core.components.query_editor import query_editor
from risc_tool_v2.ui.core.session import get_session

logger = get_logger(__name__)

math_functions = [
    "sin",
    "cos",
    "exp",
    "log",
    "expm1",
    "log1p",
    "sqrt",
    "sinh",
    "cosh",
    "tanh",
    "arcsin",
    "arccos",
    "arctan",
    "arccosh",
    "arcsinh",
    "arctanh",
    "abs",
    "arctan2",
    "log10",
]


def back_button():
    session = get_session()
    filter_editor_vm = session.filter_editor_view_model

    if st.button(
        label="Back",
        icon=":material/arrow_back_ios:",
        type="primary",
    ):
        logger.debug("User navigated back from filter editor to list view")
        filter_editor_vm.set_mode("view")
        st.rerun()


def sidebar_widgets():
    st.link_button(
        label="Polars Documentation",
        url="https://docs.pola.rs/user-guide/expressions/",
        icon=":material/open_in_new:",
    )


def filter_name_selector(current_name: str) -> str:
    edited_name = st.text_input(
        label="Filter Name",
        value=current_name,
        label_visibility="collapsed",
        placeholder="Filter Name",
    )
    return edited_name


def pie_chart_widget(filter_obj: Filter | None):
    if filter_obj is None or filter_obj.filter_expr is None:
        return

    session = get_session()
    filter_editor_vm = session.filter_editor_view_model
    lf = filter_editor_vm.lazyframe

    try:
        counts_df = lf.select([
            filter_obj.filter_expr.sum().alias("True"),
            (~filter_obj.filter_expr).sum().alias("False"),
        ]).collect()

        satisfies = counts_df.item(0, "True")
        not_satisfies = counts_df.item(0, "False")

        counts = pd.DataFrame({
            "Condition Satisfies": ["True", "False"],
            "Count": [satisfies, not_satisfies],
        })

    except Exception as e:
        logger.exception("Failed to calculate distribution chart")
        st.error(f"Failed to calculate distribution chart: {e}")
        return

    base_chart = alt.Chart(counts).encode(
        theta=alt.Theta(field="Count", type="quantitative").stack(True),
        color=alt.Color(field="Condition Satisfies", type="nominal"),
    )

    pie_chart = base_chart.mark_arc(
        outerRadius=80,
        innerRadius=40,
        cornerRadius=3,
        padAngle=0.04,
        thetaOffset=-math.pi / 2,
    )

    legends = base_chart.mark_text(
        outerRadius=115,
        size=16,
        thetaOffset=-math.pi / 2,
    ).encode(text=alt.Text(field="Count", type="quantitative", format=","))

    chart = pie_chart + legends
    st.altair_chart(chart, width="stretch")


def on_save():
    session = get_session()
    filter_editor_vm = session.filter_editor_view_model

    try:
        filter_editor_vm.save_filter()
    except RuntimeError as e:
        logger.exception("Save filter failed with RuntimeError")
        st.toast(body=f"RuntimeError: {e}", icon=":material/error:")


def filter_editor():
    session = get_session()
    filter_editor_vm = session.filter_editor_view_model

    with st.sidebar:
        sidebar_widgets()

    back_button()

    st.title("Create Filter")

    code_editor_container, controller_container = st.columns([2.5, 1])
    error_container = st.container()

    def format_completion(col_name: str):
        return Completion(
            caption=col_name,
            value=col_name,
            meta="Column",
            name=col_name,
            score=100,
        )

    completions = filter_editor_vm.get_column_completions()
    completions += list(map(format_completion, math_functions))
    completions = [comp.to_dict() for comp in completions]

    with code_editor_container:
        edited_name = filter_name_selector(filter_editor_vm.filter_cache.name)
        edited_query = query_editor(filter_editor_vm.filter_cache.query, completions)

        if edited_query["text"] == "":
            edited_query["text"] = filter_editor_vm.filter_cache.query

    with controller_container:

        def on_verify():
            filter_editor_vm.validate_filter(
                name=edited_name,
                query=edited_query["text"],
                latest_editor_id=edited_query["id"],
            )

        st.button(
            label="Verify",
            type="secondary",
            icon=":material/check:",
            width="stretch",
            on_click=on_verify,
        )

        pie_chart_widget(filter_editor_vm.filter_cache)

        disabled_save_button: bool = (
            not filter_editor_vm.is_verified
            or (
                edited_query["id"] != ""
                and edited_query["id"] != filter_editor_vm.latest_editor_id
            )
            or (edited_name != filter_editor_vm.filter_cache.name)
        )

        st.button(
            label="Save",
            type="primary",
            icon=":material/save:",
            width="stretch",
            on_click=on_save,
            disabled=disabled_save_button,
        )

    if error_message := filter_editor_vm.error_message():
        error_container.error(error_message)
    else:
        with error_container.expander(label="Filter Object", expanded=False):
            st.write(filter_editor_vm.filter_cache)


__all__ = ["filter_editor"]
