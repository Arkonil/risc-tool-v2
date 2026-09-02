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

import time
import typing as t
from abc import ABC, abstractmethod
from uuid import uuid4

from risc_tool_v2.data.core.enums import Signature
from risc_tool_v2.data.core.types import (
    Callback,
    CallbackID,
    ChangeID,
    ChangeIDs,
    Remaps,
)
from risc_tool_v2.data.core.uid import BaseUID
from risc_tool_v2.data.core.utils.logging import get_logger
from risc_tool_v2.data.core.utils.write_once_dict import WriteOnceOrderedDict


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
        self._pending_remaps: Remaps = {}

        self._callback_ids: dict[Signature, CallbackID] = {}
        self._dependencies: WriteOnceOrderedDict[Signature, ChangeNotifier] = (
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

    def _stash_remap(self, old_id: BaseUID, new_id: BaseUID) -> None:
        """Record an identity change, composing with previously stashed remaps.

        Args:
            old_id: The ID references held before this batch started.
            new_id: The ID that replaces it now.
        """
        id_class = type(old_id)
        if id_class not in self._pending_remaps:
            self._pending_remaps[id_class] = {}
        pending = self._pending_remaps[id_class]

        # Compose: anything already pointing at old_id now points at new_id.
        for src in [src for src, dst in pending.items() if dst == old_id]:
            pending[src] = new_id
        pending.pop(old_id, None)
        pending[old_id] = new_id

    def _stash_removal(self, removed_id: BaseUID) -> None:
        """Drop stashed remap entries that reference a removed entity.

        Args:
            removed_id: The ID that no longer resolves to any entity.
        """
        id_class = type(removed_id)
        if id_class not in self._pending_remaps:
            return
        pending = self._pending_remaps[id_class]
        pending.pop(removed_id, None)
        for src in [src for src, dst in pending.items() if dst == removed_id]:
            del pending[src]
        if not pending:
            del self._pending_remaps[id_class]

    def _on_dependency_update(
        self, change_ids: ChangeIDs, remaps: Remaps | None = None
    ):
        """Handle a dependency update notification.

        Args:
            change_ids: Set of change IDs from the dependency.
            remaps: Optional identity remappings published by the dependency.

        Returns:
            True if the changes were new and on_dependency_update was called,
            False if the changes were already processed.
        """
        has_changed = self._has_changed(change_ids)

        if has_changed:
            self.logger.debug(
                "Dependency update received: %d change IDs", len(change_ids)
            )
            self._add_changes(change_ids)
            if remaps:
                self.on_dependency_remap(remaps)
            self.on_dependency_update(change_ids)

        return has_changed

    def on_dependency_remap(self, remaps: Remaps) -> None:
        """React to identity remappings published by a dependency.

        Called before :meth:`on_dependency_update` when a dependency
        notifies subscribers with an optional remap payload. Subclasses
        that store references to remapped identities should rewrite them
        here so no stale references remain. Default implementation is a
        no-op for classes that do not store remappable references.

        Args:
            remaps: Identity remappings keyed by ID class
                (``{id_class: {old_id: new_id}}``).
        """

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
        self.logger.debug("Subscriber registered: %s", new_callback_id)

        return new_callback_id

    def unsubscribe(self, callback_id: CallbackID):
        """Remove a previously registered callback.

        Args:
            callback_id: The CallbackID returned from subscribe().
        """
        if callback_id in self._subscribers:
            del self._subscribers[callback_id]
            self.logger.debug("Subscriber %s unsubscribed", callback_id)

    def _consume_pending_remaps(self, remaps: Remaps | None = None) -> Remaps | None:
        """Merge stashed remaps into outbound remaps payload and clear pending.

        Args:
            remaps: Optional incoming identity remappings payload.

        Returns:
            Merged Remaps payload, or None if no remaps exist.
        """
        if not self._pending_remaps:
            return remaps

        pending_batch = dict(self._pending_remaps)
        self._pending_remaps.clear()

        outbound: Remaps = dict(remaps) if remaps else {}

        for id_class, pending_dict in pending_batch.items():
            if pending_dict:
                existing = outbound.get(id_class, {})
                outbound[id_class] = {**existing, **pending_dict}

        return outbound if outbound else None

    def notify_subscribers(
        self, change_ids: ChangeIDs | None = None, remaps: Remaps | None = None
    ):
        """Notify all subscribers of a change.

        Args:
            change_ids: Optional set of change IDs from dependencies. If None,
                only this notifier's new change ID is sent. If provided, the
                dependency change IDs are combined with this notifier's new ID.
            remaps: Optional identity remappings (``{id_class: {old_id: new_id}}``)
                to deliver to subscribers alongside the change IDs.
        """
        self.logger.info("NOTIFY_ENTRY %s at %.3f", self.signature, time.time())
        remaps = self._consume_pending_remaps(remaps)

        new_change_id: ChangeID = (self.signature, uuid4())
        if change_ids is None:
            all_change_ids: ChangeIDs = {new_change_id}
        else:
            all_change_ids: ChangeIDs = change_ids | {new_change_id}

        self.logger.debug("Notifying %d subscribers", len(self._subscribers))
        for key, callback in self._subscribers.items():
            _t0 = time.perf_counter()
            callback(all_change_ids, remaps)
            _t1 = time.perf_counter()
            _owner = getattr(getattr(callback, "__self__", None), "__class__", None)
            _owner = getattr(_owner, "__name__", _owner) if _owner else "?"
            if _t1 - _t0 > 0.05:
                self.logger.info(
                    "SUBSCRIBER %s (%s) took %.3fs",
                    _owner,
                    getattr(callback, "__name__", key),
                    _t1 - _t0,
                )

    def _on_dependency_update(
        self, change_ids: ChangeIDs, remaps: Remaps | None = None
    ):
        """Handle a dependency update and propagate to subscribers if changed.

        Args:
            change_ids: Set of change IDs from the dependency.
            remaps: Optional identity remappings published by the dependency.

        Returns:
            True if the changes were new and subscribers were notified,
            False if the changes were already processed.
        """
        has_changed = super()._on_dependency_update(change_ids, remaps)

        if has_changed:
            self.notify_subscribers(change_ids, remaps)

        return has_changed


class BaseRepository(ChangeNotifier):
    """Base class for repositories that manage collections of entities.

    Provides common functionality and change tracking through the
    ChangeNotifier system.
    """


__all__ = ["BaseRepository", "ChangeNotifier", "ChangeTracker"]
