"""Pydantic model for representing the iteration parent-child DAG graph."""

from pydantic import BaseModel, ConfigDict, Field

from risc_tool.data.models.types import IterationID


class IterationGraph(BaseModel):
    """Manages the DAG of parent and child iterations."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    connections: dict[IterationID, list[IterationID]] = Field(
        default_factory=dict[IterationID, list[IterationID]]
    )

    def add_child(self, parent_id: IterationID, child_id: IterationID) -> None:
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
        self.connections.pop(iteration_id, None)
        for children in self.connections.values():
            if iteration_id in children:
                children.remove(iteration_id)

    def get_parent(self, iteration_id: IterationID) -> IterationID | None:
        for parent, children in self.connections.items():
            if iteration_id in children:
                return parent
        return None

    def iteration_depth(self, iteration_id: IterationID) -> int:
        parent = self.get_parent(iteration_id)
        if parent is None:
            return 1
        return 1 + self.iteration_depth(parent)

    def get_ancestors(self, iteration_id: IterationID) -> list[IterationID]:
        ancestors: list[IterationID] = []
        parent = self.get_parent(iteration_id)
        while parent is not None:
            ancestors.append(parent)
            parent = self.get_parent(parent)
        return list(reversed(ancestors))

    def get_descendants(self, iteration_id: IterationID) -> list[IterationID]:
        if iteration_id not in self.connections:
            return []
        descendants = list(self.connections[iteration_id])
        for child in list(descendants):
            descendants.extend(self.get_descendants(child))
        return descendants

    def get_root_iter_id(self, iteration_id: IterationID) -> IterationID:
        parent = self.get_parent(iteration_id)
        if parent is None:
            return iteration_id
        return self.get_root_iter_id(parent)

    def is_root(self, iteration_id: IterationID) -> bool:
        return self.get_parent(iteration_id) is None

    def is_leaf(self, iteration_id: IterationID) -> bool:
        return (
            iteration_id not in self.connections
            or len(self.connections[iteration_id]) == 0
        )


__all__ = ["IterationGraph"]
