"""UI components for the Filter Editor page in the Filters module.

Provides Streamlit widgets for editing filter names and queries, including
a code editor with autocomplete, pie chart preview, and quick reference docs.
"""

import math

import altair as alt
import pandas as pd
import streamlit as st

from risc_tool.data.models.asset_path import AssetPath
from risc_tool.data.models.completion import Completion
from risc_tool.data.models.filter import Filter
from risc_tool.data.session import Session
from risc_tool.ui.components.query_editor import query_editor
from risc_tool.utils.logging import get_logger

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
    """Render a button that navigates back to the filter list view.

    When clicked, switches the view model to "view" mode and triggers a rerun.
    """
    session: Session = st.session_state["session"]
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
    """Render sidebar widgets for the filter editor.

    Currently displays a link to the Polars expression documentation.
    """
    st.link_button(
        label="Polars Documentation",
        url="https://docs.pola.rs/user-guide/expressions/",
        icon=":material/open_in_new:",
    )


def filter_name_selector(current_name: str) -> str:
    """Render a text input for editing the filter name.

    Args:
        current_name: The current name value to display.

    Returns:
        The user-edited filter name string.
    """
    edited_name = st.text_input(
        label="Filter Name",
        value=current_name,
        label_visibility="collapsed",
        placeholder="Filter Name",
    )
    return edited_name


def pie_chart_widget(filter_obj: Filter | None):
    """Render a donut pie chart showing the true/false ratio of the filter.

    Args:
        filter_obj: The Filter object with a compiled filter_expr to evaluate.
            If None or lacking a filter_expr, nothing is rendered.
    """
    if filter_obj is None or filter_obj.filter_expr is None:
        return

    session: Session = st.session_state["session"]
    filter_editor_vm = session.filter_editor_view_model
    lf = filter_editor_vm.lazyframe

    try:
        counts_df = lf.select(
            [
                filter_obj.filter_expr.sum().alias("True"),
                (~filter_obj.filter_expr).sum().alias("False"),
            ]
        ).collect()

        satisfies = counts_df.item(0, "True")
        not_satisfies = counts_df.item(0, "False")

        counts = pd.DataFrame(
            {
                "Condition Satisfies": ["True", "False"],
                "Count": [satisfies, not_satisfies],
            }
        )

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


def quick_reference_widget():
    """Render an expandable quick reference section for filter query syntax."""
    with open(AssetPath.FILTER_QUERY_REFERENCE) as fp:
        text = fp.read()

    with st.expander("Quick Reference"):
        st.markdown(text, unsafe_allow_html=True)


def on_save():
    """Callback for the Save button that persists the verified filter.

    Catches RuntimeError from the view model and displays a toast notification.
    """
    session: Session = st.session_state["session"]
    filter_editor_vm = session.filter_editor_view_model

    try:
        filter_editor_vm.save_filter()
    except RuntimeError as e:
        logger.exception("Save filter failed with RuntimeError")
        st.toast(body=f"RuntimeError: {e}", icon=":material/error:")


def filter_editor():
    """Render the Filter Editor page with code editor, controls, and preview.

    Displays a code editor with autocomplete for column names and math
    functions, a verify button, a pie chart preview of filter results,
    a save button, error messages, and a quick reference expandable section.
    """
    session: Session = st.session_state["session"]
    filter_editor_vm = session.filter_editor_view_model

    with st.sidebar:
        sidebar_widgets()

    back_button()

    st.title("Create Filter")

    code_editor_container, controller_container = st.columns([2.5, 1])
    error_container = st.container()

    # Code Completions
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

    # Code Editor
    with code_editor_container:
        edited_name = filter_name_selector(filter_editor_vm.filter_cache.name)
        edited_query = query_editor(filter_editor_vm.filter_cache.query, completions)

        if edited_query["text"] == "":
            edited_query["text"] = filter_editor_vm.filter_cache.query

    # Controls
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

    quick_reference_widget()


__all__ = ["filter_editor"]
