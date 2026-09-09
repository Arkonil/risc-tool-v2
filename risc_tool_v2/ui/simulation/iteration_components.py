"""Shared iteration widgets: top navigation, rename dialog, sortable metric selector.

These components mirror the v1 iterations UX: a top-of-page Back/Previous/Next
breadcrumb, an in-dialog rename form, and a sortable metric selector dialog.
They talk only to the SimulationViewModel.
"""

import typing as t
from collections import OrderedDict

import streamlit as st
from streamlit_sortables import sort_items  # type: ignore

from risc_tool_v2.data.core.uid import IterationID
from risc_tool_v2.ui.simulation.simulation_vm import SimulationViewModel


def _open(simulation_vm: SimulationViewModel, iteration_id: IterationID) -> None:
    simulation_vm.open_iteration(iteration_id)


def iteration_navigation(
    simulation_vm: SimulationViewModel, iteration_id: IterationID
) -> None:
    """Render the top-of-page Back/Previous/Next breadcrumb for an iteration.

    Mirrors v1 ``navigation_widgets``: Back always returns to the graph; when
    the iteration has a graph parent a Previous button opens it; when it has
    children a child selector plus a Next button opens the chosen child.
    """
    graph = simulation_vm.iteration_graph

    w1, w2, w3, w4 = 100, 120, 120, 100
    columns = st.columns(
        [w1, w2, w3, w4, (1000 - w1 - w2 - w3 - w4)],
        vertical_alignment="center",
    )

    current_column = 0
    with columns[current_column]:
        st.button(
            label="Back",
            icon=":material/arrow_back_ios:",
            type="primary",
            key=f"nav_back_{int(iteration_id)}",
            on_click=lambda: simulation_vm.set_mode("graph"),
        )

    node_depth = graph.iteration_depth(iteration_id)
    if node_depth > 1:
        parent_id = graph.get_parent(iteration_id)
        if parent_id is not None:
            current_column += 1
            with columns[current_column]:
                st.button(
                    label="Previous",
                    icon=":material/arrow_back_ios:",
                    type="primary",
                    key=f"nav_previous_{int(iteration_id)}",
                    on_click=lambda: _open(simulation_vm, parent_id),
                )

    if not graph.is_leaf(iteration_id):
        children = graph.children(iteration_id)
        if children:
            current_column += 1
            with columns[current_column]:
                child_node_id = st.selectbox(
                    label="Select child node",
                    options=children,
                    format_func=lambda uid: f"Iteration #{int(uid)}",
                    label_visibility="collapsed",
                    key=f"nav_child_{int(iteration_id)}",
                )

            current_column += 1
            with columns[current_column]:
                st.button(
                    label="Next",
                    icon=":material/arrow_forward_ios:",
                    type="primary",
                    key=f"nav_next_{int(iteration_id)}",
                    on_click=lambda: _open(simulation_vm, child_node_id),
                )


@st.dialog("Rename Iteration")
def rename_iteration_dialog(
    simulation_vm: SimulationViewModel, iteration_id: IterationID
) -> None:
    """Show a pre-filled dialog to rename an iteration."""
    current_name = simulation_vm.get_iteration(iteration_id).name
    new_name = st.text_input(
        label="Iteration Name",
        value=current_name,
        label_visibility="collapsed",
        key=f"rename_iteration_name_{int(iteration_id)}",
        placeholder="Iteration Name",
    )

    col1, col2 = st.columns(2)
    with col1:
        if st.button(label="Save", type="primary", width="stretch"):
            simulation_vm.rename_iteration(iteration_id, new_name or current_name)
            st.rerun()
    with col2:
        if st.button(label="Cancel", type="secondary", width="stretch"):
            st.rerun()


def rename_iteration_button(
    simulation_vm: SimulationViewModel, iteration_id: IterationID
) -> None:
    """Render a button that opens the rename dialog."""
    st.button(
        label="Rename Iteration",
        icon=":material/edit:",
        type="secondary",
        width="stretch",
        key=f"rename_iteration_button_{int(iteration_id)}",
        on_click=lambda: rename_iteration_dialog(simulation_vm, iteration_id),
    )


@st.dialog("Set Metrics")
def metric_selector_dialog(
    simulation_vm: SimulationViewModel, iteration_id: IterationID
) -> None:
    """Show a sortable metric selector dialog for an iteration.

    The four built-in bad rates plus the user-defined metrics are selectable;
    for double-variable iterations cumulative metrics are excluded. Ordering
    is controlled with a drag-and-drop sortable list.
    """
    iteration = simulation_vm.get_iteration(iteration_id)
    metadata = simulation_vm.iteration_metadata(iteration_id)
    options = simulation_vm.metric_options(iteration_id)
    if iteration.is_double_var:
        options = OrderedDict(
            (mid, metric)
            for mid, metric in options.items()
            if not metric.is_cumulative
        )
    current_ids = [mid for mid in metadata.metric_ids if mid in options]

    st.write("Select Metrics:")
    selected_metric_ids = st.multiselect(
        label="Metrics",
        options=list(options.keys()),
        default=current_ids,
        format_func=lambda metric_id: options[metric_id].name,
        label_visibility="collapsed",
        key=f"metric_selector_{int(iteration_id)}",
    )

    existing_metrics = [uid for uid in current_ids if uid in selected_metric_ids]
    new_metrics = [uid for uid in selected_metric_ids if uid not in current_ids]
    selected_metric_ids = existing_metrics + new_metrics

    st.write("Reorder Metrics:")
    selected_names = [options[metric_id].name for metric_id in selected_metric_ids]
    sorted_names = sort_items(
        items=selected_names,
        key=f"sort_items_{int(iteration_id)}",
    ) if selected_names else []
    sorted_ids = [
        selected_metric_ids[selected_names.index(name)] for name in sorted_names
    ]

    _, col = st.columns(2)
    with col:
        if st.button(label="Submit", type="primary", width="stretch"):
            simulation_vm.update_iteration_metadata(
                iteration_id, metric_ids=tuple(sorted_ids)
            )
            st.rerun()


def metric_selector_button(
    simulation_vm: SimulationViewModel, iteration_id: IterationID
) -> None:
    """Render a button that opens the metric selector dialog."""
    st.button(
        label="Set Metrics",
        icon=":material/functions:",
        type="secondary",
        width="stretch",
        help="Set metrics to display in the table",
        key=f"metric_selector_button_{int(iteration_id)}",
        on_click=lambda: metric_selector_dialog(simulation_vm, iteration_id),
    )


def split_view_segmented(current: bool, key: str) -> bool:
    """Render the List/Grid split-view toggle; returns True for Grid."""
    selection: str | None = st.segmented_control(
        label="Layout",
        options=["List", "Grid"],
        default="Grid" if current else "List",
        label_visibility="collapsed",
        key=key,
    )
    return selection == "Grid"


def previous_iteration_details_checkbox(current: bool, key: str) -> bool:
    """Render the "Show Previous Iteration Details" checkbox."""
    return st.checkbox(
        label="Show Previous Iteration Details",
        value=current,
        help="Show Previous Iteration Details",
        key=key,
    )


def group_display_labels(
    simulation_vm: SimulationViewModel, iteration_id: IterationID
) -> dict[t.Any, str]:
    """Return the previous iteration's band label per parent segment.

    Only meaningful for double-variable iterations whose graph parent is a
    single-variable iteration (its effective groups are keyed by root risk
    segment id); returns an empty mapping otherwise.
    """
    graph = simulation_vm.iteration_graph
    parent_id = graph.get_parent(iteration_id)
    if parent_id is None:
        return {}
    parent = simulation_vm.get_iteration(parent_id)
    if parent.is_double_var:
        return {}
    labels: dict[t.Any, str] = {}
    for gid in parent.effective_groups():
        labels[gid] = f"Band {int(gid)}"
    return labels


__all__ = [
    "group_display_labels",
    "iteration_navigation",
    "metric_selector_button",
    "previous_iteration_details_checkbox",
    "rename_iteration_button",
    "split_view_segmented",
]