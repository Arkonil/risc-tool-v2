"""Navigation breadcrumb and buttons widget for iterations."""

import streamlit as st

from risc_tool.data.session import Session


def navigation_widgets() -> None:
    """Render navigation buttons to move between iterations in the graph."""
    session: Session = st.session_state["session"]
    iterations_vm = session.iterations_view_model
    iteration_graph = iterations_vm.iteration_graph

    view, iteration_id = iterations_vm.current_status
    if view == "graph":
        return

    w1, w2, w3, w4 = 100, 120, 120, 100
    columns = st.columns(
        [w1, w2, w3, w4, (1000 - w1 - w2 - w3 - w4)], vertical_alignment="center"
    )

    current_column = 0
    with columns[current_column]:
        st.button(
            label="Back",
            icon=":material/arrow_back_ios:",
            type="primary",
            on_click=lambda: iterations_vm.set_current_status("graph"),
        )

    if view == "create" or iteration_id is None:
        return

    node_depth = iteration_graph.iteration_depth(iteration_id)

    if node_depth > 1:
        current_column += 1
        with columns[current_column]:
            st.button(
                label="Previous",
                icon=":material/arrow_back_ios:",
                type="primary",
                on_click=lambda: iterations_vm.set_current_status(
                    "view",
                    current_iteration_id=iteration_graph.get_parent(iteration_id),
                ),
            )

    if not iteration_graph.is_leaf(iteration_id):
        children = iteration_graph.connections.get(iteration_id, [])
        if children:
            current_column += 1
            with columns[current_column]:
                child_node_id = st.selectbox(
                    "Select child node",
                    children,
                    label_visibility="collapsed",
                )

            current_column += 1
            with columns[current_column]:
                st.button(
                    "Next",
                    icon=":material/arrow_forward_ios:",
                    type="primary",
                    on_click=lambda: iterations_vm.set_current_status(
                        "view",
                        current_iteration_id=child_node_id,
                    ),
                )


__all__ = ["navigation_widgets"]
