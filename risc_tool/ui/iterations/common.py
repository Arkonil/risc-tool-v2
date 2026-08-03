"""Shared iteration page helpers for legacy-compatible double-variable UI."""

import typing as t

import pandas as pd
import streamlit as st
import streamlit_antd_components as sac  # type: ignore

from risc_tool.data.models.enums import IterationType, RangeColumn
from risc_tool.data.models.types import GroupID, IterationID
from risc_tool.data.session import Session
from risc_tool.ui.components.filter_selector import filter_selector
from risc_tool.ui.components.metric_selector import metric_selector_button
from risc_tool.ui.components.variable_selector import variable_selector_dialog


@st.dialog("Set Groups")
def set_groups_dialog_widget(iteration_id: IterationID) -> None:
    """Open a dialog to select active groups for a double-variable iteration.

    Args:
        iteration_id: The ID of the iteration.
    """
    session: Session = st.session_state["session"]
    iterations_vm = session.iterations_view_model

    groups = iterations_vm.get_all_groups(iteration_id)
    if RangeColumn.SELECTED.value not in groups.columns:
        st.exception(ValueError("Selected column missing from group editor."))
        return

    column_config: dict[t.Any, t.Any] = {
        RangeColumn.SELECTED.value: st.column_config.CheckboxColumn(
            label=RangeColumn.SELECTED,
            disabled=False,
        ),
        RangeColumn.LOWER_BOUND.value: st.column_config.NumberColumn(
            label=RangeColumn.LOWER_BOUND,
            disabled=True,
            format="compact",
        ),
        RangeColumn.UPPER_BOUND.value: st.column_config.NumberColumn(
            label=RangeColumn.UPPER_BOUND,
            disabled=True,
            format="compact",
        ),
        RangeColumn.CATEGORIES.value: st.column_config.ListColumn(
            label=RangeColumn.CATEGORIES,
            width="large",
        ),
    }

    edited_groups = st.data_editor(
        groups,
        width="stretch",
        hide_index=False,
        column_config=column_config,
    )

    _, submit_col = st.columns(2)
    with submit_col:
        if st.button("Submit", type="primary", width="stretch"):
            selected_group_ids = [
                GroupID(int(group_id))
                for group_id in edited_groups[
                    edited_groups[RangeColumn.SELECTED.value]
                ].index.to_list()
            ]
            if iterations_vm.select_groups(iteration_id, selected_group_ids):
                st.rerun()


def iteration_sidebar_components(iteration_id: IterationID) -> None:
    """Render iteration sidebar widgets: variables, metrics, filters, and options.

    Args:
        iteration_id: The ID of the iteration.
    """
    session: Session = st.session_state["session"]
    iterations_vm = session.iterations_view_model
    iteration = iterations_vm.iterations.get(iteration_id)
    if iteration is None:
        return

    st.button(
        label="Set Variables",
        width="stretch",
        icon=":material/data_table:",
        help="Select variables for calculations",
        type="primary",
        on_click=variable_selector_dialog,
    )

    metric_selector_button(
        current_metrics=iterations_vm.get_iteration_metadata(iteration_id).metric_ids,
        set_metrics=lambda metric_ids: iterations_vm.set_metadata(
            iteration_id=iteration_id,
            metric_ids=metric_ids,
        ),
        is_double_var=iteration.iter_type == IterationType.DOUBLE,
    )

    if iteration.iter_type == IterationType.DOUBLE:
        left_col, right_col = st.columns([3, 1])
        with left_col:
            if st.button(
                label="Edit Groups",
                width="stretch",
                icon=":material/edit:",
            ):
                set_groups_dialog_widget(iteration_id)
        with right_col:
            if st.button(
                label="",
                width="stretch",
                icon=":material/add:",
                key=f"add-group-{iteration_id}",
            ) and iterations_vm.add_new_group(iteration_id):
                st.rerun()

    current_filter_ids = iterations_vm.get_iteration_metadata(
        iteration_id
    ).current_filter_ids
    selected_filter_ids = filter_selector(
        key=f"{iteration_id}",
        filter_ids=current_filter_ids,
    )
    if set(selected_filter_ids) != set(current_filter_ids):
        iterations_vm.set_metadata(
            iteration_id=iteration_id, filter_ids=selected_filter_ids
        )
        st.rerun()

    if iteration.iter_type == IterationType.DOUBLE:
        current_split_view = iterations_vm.get_iteration_metadata(
            iteration_id
        ).split_view_enabled

        selected_idx = sac.segmented(  # type: ignore
            items=[
                sac.SegmentedItem("List", "list"),
                sac.SegmentedItem("Grid", "grid"),
            ],
            use_container_width=True,
            size="sm",
            index=1 if current_split_view else 0,
            key=f"split-view-{iteration_id}",
            return_index=True,
        )  # type: ignore

        split_view_enabled: bool = selected_idx == 1  # type: ignore
        if split_view_enabled != current_split_view:
            iterations_vm.set_metadata(
                iteration_id=iteration_id,
                split_view_enabled=split_view_enabled,
            )
            st.rerun()

    current_scalars_enabled = iterations_vm.get_iteration_metadata(
        iteration_id
    ).scalars_enabled
    scalars_enabled = st.checkbox(
        label="Enable Scalars",
        value=current_scalars_enabled,
        help="Use Scalars for Annualized Write Off Rates",
    )
    if scalars_enabled != current_scalars_enabled:
        iterations_vm.set_metadata(
            iteration_id=iteration_id, scalars_enabled=scalars_enabled
        )
        st.rerun()

    current_remove_outliers = iterations_vm.get_iteration_metadata(
        iteration_id
    ).remove_outliers
    remove_outliers = st.checkbox(
        label="Remove Outliers",
        value=current_remove_outliers,
        help="Remove Outliers",
    )
    if remove_outliers != current_remove_outliers:
        iterations_vm.set_metadata(
            iteration_id=iteration_id, remove_outliers=remove_outliers
        )
        st.rerun()

    if iteration.iter_type == IterationType.DOUBLE:
        current_editable = iterations_vm.get_iteration_metadata(iteration_id).editable
        editable = st.checkbox(
            label="Editable",
            value=current_editable,
            help="Editable",
        )
        if editable != current_editable:
            iterations_vm.set_metadata(iteration_id=iteration_id, editable=editable)
            st.rerun()

        if iterations_vm.iteration_graph.iteration_depth(iteration_id) == 2:
            current_show_prev = iterations_vm.get_iteration_metadata(
                iteration_id
            ).show_prev_iter_details
            show_prev_iter_details = st.checkbox(
                label="Show Previous Iteration Details",
                value=current_show_prev,
                help="Show Previous Iteration Details",
            )
            if show_prev_iter_details != current_show_prev:
                iterations_vm.set_metadata(
                    iteration_id=iteration_id,
                    show_prev_iter_details=show_prev_iter_details,
                )
                st.rerun()


def check_current_rs_details() -> None:
    """Warn or notify when the current iteration's risk segment details drift."""
    session: Session = st.session_state["session"]
    iterations_vm = session.iterations_view_model
    iteration = iterations_vm.current_iteration
    if iteration is None:
        return

    is_same = iterations_vm.is_rs_details_same(iteration.uid)
    if is_same == "equal":
        return

    message = "Risk Segment Details have been changed after creating the iteration."
    if is_same == "unequal":
        message += " All calculations will be done with the original details."
        with st.expander(
            label="Error: Risk Segment Details not updated",
            expanded=False,
            icon=":material/error:",
        ):
            st.error(body=message, icon=":material/error:")
        return

    message += " Update?"
    with st.container(horizontal=True):
        st.warning(message, icon=":material/warning:")
        if st.button(
            label="Update",
            width="content",
            icon=":material/refresh:",
        ) and iterations_vm.update_rs_details(iteration.uid):
            st.rerun()


def editable_grid_widget(iteration_id: IterationID, default: bool, key: str) -> None:
    """Render the risk segment grid as a styled dataframe or data editor.

    Args:
        iteration_id: The ID of the double-variable iteration.
        default: Whether to show the default or custom grid.
        key: The widget key.
    """
    session: Session = st.session_state["session"]
    iterations_vm = session.iterations_view_model

    editable = (
        iterations_vm.get_iteration_metadata(iteration_id).editable and not default
    )
    grid_components = iterations_vm.get_editable_grid(iteration_id, default, editable)
    show_prev_iter_details = grid_components["show_prev_iter_details"]

    column_config: dict[t.Any, t.Any] = {}
    if grid_components["lower_bound_pos"] is not None:
        column_config[grid_components["lower_bound_pos"]] = (
            st.column_config.NumberColumn(
                width=100,
                format="compact",
                disabled=not editable or default,
                pinned=True,
            )
        )
    if grid_components["upper_bound_pos"] is not None:
        column_config[grid_components["upper_bound_pos"]] = (
            st.column_config.NumberColumn(
                width=100,
                format="compact",
                disabled=not editable or default,
                pinned=True,
            )
        )
    if grid_components["categories_pos"] is not None:
        column_config[grid_components["categories_pos"]] = (
            st.column_config.MultiselectColumn(
                width=200,
                disabled=not editable or default,
                pinned=True,
                options=iterations_vm.get_categorical_iteration_options(iteration_id),
                color="auto",
            )
        )
    for col_pos in grid_components["risk_segment_grid_col_pos"]:
        column_config[col_pos] = st.column_config.SelectboxColumn(
            disabled=not editable or default,
            options=grid_components["grid_options"],
            required=True,
        )

    widget_key = f"edited_grid-{key}-{iteration_id}"

    def grid_edit_handler() -> None:
        """Apply edited grid cells from the data editor to the iteration."""
        edited_rows: dict[int, dict[str, t.Any]] = st.session_state[widget_key][
            "edited_rows"
        ]
        edited_final_df = t.cast(pd.DataFrame, grid_components["styler"].data).copy()
        for row_index, row_change in edited_rows.items():
            for col_index, change in row_change.items():
                edited_final_df.at[row_index, col_index] = change
        iterations_vm.editable_grid_edit_handler(iteration_id, default, edited_final_df)

    with st.container(height=30, border=False):
        st.markdown("##### Risk Segment Grid")

    if (
        editable
        and iterations_vm.get_iteration_metadata(iteration_id).show_prev_iter_details
        and iterations_vm.get_iteration_metadata(iteration_id).split_view_enabled
        and iterations_vm.iteration_graph.iteration_depth(iteration_id) == 2
    ):
        st.space(size=20)

    if show_prev_iter_details or not editable:
        st.dataframe(
            data=grid_components["styler"],
            width="stretch",
            hide_index=True,
            column_config=column_config,
            key=widget_key,
            height="content",
            placeholder="-",
        )
    else:
        st.data_editor(
            data=grid_components["styler"],
            width="stretch",
            hide_index=True,
            column_config=column_config,
            key=widget_key,
            height="content",
            placeholder="-",
            on_change=grid_edit_handler,
        )


__all__ = [
    "check_current_rs_details",
    "editable_grid_widget",
    "iteration_sidebar_components",
    "set_groups_dialog_widget",
]
