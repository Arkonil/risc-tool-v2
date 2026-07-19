import typing as t

from risc_tool.data.models.changes import ChangeNotifier
from risc_tool.utils.new_id import id_generator, new_id


class BaseRepository(ChangeNotifier):
    def __init__(self, dependencies: list[ChangeNotifier] | None = None) -> None:
        super().__init__(dependencies=dependencies)

        self._id_generator = id_generator()

    def _get_new_id(self, current_ids: t.Collection[int] | None = None) -> int:
        return new_id(self._id_generator, current_ids)
