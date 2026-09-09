"""Double variable iteration UI page view."""

import typing as t

import streamlit as st

from risc_tool.data.models.enums import IterationType
from risc_tool.data.models.uid import IterationID
from risc_tool.data.session import Session
from risc_tool.ui.components.error_warnings import error_and_warning_widget
from risc_tool.ui.components.iteration_metric_table import iteration_metric_table
from risc_tool.ui.components.theme_detector import get_theme
from risc_tool.ui.iterations.common import (
    check_current_rs_details,
    editable_grid_widget,
    iteration_sidebar_components,
)
from risc_tool.ui.iterations.navigation import navigation_widgets


def metric_title_widget(metric_name: str, data_source_names: list[str]) -> None:
    """Render a metric title with its data source badges.

    Args:
        metric_name: The name of the metric.
        data_source_names: Labels of the data sources used.
    """
    with st.container(horizontal=True, height=30, border=False):
        st.markdown(f"##### {metric_name}")
        for ds_name in data_source_names:
            st.badge(ds_name)


def grid_layout_widget(iteration_id: IterationID, default: bool, key: str) -> None:
    """Render the split grid layout with the risk segment grid beside metric grids.

    Args:
        iteration_id: The ID of the double-variable iteration.
        default: Whether to show the default or editable grid.
        key: The widget key.
    """
    session: Session = st.session_state["session"]
    iterations_vm = session.iterations_view_model
    metric_ids = iterations_vm.get_iteration_metadata(iteration_id).metric_ids
    num_metrics = len(metric_ids)

    st.markdown("#### Default Grid" if default else "#### Editable Grid")

    if num_metrics == 0:
        editor_container = st.container(key=f"editor_grid_container-{key}")
        first_metric_container = None
    else:
        editor_container, first_metric_container = st.columns(2)

    status_container = st.container(key=f"editor_status_container-{key}")

    with editor_container:
        editable_grid_widget(iteration_id=iteration_id, key=key, default=default)

    metric_views, errors, warnings = iterations_vm.get_metric_grids(
        iteration_id,
        default,
        show_controls_idx="alternate",
        show_total_row=True,
        show_total_column=True,
        theme=get_theme(),
    )

    if first_metric_container and metric_views:
        with first_metric_container:
            metric_view = metric_views.pop(0)
            metric_title_widget(
                metric_name=metric_view["metric_name"],
                data_source_names=metric_view["data_source_names"],
            )
            st.dataframe(
                metric_view["metric_styler"],
                hide_index=True,
                height="content",
                placeholder="-",
            )

    with status_container:
        error_and_warning_widget(errors, warnings)

    if not metric_views:
        return

    columns: list[t.Any] = []
    row_count = (len(metric_views) + len(metric_views) % 2) // 2
    for _ in range(row_count):
        columns.extend(st.columns(2))

    for metric_view in metric_views:
        with columns.pop(0):
            metric_title_widget(
                metric_name=metric_view["metric_name"],
                data_source_names=metric_view["data_source_names"],
            )
            st.dataframe(
                metric_view["metric_styler"],
                hide_index=True,
                height="content",
                placeholder="-",
            )


def liner_layout_widget(iteration_id: IterationID, default: bool, key: str) -> None:
    """Render the linear layout with the risk segment grid stacked above metrics.

    Args:
        iteration_id: The ID of the double-variable iteration.
        default: Whether to show the default or editable grid.
        key: The widget key.
    """
    session: Session = st.session_state["session"]
    iterations_vm = session.iterations_view_model

    st.markdown("#### Default Grid" if default else "#### Editable Grid")
    metric_views, errors, warnings = iterations_vm.get_metric_grids(
        iteration_id,
        default,
        show_controls_idx="all",
        show_total_row=True,
        show_total_column=True,
        theme=get_theme(),
    )

    editable_grid_widget(iteration_id=iteration_id, key=key, default=default)
    error_and_warning_widget(errors, warnings)

    for metric_view in metric_views:
        metric_title_widget(
            metric_name=metric_view["metric_name"],
            data_source_names=metric_view["data_source_names"],
        )
        st.dataframe(
            metric_view["metric_styler"],
            hide_index=True,
        )


def double_var_iteration() -> None:
    """Render the double-variable iteration detail page."""
    navigation_widgets()

    session: Session = st.session_state["session"]
    iterations_vm = session.iterations_view_model
    iteration = iterations_vm.current_iteration

    if iteration is None or iteration.iter_type != IterationType.DOUBLE:
        st.exception(RuntimeError(f"Invalid Iteration Type: {type(iteration)}"))
        return

    metadata = iterations_vm.get_iteration_metadata(iteration.uid)

    with st.sidebar:
        iteration_sidebar_components(iteration_id=iteration.uid)

    st.title(iteration.pretty_name)
    st.write(f"##### Variable: `{iteration.variable_name}`")

    check_current_rs_details()

    if metadata.split_view_enabled:
        grid_layout_widget(iteration_id=iteration.uid, default=True, key="0")
        st.divider()
        grid_layout_widget(iteration_id=iteration.uid, default=False, key="1")
    else:
        liner_layout_widget(iteration_id=iteration.uid, default=True, key="0")
        st.divider()
        liner_layout_widget(iteration_id=iteration.uid, default=False, key="1")

    chain_iteration_id: IterationID | None = iteration.uid
    with st.container(border=True):
        st.markdown("## Previous Iterations")
        while chain_iteration_id is not None:
            chain_iteration = iterations_vm.get_iteration(chain_iteration_id)
            st.markdown(f"#### Iteration #{chain_iteration_id}")
            st.markdown(f"###### Variable: `{chain_iteration.variable_name}`")
            iteration_metric_table(
                iteration_id=chain_iteration_id,
                default=False,
                show_controls=True,
                filter_ids=metadata.current_filter_ids,
                metric_ids=metadata.metric_ids,
                scalars_enabled=metadata.scalars_enabled,
                remove_outliers=metadata.remove_outliers,
                editable=False,
                key=f"chain-{chain_iteration_id}",
            )
            chain_iteration_id = iterations_vm.iteration_graph.get_parent(
                chain_iteration_id
            )


__all__ = ["double_var_iteration"]
