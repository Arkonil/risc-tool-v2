"""Pivot tab view for summary dashboard."""

import typing as t

import pandas as pd
import streamlit as st
from streamlit.components.v2 import component as custom_component
from streamlit_sortables import sort_items  # type: ignore

from risc_tool.data.models.enums import RowIndex
from risc_tool.data.models.metric import Metric
from risc_tool.data.models.types import IterationID
from risc_tool.data.session import Session
from risc_tool.ui.components.filter_selector import filter_selector
from risc_tool.ui.components.metric_selector import metric_selector_button

PIVOT_TABLE_CSS = """
    .pivot-grid {
        font-family: var(--st-font);
        overflow-x: auto;
    }

    .pivot-table {
        width: 100%;
        border-collapse: collapse;
        background: var(--st-background-color);
        border: 1px solid var(--st-dataframe-border-color);
        border-radius: var(--st-base-radius);
        overflow: hidden;
    }

    .pivot-table th, .pivot-table td.pivot-lbl {
        background: var(--st-dataframe-header-background-color);
        color: var(--st-text-color);
        font-weight: 600;
        padding: 0.75rem 1rem;
        text-align: center;
        border-bottom: 1px solid var(--st-dataframe-border-color);
        font-size: var(--st-base-font-size);
    }

    .pivot-table td {
        padding: 0.75rem 1rem;
        border-bottom: 1px solid var(--st-dataframe-border-color);
        color: var(--st-text-color);
        font-size: var(--st-base-font-size);
        text-align: right;
    }

    .pivot-table tr:last-child td {
        border-bottom: none;
    }

    .pivot-table tr:hover {
        background: var(--st-secondary-background-color);
    }

    .pivot-total {
        font-weight: bold;
        background-color: var(--st-secondary-background-color);
        color: var(--text-color, #31333F);
    }
"""

PIVOT_TABLE_JS = """
export default function renderPivotTable(component) {
    const { data, parentElement } = component;
    const root = parentElement.querySelector('[data-testid="pivot-table-root"]');

    if (!root) {
        return;
    }

    root.innerHTML = data?.table_html ?? "";
}
"""

PIVOT_TABLE_COMPONENT = custom_component(
    name="pivot_table_component",
    html="""
    <div data-testid="pivot-table-root"></div>
    """,
    css=PIVOT_TABLE_CSS,
    js=PIVOT_TABLE_JS,
    isolate_styles=True,
)


def render_html_table(
    df: pd.DataFrame,
    row_names: list[str],
    col_names: list[str],
    metric: Metric,
    key: str | None = None,
) -> None:
    """Render a single hierarchical pivot table using Custom Component v2."""
    html: list[str] = []
    html.append('<div class="pivot-grid">')
    html.append('<table class="pivot-table">')

    R = len(row_names)
    C = len(col_names)

    # Thead
    html.append("<thead>")
    if C > 0:
        for c_idx in range(C):
            html.append("<tr>")
            if c_idx == C - 1 and R > 0:
                for r_name in row_names:
                    html.append(f'<th class="pivot-lbl">{r_name}</th>')
            elif R > 0:
                html.append(f'<th colspan="{R}" class="pivot-lbl"></th>')

            spans: list[tuple[str, int]] = []
            current_val = None
            span_count = 0

            for col_tuple in df.columns:
                val = col_tuple[c_idx] if isinstance(col_tuple, tuple) else col_tuple
                val_str = (
                    "Total"
                    if val == RowIndex.TOTAL
                    else ("(Blank)" if pd.isna(val) else str(val))
                )

                if current_val is None:
                    current_val = val_str
                    span_count = 1
                elif val_str == current_val:
                    span_count += 1
                else:
                    spans.append((current_val, span_count))
                    current_val = val_str
                    span_count = 1

            if span_count > 0 and current_val is not None:
                spans.append((current_val, span_count))

            for val_str, count in spans:
                cls_str = ' class="pivot-total"' if val_str == "Total" else ""
                html.append(f'<th colspan="{count}"{cls_str}>{val_str}</th>')
            html.append("</tr>")
    else:
        html.append("<tr>")
        for r in row_names:
            html.append(f'<th class="pivot-lbl">{r}</th>')
        html.append(f"<th>{metric.pretty_name}</th>")
        html.append("</tr>")
    html.append("</thead>")

    # Tbody
    html.append("<tbody>")
    prev_r_tuple = None
    for r_idx, row_obj in df.iterrows():
        if isinstance(r_idx, tuple):
            r_tuple = t.cast(tuple[t.Hashable, ...], r_idx)
        else:
            r_tuple = (r_idx,)

        is_row_total = any(x == RowIndex.TOTAL for x in r_tuple)

        html.append("<tr>")

        if R > 0:
            for level_idx, val in enumerate(r_tuple):
                val_str = (
                    "Total"
                    if val == RowIndex.TOTAL
                    else ("(Blank)" if pd.isna(val) else str(val))  # type: ignore
                )

                show_val = True
                if prev_r_tuple is not None and (
                    prev_r_tuple[: level_idx + 1] == r_tuple[: level_idx + 1]
                    and val != RowIndex.TOTAL
                ):
                    show_val = False

                display_str = val_str if show_val else ""
                cls = "pivot-total pivot-lbl" if val == RowIndex.TOTAL else "pivot-lbl"
                html.append(f'<td class="{cls}">{display_str}</td>')

        prev_r_tuple = r_tuple

        for col_name in df.columns:
            val = row_obj[col_name]
            is_col_total = False
            if isinstance(col_name, tuple):
                is_col_total = any(x == RowIndex.TOTAL for x in col_name)
            elif col_name == RowIndex.TOTAL:
                is_col_total = True

            fmt_val = val if isinstance(val, str) else "-"
            cls_str = "pivot-total" if (is_row_total or is_col_total) else ""
            html.append(f'<td class="{cls_str}">{fmt_val}</td>')

        html.append("</tr>")

    html.append("</tbody>")
    html.append("</table>")
    html.append("</div>")

    html_str = "".join(html)

    st.subheader(metric.pretty_name)
    PIVOT_TABLE_COMPONENT(
        data={"table_html": html_str},
        key=key or str(metric.uid),
    )


def sidebar_widgets() -> None:
    """Render sidebar control widgets for Pivot tab."""
    session: Session = st.session_state["session"]
    summary_vm = session.summary_view_model

    # Metric Selection
    metric_selector_button(
        current_metrics=summary_vm.pv_metric_ids,
        set_metrics=summary_vm.set_pivot_metrics,
    )

    # Filter Selection
    current_filter_ids = summary_vm.pv_filter_ids

    selected_filter_ids = filter_selector(
        key="summary-pivot-filter-selector",
        filter_ids=current_filter_ids,
    )

    if set(selected_filter_ids) != set(current_filter_ids):
        summary_vm.pv_filter_ids = selected_filter_ids
        st.rerun()

    # Outlier Toggle
    current_remove_outliers = summary_vm.pv_remove_outliers

    remove_outliers = st.checkbox(
        label="Remove Outliers",
        value=current_remove_outliers,
        help="Remove Outliers",
    )

    if remove_outliers != current_remove_outliers:
        summary_vm.pv_remove_outliers = remove_outliers
        st.rerun()

    # Scalar Toggle (Disabled)
    st.checkbox(
        label="Enable Scalars",
        value=False,
        help="Use Scalars for Annualized Write Off Rates",
        disabled=True,
    )


def pivot() -> None:
    """Render main Pivot tab content."""
    session: Session = st.session_state["session"]
    summary_vm = session.summary_view_model

    with st.sidebar:
        sidebar_widgets()

    col_table, col_controls = st.columns([3, 1])

    row_key_slug = "_".join(str(v) for v in summary_vm.pv_row_vars)
    col_key_slug = "_".join(str(v) for v in summary_vm.pv_col_vars)

    with col_controls:
        st.markdown("##### Variables")
        available_vars = summary_vm.pivot_variables
        var_keys = list(available_vars.keys())

        def format_var(x: str | tuple[IterationID, bool]) -> str:
            return available_vars.get(x, str(x))

        selected_row_vars = st.multiselect(
            "Row Variables",
            options=var_keys,
            default=[v for v in summary_vm.pv_row_vars if v in var_keys],
            format_func=format_var,
            key="pv_row_vars_multiselect",
        )
        if selected_row_vars != summary_vm.pv_row_vars:
            summary_vm.pv_row_vars = selected_row_vars
            st.rerun()

        selected_col_vars = st.multiselect(
            "Column Variables",
            options=var_keys,
            default=[v for v in summary_vm.pv_col_vars if v in var_keys],
            format_func=format_var,
            key="pv_col_vars_multiselect",
        )
        if selected_col_vars != summary_vm.pv_col_vars:
            summary_vm.pv_col_vars = selected_col_vars
            st.rerun()

        if summary_vm.pv_row_vars and len(summary_vm.pv_row_vars) > 1:
            st.markdown("##### Order Rows")
            ordered_rows = sort_items(
                items=[
                    available_vars[v]
                    for v in summary_vm.pv_row_vars
                    if v in available_vars
                ],
                key=f"pv_row_sort_{row_key_slug}",
            )
            new_row_vars = [
                summary_vm.pv_row_vars[
                    [
                        available_vars[v]
                        for v in summary_vm.pv_row_vars
                        if v in available_vars
                    ].index(n)
                ]
                for n in ordered_rows
                if n
                in [
                    available_vars[v]
                    for v in summary_vm.pv_row_vars
                    if v in available_vars
                ]
            ]
            if new_row_vars != summary_vm.pv_row_vars:
                summary_vm.pv_row_vars = new_row_vars
                st.rerun()

        if summary_vm.pv_col_vars and len(summary_vm.pv_col_vars) > 1:
            st.markdown("##### Order Columns")
            ordered_cols = sort_items(
                items=[
                    available_vars[v]
                    for v in summary_vm.pv_col_vars
                    if v in available_vars
                ],
                key=f"pv_col_sort_{col_key_slug}",
            )
            new_col_vars = [
                summary_vm.pv_col_vars[
                    [
                        available_vars[v]
                        for v in summary_vm.pv_col_vars
                        if v in available_vars
                    ].index(n)
                ]
                for n in ordered_cols
                if n
                in [
                    available_vars[v]
                    for v in summary_vm.pv_col_vars
                    if v in available_vars
                ]
            ]
            if new_col_vars != summary_vm.pv_col_vars:
                summary_vm.pv_col_vars = new_col_vars
                st.rerun()

    with col_table:
        pivot_dfs = summary_vm.get_pivot_tables()

        if not pivot_dfs:
            st.info("Select row variables and metrics to display in the table")
            return

        for df, mid in zip(pivot_dfs, summary_vm.pv_metric_ids):
            table_key = f"pv_table_{mid}_{row_key_slug}_{col_key_slug}"
            render_html_table(
                df,
                list(map(str, df.index.names)),
                list(map(str, df.columns.names)),
                summary_vm.get_metric(mid),
                key=table_key,
            )


__all__ = ["pivot"]
