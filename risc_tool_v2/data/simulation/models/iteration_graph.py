"""Pydantic model for the iteration parent-child DAG graph.

Tracks how iterations relate: a single-variable iteration is a child of the
simulation; double-variable iterations are children of the iteration they
layer over; editable clones fan out from their family's fixed root. The graph
lives in the simulation repository and persists via :class:`IterationGraphJSON`.
"""

import typing as t

from pydantic import BaseModel, ConfigDict, Field

from risc_tool_v2.data.core.uid import IterationID
from risc_tool_v2.data.simulation.json.simulation_json import IterationGraphJSON


class IterationGraph(BaseModel):
    """Manages the DAG of parent and child iterations.

    Attributes:
        connections: Mapping of parent IterationID to a list of child IterationIDs.
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    connections: dict[IterationID, list[IterationID]] = Field(
        default_factory=dict[IterationID, list[IterationID]]
    )

    def add_child(self, parent_id: IterationID, child_id: IterationID) -> None:
        """Add a parent-child edge to the graph, enforcing DAG invariants.

        Args:
            parent_id: The parent iteration ID.
            child_id: The child iteration ID.

        Raises:
            ValueError: If the edge is a self-link, the child already has a
                different parent, or the edge would create a cycle.
        """
        if parent_id == child_id:
            raise ValueError(
                f"Cannot add self-link: parent_id and child_id are both {parent_id}."
            )
        existing_parent = self.get_parent(child_id)
        if existing_parent is not None and existing_parent != parent_id:
            raise ValueError(
                f"Child iteration #{child_id} already has parent iteration #{existing_parent}."
            )
        if parent_id in self.get_descendants(child_id):
            raise ValueError(
                f"Cannot add edge {parent_id} -> {child_id}: creates a cycle in the iteration graph."
            )

        if parent_id not in self.connections:
            self.connections[parent_id] = []
        if child_id not in self.connections[parent_id]:
            self.connections[parent_id].append(child_id)

    def remove_iteration(self, iteration_id: IterationID) -> None:
        """Remove an iteration from the graph, including any incoming edges.

        Args:
            iteration_id: The iteration ID to remove.
        """
        self.connections.pop(iteration_id, None)
        for children in self.connections.values():
            if iteration_id in children:
                children.remove(iteration_id)

    def get_parent(self, iteration_id: IterationID) -> IterationID | None:
        """Return the parent of an iteration, or None if it is a root.

        Args:
            iteration_id: The iteration ID to look up.

        Returns:
            The parent IterationID, or None if the iteration has no parent.
        """
        for parent, children in self.connections.items():
            if iteration_id in children:
                return parent
        return None

    def children(self, iteration_id: IterationID) -> tuple[IterationID, ...]:
        """Return the direct children of an iteration in insertion order.

        Args:
            iteration_id: The iteration ID to inspect.

        Returns:
            A tuple of direct child IterationIDs (empty if none).
        """
        return tuple(self.connections.get(iteration_id, ()))

    def roots(self) -> tuple[IterationID, ...]:
        """Return all root iterations (those without a parent).

        Returns:
            A tuple of root IterationIDs in insertion order.
        """
        child_ids = {
            child for children in self.connections.values() for child in children
        }
        return tuple(
            iter_id for iter_id in self.connections if iter_id not in child_ids
        )

    def iteration_depth(self, iteration_id: IterationID) -> int:
        """Compute the depth (level) of an iteration in the graph.

        Args:
            iteration_id: The iteration ID to measure.

        Returns:
            The depth, where root iterations have depth 1.
        """
        parent = self.get_parent(iteration_id)
        if parent is None:
            return 1
        return 1 + self.iteration_depth(parent)

    def get_ancestors(self, iteration_id: IterationID) -> list[IterationID]:
        """Return all ancestors of an iteration, ordered root-first.

        Args:
            iteration_id: The iteration ID to inspect.

        Returns:
            A list of ancestor IterationIDs from root down to the direct parent.
        """
        ancestors: list[IterationID] = []
        parent = self.get_parent(iteration_id)
        while parent is not None:
            ancestors.append(parent)
            parent = self.get_parent(parent)
        return list(reversed(ancestors))

    def get_descendants(self, iteration_id: IterationID) -> list[IterationID]:
        """Return all descendants of an iteration, in traversal order.

        Args:
            iteration_id: The iteration ID to inspect.

        Returns:
            A list of descendant IterationIDs (direct and indirect children).
        """
        if iteration_id not in self.connections:
            return []
        descendants = list(self.connections[iteration_id])
        for child in list(descendants):
            descendants.extend(self.get_descendants(child))
        return descendants

    def get_root_iter_id(self, iteration_id: IterationID) -> IterationID:
        """Return the root ancestor of an iteration.

        Args:
            iteration_id: The iteration ID to inspect.

        Returns:
            The IterationID of the root ancestor (the iteration itself if it is a root).
        """
        parent = self.get_parent(iteration_id)
        if parent is None:
            return iteration_id
        return self.get_root_iter_id(parent)

    def is_root(self, iteration_id: IterationID) -> bool:
        """Check whether an iteration has no parent.

        Args:
            iteration_id: The iteration ID to inspect.

        Returns:
            True if the iteration is a root, False otherwise.
        """
        return self.get_parent(iteration_id) is None

    def is_leaf(self, iteration_id: IterationID) -> bool:
        """Check whether an iteration has no children.

        Args:
            iteration_id: The iteration ID to inspect.

        Returns:
            True if the iteration is a leaf, False otherwise.
        """
        return (
            iteration_id not in self.connections
            or len(self.connections[iteration_id]) == 0
        )

    def to_dict(self) -> IterationGraphJSON:
        """Serialize this graph to its JSON model."""
        return IterationGraphJSON(
            connections={
                parent_id: list(child_ids)
                for parent_id, child_ids in self.connections.items()
            }
        )

    @classmethod
    def from_dict(cls, data: IterationGraphJSON) -> t.Self:
        """Reconstruct a graph from its JSON model."""
        return cls(
            connections={
                parent_id: [IterationID(child) for child in child_ids]
                for parent_id, child_ids in data.connections.items()
            }
        )


__all__ = ["IterationGraph"]
