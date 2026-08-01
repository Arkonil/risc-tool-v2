"""Iteration metric table UI component displaying preconfigured Styler in st.data_editor."""

import typing as t

import pandas as pd
import streamlit as st

from risc_tool.data.models.enums import RangeColumn, RowIndex
from risc_tool.data.models.types import FilterID, IterationID, MetricID
from risc_tool.data.session import Session
from risc_tool.ui.components.error_warnings import error_and_warning_widget
from risc_tool.ui.components.theme_detector import get_theme


def iteration_metric_table(
    iteration_id: IterationID,
    default: bool,
    show_controls: bool,
    filter_ids: list[FilterID],
    metric_ids: list[MetricID],
    scalars_enabled: bool,
    remove_outliers: bool,
    editable: bool,
    key: str,
) -> None:
    session: Session = st.session_state["session"]
    iterations_vm = session.iterations_view_model

    key_name = f"edited_range-{key}-{iteration_id}"

    final_df_styled, errors, warnings = iterations_vm.get_iteration_metric_table(
        iteration_id=iteration_id,
        default=default,
        show_controls=show_controls,
        filter_ids=filter_ids,
        metric_ids=metric_ids,
        scalars_enabled=scalars_enabled,
        remove_outliers=remove_outliers,
        show_total_row=True,
        theme=get_theme(),
    )

    all_columns = list(final_df_styled.columns)

    column_config = {
        RangeColumn.RISK_SEGMENT.value: st.column_config.TextColumn(
            label=RangeColumn.RISK_SEGMENT.value,
            disabled=True,
            pinned=True,
        ),
        RangeColumn.CATEGORIES.value: st.column_config.MultiselectColumn(
            label=RangeColumn.CATEGORIES.value,
            width=300,
            disabled=not editable or default,
            pinned=True,
            options=iterations_vm.get_categorical_iteration_options(iteration_id),
            color="auto",
        ),
        RangeColumn.LOWER_BOUND.value: st.column_config.NumberColumn(
            label=RangeColumn.LOWER_BOUND.value,
            width=150,
            format="compact",
            disabled=not editable or default,
            pinned=True,
        ),
        RangeColumn.UPPER_BOUND.value: st.column_config.NumberColumn(
            label=RangeColumn.UPPER_BOUND.value,
            width=150,
            format="compact",
            disabled=not editable or default,
            pinned=True,
        ),
    }

    remaining_columns = [
        column for column in all_columns if column not in column_config.keys()
    ]

    for column in remaining_columns:
        column_config[column] = st.column_config.TextColumn(
            label=column,
            disabled=True,
        )

    def control_edit_handler() -> None:
        edited_rows: dict[int, dict[str, t.Any]] = st.session_state[key_name].get(
            "edited_rows", {}
        )
        edited_final_df: pd.DataFrame = final_df_styled.data.copy()  # type: ignore

        for row_index, row_change in edited_rows.items():
            if row_index not in edited_final_df.index or row_index == RowIndex.TOTAL:
                continue
            for col_index, change in row_change.items():
                edited_final_df.at[row_index, col_index] = change

        iterations_vm.editable_range_edit_handler(
            iteration_id, default, edited_final_df
        )

    # st.write(final_df_styled.data)  # type: ignore

    st.data_editor(
        data=final_df_styled,
        width="stretch",
        hide_index=True,
        column_config=column_config,
        key=key_name,
        placeholder="-",
        on_change=control_edit_handler,
        height="content",
    )

    if editable:
        error_and_warning_widget(errors, warnings)


__all__ = ["iteration_metric_table"]
