"""Base repository class for data management with change notification."""

import typing as t
from uuid import UUID

from risc_tool.data.models.changes import ChangeNotifier
from risc_tool.utils.new_id import id_generator, new_id


class BaseRepository(ChangeNotifier):
    """Base class for repositories that manage collections of entities.

    Provides common functionality for entity ID generation and change tracking
    through the ChangeNotifier system.

    Attributes:
        _id_generator: Generator for unique integer IDs.
    """

    def __init__(self, dependencies: list[ChangeNotifier] | None = None) -> None:
        """Initialize the base repository.

        Args:
            dependencies: Optional list of ChangeNotifier dependencies to track.
        """
        super().__init__(dependencies=dependencies)

        self._id_generator = id_generator()

    def _get_new_id(self, current_ids: t.Iterable[int | UUID] | None = None) -> int:
        """Generate a new unique ID not present in the given collection.

        Args:
            current_ids: Collection of existing IDs to avoid. If None, generates
                the next sequential ID.

        Returns:
            A new unique integer ID.
        """
        return new_id(self._id_generator, current_ids)
