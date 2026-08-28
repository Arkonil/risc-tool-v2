from risc_tool_v2.data.core.changes import ChangeNotifier, ChangeTracker
from risc_tool_v2.data.core.enums import Signature
from risc_tool_v2.data.core.id_remap import Remaps
from risc_tool_v2.data.core.types import ChangeIDs
from risc_tool_v2.data.core.uid import DataSourceID


class DummyNotifier(ChangeNotifier):
    @property
    def signature(self) -> Signature:
        return Signature.DATA_REPOSITORY

    def on_dependency_update(self, change_ids: ChangeIDs) -> None:
        pass


class DummyTracker(ChangeTracker):
    @property
    def signature(self) -> Signature:
        return Signature.CHANGE_TRACKER

    def __init__(self, notifier: ChangeNotifier):
        super().__init__(dependencies=[notifier])
        self.notified = False
        self.received_remaps: Remaps | None = None

    def on_dependency_update(self, change_ids: ChangeIDs) -> None:
        self.notified = True

    def on_dependency_remap(self, remaps: Remaps) -> None:
        self.received_remaps = remaps


def test_change_notification():
    notifier = DummyNotifier()
    tracker = DummyTracker(notifier)

    assert not tracker.notified
    notifier.notify_subscribers()
    assert tracker.notified


def test_remap_stashing_and_merging():
    notifier = DummyNotifier()
    tracker = DummyTracker(notifier)

    old_id = DataSourceID(int=1)
    new_id = DataSourceID(int=2)
    notifier._stash_remap(old_id, new_id)

    notifier.notify_subscribers()
    assert tracker.received_remaps is not None
    assert DataSourceID in tracker.received_remaps
    assert tracker.received_remaps[DataSourceID][old_id] == new_id
