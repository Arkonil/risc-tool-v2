"""Simulation graph view: streamlit-flow canvas with sidebar actions."""

import html

import streamlit as st
from streamlit_flow import streamlit_flow  # type: ignore
from streamlit_flow.elements import StreamlitFlowEdge, StreamlitFlowNode  # type: ignore
from streamlit_flow.layouts import TreeLayout as FlowLayout  # type: ignore
from streamlit_flow.state import StreamlitFlowState  # type: ignore

from risc_tool_v2.data.core.uid import IterationID, SimulationID, short_id
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


def _iteration_node_id(iteration_id: IterationID) -> str:
    """Encode an iteration into a compact flow node id.

    Uses the decimal integer uid suffix (e.g. ``"iter-42"``) which round-trips
    cleanly through :func:`_decode_iteration_node_id`. The full UUID string
    form must NOT be used here, because ``int(uuid_str)`` raises ``ValueError``
    and the node click would silently fail to decode.
    """
    return f"iter-{int(iteration_id)}"


def _decode_iteration_node_id(
    raw: str,
) -> IterationID | None:
    """Decode ``"iter-<int>"`` back into an :class:`IterationID`.

    Returns ``None`` when ``raw`` is not a valid iteration node id.
    """
    if not raw.startswith("iter-"):
        return None
    try:
        return IterationID(int=int(raw[5:]))
    except (TypeError, ValueError):
        return None


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
        st.sidebar.markdown(f"**Selected: Iteration #{int(iteration.uid)}**")

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
        st.sidebar.button(
            label="Add Double-Variable Iteration",
            icon=":material/add_chart:",
            width="stretch",
            type="secondary",
            disabled=iteration.is_double_var,
            on_click=lambda: simulation_vm.begin_iteration_create(iteration.uid),
        )

    elif selected_id is not None:
        sim_id: SimulationID = selected_id

        st.sidebar.divider()
        st.sidebar.markdown(f"**Selected: Simulation #{short_id(sim_id)}**")

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
            <strong>Simulation #{short_id(sim_id)}</strong>
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

    # Iterations build a layered DAG: a root iteration hangs off its
    # simulation, while double-variable iterations and editable clones connect
    # to their graph parent instead. Each node id is the compact integer suffix
    # "iter-<int(uid)>" so clicks can be decoded back to an IterationID without
    # clashing with the UUID-string simulation ids; the x offset encodes the
    # graph depth.
    index = 0
    for sim_id in simulations:
        for iteration in simulation_vm.iterations_for_sim(sim_id):
            depth = simulation_vm.iteration_graph.iteration_depth(iteration.uid)
            safe_var = html.escape(iteration.variable_name)
            markers = " · ".join(
                marker
                for marker, active in (
                    ("double-var", iteration.is_double_var),
                    ("editable", iteration.is_editable),
                )
                if active
            )
            marker_line = (
                f'<br /><span style="color: grey;">{markers}</span>' if markers else ""
            )
            node_content = f"""<p>
                <strong>Iteration #{int(iteration.uid)}</strong>
                <br />
                <i>{safe_var}</i>
                {marker_line}</p>"""
            nodes.append(
                StreamlitFlowNode(
                    id=_iteration_node_id(iteration.uid),
                    pos=(320 + (depth - 1) * 230, 150 + index * 60),
                    data={"content": node_content},
                    node_type="default",
                    source_position="right",
                    target_position="left",
                    draggable=False,
                    style=_NODE_STYLE,
                )
            )
            parent_id = simulation_vm.iteration_graph.get_parent(iteration.uid)
            source = (
                _iteration_node_id(parent_id) if parent_id is not None else f"{sim_id}"
            )
            target = _iteration_node_id(iteration.uid)
            edges.append(
                StreamlitFlowEdge(
                    id=f"{target}-edge",
                    source=source,
                    target=target,
                    animated=True,
                )
            )
            index += 1

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
            # Iteration node ids carry the compact decimal uid suffix; see
            # _iteration_node_id / _decode_iteration_node_id.
            selected_iteration_id = _decode_iteration_node_id(raw_selected)
        else:
            try:
                selected_id = SimulationID(raw_selected)
            except (TypeError, ValueError):
                selected_id = None

    _sidebar_widgets(selected_id, selected_iteration_id)

    if not simulations:
        st.caption("No simulations yet. Use **Create Simulation** to get started.")


__all__ = ["simulation_graph"]
