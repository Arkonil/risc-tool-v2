"""Metric editor UI with code editor, template builder, and format controls."""

import hashlib
import typing as t

import streamlit as st

from risc_tool.data.models.asset_path import AssetPath
from risc_tool.data.models.completion import Completion
from risc_tool.data.models.enums import MetricTemplates
from risc_tool.data.models.metric import MetricQueryValidator
from risc_tool.data.session import Session
from risc_tool.ui.components.query_editor import query_editor


def back_button():
    """Render a back button that returns to the metric list view."""
    session: Session = st.session_state["session"]
    metric_editor_vm = session.metric_editor_view_model

    if st.button(
        label="Back",
        icon=":material/arrow_back_ios:",
        type="primary",
    ):
        metric_editor_vm.set_mode("view")
        st.rerun()


def data_source_selector():
    """Render a multiselect widget for choosing the metric's data sources."""
    session: Session = st.session_state["session"]
    metric_editor_vm = session.metric_editor_view_model

    current_data_source_ids = metric_editor_vm.metric_cache.data_source_ids

    selected_data_source_ids = st.multiselect(
        label="Select Data Sources",
        options=metric_editor_vm.all_data_source_ids,
        default=current_data_source_ids,
        format_func=metric_editor_vm.get_data_source_label,
        key="select_data_source_ids",
        width="stretch",
        label_visibility="collapsed",
        placeholder="Select Data Sources",
    )

    if set(selected_data_source_ids) == set(current_data_source_ids):
        return

    metric_editor_vm.selected_data_source_ids = selected_data_source_ids
    st.rerun()


def metric_name_selector(current_name: str):
    """Render a text input for the metric name.

    Args:
        current_name: The current metric name.

    Returns:
        The edited metric name.
    """
    edited_name = st.text_input(
        label="Metric Name",
        value=current_name,
        label_visibility="collapsed",
        placeholder="Metric Name",
    )
    return edited_name


def format_display(use_thousand_sep: bool, is_percentage: bool, decimal_places: int):
    """Render a format preview showing an example value transformation.

    Args:
        use_thousand_sep: Whether thousand separators are used.
        is_percentage: Whether the value is formatted as a percentage.
        decimal_places: Number of decimal places to display.
    """
    with st.container(horizontal=True, vertical_alignment="center"):
        original_value = (
            st.text_input(
                label="Original Value",
                value="1234.567",
                label_visibility="collapsed",
            )
            or ""
        )

        try:
            original_value = float(original_value.strip())
        except ValueError:
            original_value = 1234.567

        st.image(AssetPath.ARROW_RIGHT)

        formatter = f"{{:{',' if use_thousand_sep else ''}.{decimal_places}f}}{'%' if is_percentage else ''}"
        st.text_input(
            label="Transformed Value",
            value=formatter.format(
                original_value * 100 if is_percentage else original_value
            ),
            disabled=True,
            label_visibility="collapsed",
        )


def format_selector():
    """Render checkboxes and inputs for configuring the metric display format."""
    session: Session = st.session_state["session"]
    mc = session.metric_editor_view_model

    st.markdown("##### Metric Format:")

    is_cumulative = st.checkbox(
        "Is Cumulative",
        value=mc.metric_cache.is_cumulative,
        help="Calculate the metric cumulatively across groups.",
    )

    if is_cumulative != mc.metric_cache.is_cumulative:
        mc.set_metric_property(is_cumulative=is_cumulative)
        st.rerun()

    use_thousand_sep = st.checkbox(
        "Use Thousand Separator",
        value=mc.metric_cache.use_thousand_sep,
        help="Format numbers with a comma as a thousand separator (e.g., 1,000).",
    )

    if use_thousand_sep != mc.metric_cache.use_thousand_sep:
        mc.set_metric_property(use_thousand_sep=use_thousand_sep)
        st.rerun()

    is_percentage = st.checkbox(
        "Is Percentage",
        value=mc.metric_cache.is_percentage,
        help="Format the metric as a percentage (e.g., 50%).",
    )

    if is_percentage != mc.metric_cache.is_percentage:
        mc.set_metric_property(is_percentage=is_percentage)
        st.rerun()

    decimal_places = st.number_input(
        "Decimal Places",
        min_value=0,
        value=mc.metric_cache.decimal_places,
        help="Number of decimal places to display for the metric.",
    )

    if decimal_places != mc.metric_cache.decimal_places:
        mc.set_metric_property(decimal_places=decimal_places)
        st.rerun()

    with st.container(border=True):
        st.markdown("##### Format Preview:")
        format_display(
            use_thousand_sep,
            is_percentage,
            decimal_places,
        )


def on_save():
    """Save the verified metric and notify on errors."""
    session: Session = st.session_state["session"]
    metric_editor_vm = session.metric_editor_view_model

    try:
        metric_editor_vm.save_metric()
    except RuntimeError as e:
        st.toast(body=f"RuntimeError: {e}", icon=":material/error:")


def format_value_str(val: str):
    """Escape and quote a string value for use in a query literal.

    Args:
        val: The raw value.

    Returns:
        A double-quoted, escaped string literal.
    """
    val_str = str(val).replace('"', '\\"')
    return f'"{val_str}"'


def template_builder() -> dict[str, str]:
    """Render template widgets and generate a query from the selections.

    Returns:
        A dict with the generated "text" query and its "id" hash.
    """
    session: Session = st.session_state["session"]
    metric_editor_vm = session.metric_editor_view_model

    if "metric_template_state" not in st.session_state:
        st.session_state["metric_template_state"] = {
            "template": MetricTemplates.VOLUME,
            "last_generated_query": "",
            MetricTemplates.VOLUME: "Default (no column)",
            MetricTemplates.APPROVAL_RATE: {"a": None, "b": [], "c": []},
            MetricTemplates.OVERALL_APPROVAL_RATE: {"a": None, "b": []},
            MetricTemplates.DLR_BAD_RATE: {"a": None, "b": None},
            MetricTemplates.UNT_BAD_RATE: {"a": None},
        }

    state = st.session_state["metric_template_state"]
    current_query = metric_editor_vm.metric_cache.query

    # Reset state if the query was modified externally (in Code Editor)
    if state["last_generated_query"] and current_query != state["last_generated_query"]:
        state[MetricTemplates.VOLUME] = "Default (no column)"
        state[MetricTemplates.APPROVAL_RATE] = {"a": None, "b": [], "c": []}
        state[MetricTemplates.OVERALL_APPROVAL_RATE] = {"a": None, "b": []}
        state[MetricTemplates.DLR_BAD_RATE] = {"a": None, "b": None}
        state[MetricTemplates.UNT_BAD_RATE] = {"a": None}

    template = st.selectbox(
        label="Select Template",
        options=list(MetricTemplates),
        index=list(MetricTemplates).index(state["template"]),
        key="template_builder_selector",
    )
    state["template"] = template

    # Extract completions
    completions = metric_editor_vm.get_column_completions()
    columns = [c.value for c in completions if c.meta != "function"]

    def get_index(val: t.Any, options: t.Sequence[t.Any]) -> int | None:
        """Get the index of a value in options, or None if absent.

        Args:
            val: The value to look up.
            options: The sequence of options.

        Returns:
            The index, or None if not present.
        """
        return options.index(val) if val in options else None

    query_text = ""

    if template == MetricTemplates.VOLUME:
        volume_options = ["Default (no column)"] + columns
        saved_vol_col = state.get(MetricTemplates.VOLUME, "Default (no column)")
        vol_col = st.selectbox(
            "Column",
            options=volume_options,
            index=volume_options.index(saved_vol_col) if saved_vol_col in volume_options else 0,
            key="volume_column",
            placeholder="Select a column for Volume",
        )
        state[MetricTemplates.VOLUME] = vol_col
        if vol_col == "Default (no column)":
            query_text = "__MISSING__"
        else:
            query_text = f"`{vol_col}`.size"

    elif template == MetricTemplates.APPROVAL_RATE:
        col1, col2, col3 = st.columns(3)
        a = col1.selectbox(
            "Application Status",
            options=columns,
            index=get_index(state[MetricTemplates.APPROVAL_RATE]["a"], columns),
            key="approval_a",
            placeholder="Select a column for Application Status",
        )
        state[MetricTemplates.APPROVAL_RATE]["a"] = a

        unique_vals = metric_editor_vm.get_unique_values(a) if a else []
        for v in (
            state[MetricTemplates.APPROVAL_RATE]["b"]
            + state[MetricTemplates.APPROVAL_RATE]["c"]
        ):
            if v not in unique_vals:
                unique_vals.append(v)

        b = col2.multiselect(
            "Values for Approved",
            options=unique_vals,
            default=[val for val in state[MetricTemplates.APPROVAL_RATE]["b"]],
            key="approval_b",
            placeholder="Select or enter values for Approved",
        )
        state[MetricTemplates.APPROVAL_RATE]["b"] = b

        c = col3.multiselect(
            "Values for Declined",
            options=unique_vals,
            default=[val for val in state[MetricTemplates.APPROVAL_RATE]["c"]],
            key="approval_c",
            placeholder="Select or enter values for Declined",
        )
        state[MetricTemplates.APPROVAL_RATE]["c"] = c

        b_list_str = "[" + ", ".join(format_value_str(v) for v in b) + "]"
        bc_list_str = "[" + ", ".join(format_value_str(v) for v in b + c) + "]"
        query_text = f"(`{a or ''}`.isin({b_list_str}).sum() / `{a or ''}`.isin({bc_list_str}).sum())"

    elif template == MetricTemplates.OVERALL_APPROVAL_RATE:
        col1, col2 = st.columns(2)
        a = col1.selectbox(
            "Application Status",
            options=columns,
            index=get_index(state[MetricTemplates.OVERALL_APPROVAL_RATE]["a"], columns),
            key="approval_a",
            placeholder="Select a column for Application Status",
        )
        state[MetricTemplates.OVERALL_APPROVAL_RATE]["a"] = a

        unique_vals = metric_editor_vm.get_unique_values(a) if a else []
        for v in state[MetricTemplates.OVERALL_APPROVAL_RATE]["b"]:
            if v not in unique_vals:
                unique_vals.append(v)

        b = col2.multiselect(
            "Values for Approved",
            options=unique_vals,
            default=[val for val in state[MetricTemplates.OVERALL_APPROVAL_RATE]["b"]],
            key="approval_b",
            placeholder="Select or enter values for Approved",
        )
        state[MetricTemplates.OVERALL_APPROVAL_RATE]["b"] = b

        b_list_str = "[" + ", ".join(format_value_str(v) for v in b) + "]"
        query_text = f"(`{a or ''}`.isin({b_list_str}).sum() / __TOTAL_SIZE__)"

    elif template == MetricTemplates.DLR_BAD_RATE:
        col1, col2 = st.columns(2)
        a = col1.selectbox(
            "Numerator",
            options=columns,
            index=get_index(state[MetricTemplates.DLR_BAD_RATE]["a"], columns),
            key="bad_rate_a",
            placeholder="Select a column for Numerator",
        )
        state[MetricTemplates.DLR_BAD_RATE]["a"] = a

        b = col2.selectbox(
            "Denominator",
            options=columns,
            index=get_index(state[MetricTemplates.DLR_BAD_RATE]["b"], columns),
            key="bad_rate_b",
            placeholder="Select a column for Denominator",
        )
        state[MetricTemplates.DLR_BAD_RATE]["b"] = b

        query_text = f"(`{a or ''}`.sum() / `{b or ''}`.sum())"

    elif template == MetricTemplates.UNT_BAD_RATE:
        a = st.selectbox(
            "Numerator",
            options=columns,
            index=get_index(state[MetricTemplates.UNT_BAD_RATE]["a"], columns),
            key="number_bad_rate_a",
            placeholder="Select a column for Numerator",
        )
        state[MetricTemplates.UNT_BAD_RATE]["a"] = a

        query_text = f"(`{a or ''}`.sum() / `{a or ''}`.size)"

    st.code(query_text, language="python")

    # We update the session state variable
    state["last_generated_query"] = query_text

    if query_text and query_text != current_query:
        metric_editor_vm.set_metric_property(query=query_text)

    return {
        "text": query_text,
        "id": hashlib.md5(query_text.encode()).hexdigest() if query_text else "",
    }


def metric_editor():
    """Render the full metric editor page."""
    session: Session = st.session_state["session"]
    metric_editor_vm = session.metric_editor_view_model

    back_button()

    st.title("Metric Editor")

    code_editor_container, controller_container = st.columns([2.5, 1])
    error_container = st.container()

    # Code Completions
    completions = metric_editor_vm.get_column_completions()
    for f in (
        MetricQueryValidator.allowed_functions
        | MetricQueryValidator.allowed_series_methods
    ):
        completions.append(
            Completion(
                caption=f,
                value=f,
                meta="function",
                name=f,
                score=100,
            )
        )
    completions = [comp.to_dict() for comp in completions]

    # Code Editor
    with code_editor_container:
        data_source_selector()

        edited_name = metric_name_selector(metric_editor_vm.metric_cache.name)

        editor_mode = st.radio(
            "Editor Mode",
            options=["Code Editor", "Template Builder"],
            horizontal=True,
            label_visibility="collapsed",
        )

        if editor_mode == "Code Editor":
            edited_query = query_editor(
                metric_editor_vm.metric_cache.query, completions
            )

            if edited_query["text"] == "":
                edited_query["text"] = metric_editor_vm.metric_cache.query
        else:
            edited_query = template_builder()

    # Controls
    with controller_container:

        def on_verify():
            """Trigger validation of the metric in the editor."""
            metric_editor_vm.validate_metric(
                edited_name, edited_query["text"], edited_query["id"]
            )

        format_selector()

        st.button(
            label="Verify",
            type="secondary",
            icon=":material/check:",
            width="stretch",
            on_click=on_verify,
        )

        disabled_save_button: bool = (
            not metric_editor_vm.is_verified
            or (
                edited_query["id"] != ""
                and edited_query["id"] != metric_editor_vm.latest_editor_id
            )
            or (edited_name != metric_editor_vm.metric_cache.name)
        )

        st.button(
            label="Save",
            type="primary",
            icon=":material/save:",
            width="stretch",
            on_click=on_save,
            disabled=disabled_save_button,
        )

    if error_message := metric_editor_vm.error_message():
        error_container.error(error_message)
    else:
        with error_container.expander(label="Metric Object", expanded=False):
            st.write(metric_editor_vm.metric_cache)


__all__ = ["metric_editor"]
