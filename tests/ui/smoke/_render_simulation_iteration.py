"""Test wrapper that renders the v2 simulation iteration page for AppTest.

Requires ``st.session_state["session"]`` to be a fully prepared Session whose
simulation view model has a run simulation with an opened iteration.
"""

from risc_tool_v2.ui.simulation.simulation_iteration_view import (
    simulation_iteration_view,
)

simulation_iteration_view()
