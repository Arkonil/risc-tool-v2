"""Change tracking and notification system for the RISC Tool.

This module provides a reactive programming framework based on the Observer pattern.
Components can track changes in their dependencies and notify subscribers when
their own state changes. This enables automatic UI updates and data synchronization
across the application.

Key concepts:
- ChangeTracker: Abstract base for components that react to dependency changes.
- ChangeNotifier: Extends ChangeTracker to also notify its own subscribers.
- Signature: Unique identifier for each component type in the system.
- ChangeID: A tuple of (Signature, UUID) identifying a specific change event.
- Callback: Function signature for change notifications.
"""

import typing as t
from abc import ABC, abstractmethod
from uuid import uuid4

from risc_tool.data.models.enums import Signature
from risc_tool.data.models.types import Callback, CallbackID, ChangeID, ChangeIDs
from risc_tool.utils.logging import get_logger
from risc_tool.utils.write_once_dict import WriteOnceOrderedDict


class ChangeTracker(ABC):
    """Abstract base class for components that track changes in their dependencies.

    A ChangeTracker maintains a list of dependencies (ChangeNotifiers) and
    automatically subscribes to their change notifications. When a dependency
    changes, the tracker's on_dependency_update method is called.

    Attributes:
        signature: Unique identifier for this tracker type.
        _previous_changes: Set of change IDs that have already been processed.
        _callback_ids: Mapping from dependency signature to subscription callback ID.
        _dependencies: Ordered dictionary of dependency signatures to ChangeNotifiers.
    """

    @property
    @abstractmethod
    def signature(self) -> Signature:
        """Return the unique signature for this tracker type.

        Returns:
            The Signature enum value identifying this tracker.
        """
        return Signature.CHANGE_TRACKER

    def __init__(self, dependencies: list["ChangeNotifier"] | None = None):
        """Initialize the ChangeTracker with optional dependencies.

        Args:
            dependencies: List of ChangeNotifiers to track. The tracker will
                subscribe to each dependency's change notifications.
        """
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
        """Clean up subscriptions when the tracker is garbage collected."""
        for dependency in self._dependencies.values():
            dependency.unsubscribe(self._callback_ids[dependency.signature])

    def _has_changed(self, change_ids: ChangeIDs) -> bool:
        """Check if the given change IDs represent new changes.

        Args:
            change_ids: Set of change IDs from a dependency notification.

        Returns:
            True if any change ID is new (not in _previous_changes), False otherwise.
        """
        return not self._previous_changes.issuperset(change_ids)

    def _add_changes(self, change_ids: ChangeIDs):
        """Add change IDs to the set of processed changes.

        Args:
            change_ids: Set of change IDs to add to the processed set.
        """
        self._previous_changes.update(change_ids)

    def _on_dependency_update(self, change_ids: ChangeIDs):
        """Handle a dependency update notification.

        Args:
            change_ids: Set of change IDs from the dependency.

        Returns:
            True if the changes were new and on_dependency_update was called,
            False if the changes were already processed.
        """
        has_changed = self._has_changed(change_ids)

        if has_changed:
            self._add_changes(change_ids)
            self.on_dependency_update(change_ids)

        return has_changed

    @abstractmethod
    def on_dependency_update(self, change_ids: ChangeIDs) -> None:
        """Called when a dependency has new changes.

        Subclasses must implement this to react to dependency changes.

        Args:
            change_ids: Set of change IDs representing what changed.
        """
        raise NotImplementedError()


class ChangeNotifier(ChangeTracker):
    """A ChangeTracker that can also notify its own subscribers.

    ChangeNotifier extends ChangeTracker by maintaining a list of subscribers
    (callbacks) and providing methods to notify them when this component's
    state changes. It automatically notifies subscribers when its dependencies
    change (if those changes are new).

    Attributes:
        signature: Unique identifier for this notifier type.
        _subscribers: Ordered dictionary of callback IDs to callback functions.
    """

    @property
    @abstractmethod
    def signature(self) -> Signature:
        """Return the unique signature for this notifier type.

        Returns:
            The Signature enum value identifying this notifier.
        """
        return Signature.CHANGE_NOTIFIER

    def __init__(self, dependencies: list["ChangeNotifier"] | None = None):
        """Initialize the ChangeNotifier with optional dependencies.

        Args:
            dependencies: List of ChangeNotifiers to track as dependencies.
        """
        super().__init__(dependencies=dependencies)

        self._subscribers: t.OrderedDict[CallbackID, Callback] = t.OrderedDict()

    def subscribe(self, callback: Callback) -> CallbackID:
        """Register a callback to be notified of changes.

        Args:
            callback: A function that accepts a set of ChangeIDs and returns a bool.

        Returns:
            A unique CallbackID that can be used to unsubscribe later.
        """
        new_callback_id = uuid4()

        self._subscribers[new_callback_id] = callback

        return new_callback_id

    def unsubscribe(self, callback_id: CallbackID):
        """Remove a previously registered callback.

        Args:
            callback_id: The CallbackID returned from subscribe().
        """
        if callback_id in self._subscribers:
            del self._subscribers[callback_id]

    def notify_subscribers(self, change_ids: ChangeIDs | None = None):
        """Notify all subscribers of a change.

        Args:
            change_ids: Optional set of change IDs from dependencies. If None,
                only this notifier's new change ID is sent. If provided, the
                dependency change IDs are combined with this notifier's new ID.
        """
        new_change_id: ChangeID = (self.signature, uuid4())

        if change_ids is None:
            all_change_ids: ChangeIDs = {new_change_id}
        else:
            all_change_ids: ChangeIDs = change_ids | {new_change_id}

        for callback in self._subscribers.values():
            callback(all_change_ids)

    def _on_dependency_update(self, change_ids: ChangeIDs):
        """Handle a dependency update and propagate to subscribers if changed.

        Args:
            change_ids: Set of change IDs from the dependency.

        Returns:
            True if the changes were new and subscribers were notified,
            False if the changes were already processed.
        """
        has_changed = super()._on_dependency_update(change_ids)

        if has_changed:
            self.notify_subscribers(change_ids)

        return has_changed


__all__ = ["ChangeTracker", "ChangeNotifier"]
