import typing as t
from abc import ABC, abstractmethod
from uuid import uuid4

from risc_tool.data.models.enums import Signature
from risc_tool.data.models.types import Callback, CallbackID, ChangeID, ChangeIDs
from risc_tool.utils.logging import get_logger
from risc_tool.utils.write_once_dict import WriteOnceOrderedDict


class ChangeTracker(ABC):
    @property
    @abstractmethod
    def signature(self) -> Signature:
        return Signature.CHANGE_TRACKER

    def __init__(self, dependencies: list["ChangeNotifier"] | None = None):
        self.logger = get_logger(self.__class__.__name__)
        self._previous_changes: ChangeIDs = set()

        self._callback_ids: dict[Signature, CallbackID] = {}
        self._dependencies: WriteOnceOrderedDict[Signature, "ChangeNotifier"] = (
            WriteOnceOrderedDict()
        )

        dependencies = dependencies if dependencies else []
        for dependency in dependencies:
            self._dependencies[dependency.signature] = dependency

            callback_id = dependency.subscribe(self._on_dependency_update)
            self._callback_ids[dependency.signature] = callback_id

    def __del__(self):
        for dependency in self._dependencies.values():
            dependency.unsubscribe(self._callback_ids[dependency.signature])

    def _has_changed(self, change_ids: ChangeIDs) -> bool:
        return not self._previous_changes.issuperset(change_ids)

    def _add_changes(self, change_ids: ChangeIDs):
        self._previous_changes.update(change_ids)

    def _on_dependency_update(self, change_ids: ChangeIDs):
        has_changed = self._has_changed(change_ids)

        if has_changed:
            self._add_changes(change_ids)
            self.on_dependency_update(change_ids)

        return has_changed

    @abstractmethod
    def on_dependency_update(self, change_ids: ChangeIDs) -> None:
        raise NotImplementedError()


class ChangeNotifier(ChangeTracker):
    @property
    @abstractmethod
    def signature(self) -> Signature:
        return Signature.CHANGE_NOTIFIER

    def __init__(self, dependencies: list["ChangeNotifier"] | None = None):
        super().__init__(dependencies=dependencies)

        self._subscribers: t.OrderedDict[CallbackID, Callback] = t.OrderedDict()

    def subscribe(self, callback: Callback) -> CallbackID:
        new_callback_id = uuid4()

        self._subscribers[new_callback_id] = callback

        return new_callback_id

    def unsubscribe(self, callback_id: CallbackID):
        if callback_id in self._subscribers:
            del self._subscribers[callback_id]

    def notify_subscribers(self, change_ids: ChangeIDs | None = None):
        new_change_id: ChangeID = (self.signature, uuid4())

        if change_ids is None:
            all_change_ids: ChangeIDs = {new_change_id}
        else:
            all_change_ids: ChangeIDs = change_ids | {new_change_id}

        for callback in self._subscribers.values():
            callback(all_change_ids)

    def _on_dependency_update(self, change_ids: ChangeIDs):
        has_changed = super()._on_dependency_update(change_ids)

        if has_changed:
            self.notify_subscribers(change_ids)

        return has_changed


__all__ = ["ChangeTracker", "ChangeNotifier"]
