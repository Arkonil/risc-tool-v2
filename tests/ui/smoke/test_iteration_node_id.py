"""Unit tests for the simulation graph iteration node-id encode/decode.

Guards against the regression where iteration node ids were the full UUID
string form (``iter-0000...0001``) but the decoder called ``int(suffix)``,
raising ``ValueError`` so a node click could never select an iteration and the
"Open Iteration" button would never appear.
"""

from risc_tool_v2.data.core.uid import IterationID
from risc_tool_v2.ui.simulation.simulation_graph import (
    _decode_iteration_node_id,
    _iteration_node_id,
)


def test_iteration_node_id_round_trips():
    for uid in (IterationID(int=1), IterationID(int=42), IterationID(int=7)):
        encoded = _iteration_node_id(uid)
        assert encoded == f"iter-{int(uid)}"
        assert _decode_iteration_node_id(encoded) == uid


def test_iteration_node_id_rejects_uuid_form():
    # The UUID string form must NOT be a valid node id -- int() on a hyphenated
    # hex UUID string raises ValueError, which is exactly the historical bug.
    assert _decode_iteration_node_id("iter-00000000-0000-0000-0000-000000000001") is None


def test_iteration_node_id_rejects_non_iteration_inputs():
    assert _decode_iteration_node_id("") is None
    assert _decode_iteration_node_id("live-42") is None
    assert _decode_iteration_node_id("iter-abc") is None
