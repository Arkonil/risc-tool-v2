"""Tests for DataSourceID reference remapping when a data source is updated.

Data source identities are content-addressed, so editing a source re-derives
its ID. The repository publishes an old->new remap and dependent components
must rewrite their stored references so nothing dangles.
"""

from pathlib import Path

from risc_tool_v2.data.core.uid import DataSourceID
from risc_tool_v2.data.data_source.models.data_source import ReadConfig
from risc_tool_v2.data.data_source.repositories.data_repository import DataRepository
from risc_tool_v2.ui.data_source.data_explorer.data_explorer_vm import (
    DataExplorerViewModel,
)


def _write_csv(path: Path, contents: str) -> None:
    path.write_text(contents, encoding="utf-8")


def _repo_with(tmp_path: Path) -> tuple[DataRepository, Path, Path]:
    first = tmp_path / "a.csv"
    second = tmp_path / "b.csv"
    _write_csv(first, "value\n1\n")
    _write_csv(second, "value\n2\n")
    return DataRepository(), first, second


def test_data_source_order_preserved_across_update(tmp_path: Path) -> None:
    repo, first_path, second_path = _repo_with(tmp_path)
    first = repo.add_data_source("A", first_path, ReadConfig())
    second = repo.add_data_source("B", second_path, ReadConfig())

    old_id = first.uid
    updated = repo.update_data_source(first.uid, label="A2")

    assert old_id not in repo.data_sources
    assert list(repo.data_sources) == [updated.uid, second.uid]


def test_data_source_order_preserved_across_delete(tmp_path: Path) -> None:
    repo, first_path, second_path = _repo_with(tmp_path)
    first = repo.add_data_source("A", first_path, ReadConfig())
    second = repo.add_data_source("B", second_path, ReadConfig())

    repo.delete_data_source(second.uid)

    assert list(repo.data_sources) == [first.uid]


def test_update_publishes_remap_only_when_id_changes(tmp_path: Path) -> None:
    repo, first_path, _ = _repo_with(tmp_path)
    seen_remaps = []
    repo.subscribe(lambda change_ids, remaps: seen_remaps.append(remaps))

    ds = repo.add_data_source("Dev", first_path, ReadConfig())
    seen_remaps.clear()

    repo.update_data_source(ds.uid, label="Dev 2")
    assert seen_remaps == [{DataSourceID: {ds.uid: next(iter(repo.data_sources))}}]

    seen_remaps.clear()
    repo.update_data_source(next(iter(repo.data_sources)), label="Dev 2")
    assert seen_remaps == [None]


def test_metric_repository_remaps_references(data_repository, metric_repository):
    ds_ids = list(data_repository.data_sources.keys())
    metric_repository.create_metric(
        name="Avg Credit",
        query="`credit_score`.mean()",
        is_cumulative=False,
        use_thousand_sep=True,
        is_percentage=False,
        decimal_places=2,
        data_source_ids=ds_ids,
    )
    old_metric_id = next(iter(metric_repository.metrics))

    old_id = ds_ids[0]
    updated = data_repository.update_data_source(old_id, label="Dev Data 2")
    new_id = updated.uid

    # Metric identities hash their data source IDs: rewriting the reference
    # re-derives the metric's ID.
    assert new_id != old_id
    new_metric_id = next(iter(metric_repository.metrics))
    assert new_metric_id != old_metric_id

    metric = next(iter(metric_repository.metrics.values()))
    assert metric.data_source_ids == [new_id]
    assert old_id not in metric.data_source_ids

    dumped = next(iter(metric_repository.to_dict().metrics.values()))
    assert dumped.uid == new_metric_id
    assert dumped.data_source_ids == [new_id]


def test_data_explorer_remaps_iv_data_sources(data_repository, filter_repository):
    vm = DataExplorerViewModel(data_repository, filter_repository)
    old_id = next(iter(data_repository.data_sources.keys()))
    vm.iv_data_sources = [old_id]

    updated = data_repository.update_data_source(old_id, label="Dev Data 2")

    assert vm.iv_data_sources == [updated.uid]
    assert old_id not in vm.iv_data_sources
