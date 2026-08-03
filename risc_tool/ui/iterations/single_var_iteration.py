"""Single variable iteration UI page view."""

import streamlit as st

from risc_tool.data.models.enums import IterationType
from risc_tool.data.models.types import IterationID
from risc_tool.data.session import Session
from risc_tool.ui.components.filter_selector import filter_selector
from risc_tool.ui.components.iteration_metric_table import iteration_metric_table
from risc_tool.ui.components.metric_selector import metric_selector_button
from risc_tool.ui.components.variable_selector import variable_selector_dialog
from risc_tool.ui.iterations.navigation import navigation_widgets


def sidebar_components(iteration_id: IterationID) -> None:
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

    meta = iterations_vm.get_iteration_metadata(iteration_id)
    metric_selector_button(
        current_metrics=meta.metric_ids,
        set_metrics=lambda metric_ids: iterations_vm.set_metadata(
            iteration_id=iteration_id,
            metric_ids=metric_ids,
        ),
        is_double_var=iteration.iter_type == IterationType.DOUBLE,
    )

    current_filter_ids = meta.current_filter_ids
    selected_filter_ids = filter_selector(
        key=f"{iteration_id}", filter_ids=current_filter_ids
    )
    if set(selected_filter_ids) != set(current_filter_ids):
        iterations_vm.set_metadata(
            iteration_id=iteration_id, filter_ids=selected_filter_ids
        )
        st.rerun()

    scalars_enabled = st.checkbox("Enable Scalars", value=meta.scalars_enabled)
    if scalars_enabled != meta.scalars_enabled:
        iterations_vm.set_metadata(
            iteration_id=iteration_id, scalars_enabled=scalars_enabled
        )
        st.rerun()

    remove_outliers = st.checkbox("Remove Outliers", value=meta.remove_outliers)
    if remove_outliers != meta.remove_outliers:
        iterations_vm.set_metadata(
            iteration_id=iteration_id, remove_outliers=remove_outliers
        )
        st.rerun()


def single_var_iteration() -> None:
    """Render the single-variable iteration detail page."""
    navigation_widgets()
    session: Session = st.session_state["session"]
    iterations_vm = session.iterations_view_model
    iteration = iterations_vm.current_iteration

    if iteration is None or iteration.iter_type != IterationType.SINGLE:
        st.exception(RuntimeError(f"Invalid Iteration Type: {type(iteration)}"))
        return

    metadata = iterations_vm.get_iteration_metadata(iteration.uid)

    with st.sidebar:
        sidebar_components(iteration.uid)

    st.title(iteration.pretty_name)
    st.write(f"##### Variable: `{iteration.variable_name}`")

    st.markdown("##### Default Range")
    iteration_metric_table(
        iteration_id=iteration.uid,
        editable=True,
        default=True,
        show_controls=True,
        filter_ids=metadata.current_filter_ids,
        metric_ids=metadata.metric_ids,
        scalars_enabled=metadata.scalars_enabled,
        remove_outliers=metadata.remove_outliers,
        key="range-grid-default",
    )

    st.markdown("##### Editable Range")
    iteration_metric_table(
        iteration_id=iteration.uid,
        editable=True,
        default=False,
        show_controls=True,
        filter_ids=metadata.current_filter_ids,
        metric_ids=metadata.metric_ids,
        scalars_enabled=metadata.scalars_enabled,
        remove_outliers=metadata.remove_outliers,
        key="range-grid-editable",
    )


__all__ = ["single_var_iteration"]
