"""Iteration graph tree visualization UI page."""

import html

import streamlit as st
from streamlit_flow import streamlit_flow  # type: ignore
from streamlit_flow.elements import StreamlitFlowEdge, StreamlitFlowNode  # type: ignore
from streamlit_flow.layouts import TreeLayout as FlowLayout  # type: ignore
from streamlit_flow.state import StreamlitFlowState  # type: ignore

from risc_tool.data.models.iteration import Iteration
from risc_tool.data.models.iteration_graph import IterationGraph
from risc_tool.data.models.types import IterationID
from risc_tool.data.session import Session


def streamlit_flow_graph(
    iterations: dict[IterationID, Iteration],
    iteration_graph: IterationGraph,
    selected_node_id: IterationID | None,
) -> StreamlitFlowState:
    connections = iteration_graph.connections

    node_style = {
        "background": "rgba(255, 255, 255, 0.9)",
        "box-shadow": "0 8px 32px 0 rgba( 31, 38, 135, 0.37 )",
        "backdrop-filter": "blur( 4.5px )",
        "-webkit-backdrop-filter": "blur( 4.5px )",
        "border-radius": "10px",
        "border": "1px solid rgba( 255, 255, 255, 0.18 )",
    }

    nodes: list[StreamlitFlowNode] = []

    for node_id, iteration in iterations.items():
        is_root = iteration_graph.is_root(node_id)
        is_leaf = iteration_graph.is_leaf(node_id)

        if is_root:
            node_type = "input"
        elif is_leaf:
            node_type = "output"
        else:
            node_type = "default"

        safe_name = html.escape(iteration.name)
        safe_var = html.escape(iteration.variable_name)

        if iteration.name == "":
            node_content = f"""<p>
                <strong>Iteration #{node_id}</strong>
                <br />
                <i>{safe_var}</i>
            </p>"""
        else:
            node_content = f"""<p>
                <strong>Iteration #{node_id}</strong>
                <br />
                {safe_name}
                <br />
                <i>{safe_var}</i>
            </p>"""

        nodes.append(
            StreamlitFlowNode(
                id=f"{node_id}",
                pos=(100, 100),
                data={"content": node_content},
                node_type=node_type,
                source_position="right",
                target_position="left",
                draggable=False,
                style=node_style,
            )
        )

    edges: list[StreamlitFlowEdge] = []

    for node_id, children in connections.items():
        for child_id in children:
            edges.append(
                StreamlitFlowEdge(
                    id=f"{node_id}-{child_id}",
                    source=f"{node_id}",
                    target=f"{child_id}",
                    edge_type="simplebezier",
                    animated=True,
                )
            )

    if selected_node_id is None:
        state = StreamlitFlowState(nodes, edges)
    else:
        state = StreamlitFlowState(nodes, edges, selected_id=str(selected_node_id))

    state.timestamp = 0

    new_state = streamlit_flow(
        key=f"iteration_flow-{len(iterations)}",
        state=state,
        layout=FlowLayout(direction="right"),
        fit_view=True,
        height=550,
        enable_node_menu=False,
        enable_edge_menu=False,
        enable_pane_menu=False,
        show_controls=False,
        get_edge_on_click=False,
        get_node_on_click=True,
        show_minimap=st.sidebar.checkbox("Show Minimap", value=True),
        hide_watermark=True,
        allow_new_edges=False,
    )

    return new_state


@st.dialog("Confirm Delete")
def delete_confirmation_dialog(node_id: IterationID):
    session: Session = st.session_state["session"]
    iterations_vm = session.iterations_view_model

    st.write(f"Are you sure you want to delete iteration #{node_id}?")

    children = iterations_vm.iteration_graph.get_descendants(node_id)
    if children:
        st.markdown("The following iterations will also be deleted:")
        st.markdown("\n".join([f"* `Iteration #{child}`" for child in children]))

    st.write("This action cannot be undone.")

    col1, col2 = st.columns(2)

    with col1:
        if st.button("Delete", type="primary", width="stretch"):
            iterations_vm.delete_iteration(node_id)
            st.rerun()
    with col2:
        if st.button("Cancel", type="secondary", width="stretch"):
            st.rerun()


@st.dialog("Rename Iteration")
def rename_iteration_dialog(node_id: IterationID):
    session: Session = st.session_state["session"]
    iterations_vm = session.iterations_view_model

    current_name = iterations_vm.get_iteration_name(node_id)
    new_name = st.text_input(
        "Iteration Name",
        value=current_name,
        key=f"rename_iteration_name_{node_id}",
    )

    col1, col2 = st.columns(2)

    with col1:
        if st.button("Save", type="primary", width="stretch"):
            iterations_vm.rename_iteration(node_id, new_name)
            st.rerun()
    with col2:
        if st.button("Cancel", type="secondary", width="stretch"):
            st.rerun()


def iteration_graph() -> None:
    session: Session = st.session_state["session"]
    iterations_vm = session.iterations_view_model

    st.title("Iteration Graph")

    _, selected_id = iterations_vm.current_status

    new_state = streamlit_flow_graph(
        iterations=iterations_vm.iterations,
        iteration_graph=iterations_vm.iteration_graph,
        selected_node_id=selected_id,
    )

    if new_state.selected_id is not None and new_state.selected_id.isdecimal():
        selected_id = IterationID(int(new_state.selected_id))
    else:
        selected_id = None

    if selected_id is None:
        st.sidebar.button(
            label="Add New Iteration",
            icon=":material/add:",
            width="stretch",
            type="secondary",
            on_click=lambda: iterations_vm.set_current_status(
                "create", iteration_create_parent_id=None
            ),
        )

    else:
        iterations_vm.set_current_status("graph", selected_iteration_id=selected_id)

        st.sidebar.button(
            label=f"Open Iteration #{selected_id}",
            width="stretch",
            type="primary",
            icon=":material/open_in_new:",
            on_click=lambda: iterations_vm.set_current_status(
                "view", current_iteration_id=selected_id
            ),
        )

        if iterations_vm.can_have_child(selected_id):
            st.sidebar.button(
                label="Add Child Iteration",
                icon=":material/add:",
                width="stretch",
                type="secondary",
                on_click=lambda: iterations_vm.set_current_status(
                    "create", iteration_create_parent_id=selected_id
                ),
            )

        if st.sidebar.button(
            label="Rename Iteration",
            icon=":material/edit:",
            width="stretch",
            type="secondary",
        ):
            rename_iteration_dialog(selected_id)

        if st.sidebar.button(
            label="Delete Iteration",
            icon=":material/delete:",
            width="stretch",
            type="secondary",
        ):
            delete_confirmation_dialog(selected_id)


__all__ = ["iteration_graph"]
