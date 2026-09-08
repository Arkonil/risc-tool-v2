"""Simulation graph view: streamlit-flow canvas with sidebar actions."""

import html

import streamlit as st
from streamlit_flow import streamlit_flow  # type: ignore
from streamlit_flow.elements import StreamlitFlowEdge, StreamlitFlowNode  # type: ignore
from streamlit_flow.layouts import TreeLayout as FlowLayout  # type: ignore
from streamlit_flow.state import StreamlitFlowState  # type: ignore

from risc_tool_v2.data.core.uid import IterationID, SimulationID
from risc_tool_v2.data.simulation.models.iteration import SimulationIteration
from risc_tool_v2.ui.core.session import get_session
from risc_tool_v2.ui.simulation.simulation_vm import SimulationViewModel

_NODE_STYLE = {
    "background": "rgba(255, 255, 255, 0.9)",
    "box-shadow": "0 8px 32px 0 rgba( 31, 38, 135, 0.37 )",
    "backdrop-filter": "blur( 4.5px )",
    "-webkit-backdrop-filter": "blur( 4.5px )",
    "border-radius": "10px",
    "border": "1px solid rgba( 255, 255, 255, 0.18 )",
}


def _open_iteration(
    simulation_vm: SimulationViewModel, iteration_id: IterationID
) -> None:
    simulation_vm.open_iteration(iteration_id)


def _open_simulation(simulation_vm: SimulationViewModel, sim_id: SimulationID) -> None:
    simulation_vm.set_mode("view", sim_id)


def _sidebar_widgets(
    selected_id: SimulationID | None, selected_iteration_id: IterationID | None
) -> None:
    session = get_session()
    simulation_vm = session.simulation_view_model

    st.sidebar.button(
        label="Create Simulation",
        icon=":material/add:",
        width="stretch",
        type="secondary",
        on_click=lambda: simulation_vm.set_mode("create"),
    )

    iteration: SimulationIteration | None = None
    if selected_iteration_id is not None:
        try:
            iteration = simulation_vm.get_iteration(selected_iteration_id)
        except ValueError:
            iteration = None

    if iteration is not None:
        st.sidebar.divider()
        st.sidebar.markdown(f"**Selected: Iteration #{iteration.uid}**")

        st.sidebar.button(
            label="Open Iteration",
            icon=":material/open_in_new:",
            width="stretch",
            type="primary",
            on_click=lambda: _open_iteration(simulation_vm, iteration.uid),
        )
        st.sidebar.button(
            label="Open Simulation",
            icon=":material/account_tree:",
            width="stretch",
            type="secondary",
            on_click=lambda: _open_simulation(simulation_vm, iteration.simulation_id),
        )

    elif selected_id is not None:
        sim_id: SimulationID = selected_id

        st.sidebar.divider()
        st.sidebar.markdown(f"**Selected: Simulation #{sim_id}**")

        st.sidebar.button(
            label="Open Simulation",
            icon=":material/open_in_new:",
            width="stretch",
            type="primary",
            on_click=lambda: _open_simulation(simulation_vm, sim_id),
        )


def simulation_graph() -> None:
    """Render the simulation canvas and sidebar actions."""
    session = get_session()
    simulation_vm = session.simulation_view_model

    st.title("Simulations")

    simulations = simulation_vm.simulations

    nodes: list[StreamlitFlowNode] = []
    for sim_id, sim in simulations.items():
        scg = simulation_vm.scg_for(sim)
        safe_name = scg.name
        safe_var = scg.variable_name
        status = sim.status.value

        node_content = f"""<p>
            <strong>Simulation #{sim_id}</strong>
            <br />
            {safe_name}
            <br />
            <i>{safe_var}</i>
            <br />
            <span style="color: grey;">{status}</span>
        </p>"""

        nodes.append(
            StreamlitFlowNode(
                id=f"{sim_id}",
                pos=(100, 100),
                data={"content": node_content},
                node_type="input",
                source_position="right",
                target_position="left",
                draggable=False,
                style=_NODE_STYLE,
            )
        )

    edges: list[StreamlitFlowEdge] = []

    # Iterations hang off their simulation as a second layer. Each node id is
    # prefixed with "iter-" so clicks can be decoded without clashing with the
    # UUID-string simulation ids.
    for sim_id in simulations:
        for index, iteration in enumerate(simulation_vm.iterations_for_sim(sim_id)):
            safe_var = html.escape(iteration.variable_name)
            node_content = f"""<p>
                <strong>Iteration #{iteration.uid}</strong>
                <br />
                <i>{safe_var}</i>
            </p>"""
            nodes.append(
                StreamlitFlowNode(
                    id=f"iter-{iteration.uid}",
                    pos=(100, 150 + index * 50),
                    data={"content": node_content},
                    node_type="default",
                    source_position="right",
                    target_position="left",
                    draggable=False,
                    style=_NODE_STYLE,
                )
            )
            edges.append(
                StreamlitFlowEdge(
                    id=f"iter-{iteration.uid}-edge",
                    source=f"{sim_id}",
                    target=f"iter-{iteration.uid}",
                    animated=True,
                )
            )

    state = StreamlitFlowState(nodes, edges)
    state.timestamp = 0

    new_state = streamlit_flow(
        key=f"simulation_flow-{len(simulations)}",
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

    selected_id: SimulationID | None = None
    selected_iteration_id: IterationID | None = None
    raw_selected: str | None = (
        str(new_state.selected_id) if new_state.selected_id is not None else None
    )
    if raw_selected is not None:
        if raw_selected.startswith("iter-"):
            try:
                selected_iteration_id = IterationID(int=int(raw_selected[5:]))
            except (TypeError, ValueError):
                selected_iteration_id = None
        else:
            try:
                selected_id = SimulationID(raw_selected)
            except (TypeError, ValueError):
                selected_id = None

    _sidebar_widgets(selected_id, selected_iteration_id)

    if not simulations:
        st.caption("No simulations yet. Use **Create Simulation** to get started.")


__all__ = ["simulation_graph"]
