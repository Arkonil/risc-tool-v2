"""Tests for MetricID reference remapping when metrics and data sources change.

Metric identities hash their content including data source IDs, so editing
a metric re-derives its ID and editing a data source chains into metric ID
changes. The repository publishes old->new remaps for both paths; dependent
components use them to rewrite stored references.
"""

from pathlib import Path

import pytest

from risc_tool.data.models.data_source import ReadConfig
from risc_tool.data.models.uid import DataSourceID, MetricID
from risc_tool.ui.metrics.metrics_vm import MetricViewModel

METRIC_QUERY = "`credit_score`.mean()"


def _create_metric(
    data_repository,
    metric_repository,
    name: str = "Avg Credit",
    query: str = METRIC_QUERY,
    data_source_ids=None,
    **overrides,
) -> None:
    """Create a user-defined metric over all current sources by default."""
    metric_repository.create_metric(
        name=name,
        query=query,
        is_cumulative=False,
        use_thousand_sep=True,
        is_percentage=False,
        decimal_places=2,
        data_source_ids=(
            data_source_ids
            if data_source_ids is not None
            else list(data_repository.data_sources.keys())
        ),
        **overrides,
    )


def test_create_metric_uses_content_addressed_id(data_repository, metric_repository):
    _create_metric(data_repository, metric_repository)

    metric = next(iter(metric_repository.metrics.values()))
    assert next(iter(metric_repository.metrics)) == metric.create_hash()


def test_create_metric_rejects_duplicate_content(data_repository, metric_repository):
    _create_metric(data_repository, metric_repository)

    with pytest.raises(ValueError, match="already exists"):
        _create_metric(data_repository, metric_repository)


def test_modify_publishes_remap_only_when_content_changes(
    data_repository, metric_repository
):
    _create_metric(data_repository, metric_repository)
    old_id = next(iter(metric_repository.metrics))
    ds_ids = list(metric_repository.metrics[old_id].data_source_ids)

    seen_remaps = []
    metric_repository.subscribe(lambda change_ids, remaps: seen_remaps.append(remaps))

    # Rename only: new identity.
    metric_repository.modify_metric(
        old_id, "Avg Credit 2", METRIC_QUERY, False, True, False, 2, ds_ids
    )

    new_id = next(iter(metric_repository.metrics))
    assert len(metric_repository.metrics) == 1
    assert new_id != old_id
    assert seen_remaps == [{MetricID: {old_id: new_id}}]

    # Re-modifying with identical content keeps the ID: no remap.
    seen_remaps.clear()
    metric_repository.modify_metric(
        new_id, "Avg Credit 2", METRIC_QUERY, False, True, False, 2, ds_ids
    )
    assert seen_remaps == [None]
    assert next(iter(metric_repository.metrics)) == new_id


def test_display_flag_change_rehashes_identity(data_repository, metric_repository):
    _create_metric(data_repository, metric_repository)
    old_id = next(iter(metric_repository.metrics))
    ds_ids = list(metric_repository.metrics[old_id].data_source_ids)

    seen_remaps = []
    metric_repository.subscribe(lambda change_ids, remaps: seen_remaps.append(remaps))

    metric_repository.modify_metric(
        old_id, "Avg Credit", METRIC_QUERY, False, True, False, 3, ds_ids
    )

    new_id = next(iter(metric_repository.metrics))
    assert new_id != old_id
    assert metric_repository.metrics[new_id].decimal_places == 3
    assert seen_remaps == [{MetricID: {old_id: new_id}}]


def test_modify_preserves_registration_order(data_repository, metric_repository):
    _create_metric(data_repository, metric_repository, name="First")
    _create_metric(
        data_repository, metric_repository, name="Second", query="`income`.mean()"
    )
    first_id = next(iter(metric_repository.metrics))
    ds_ids = list(metric_repository.metrics[first_id].data_source_ids)

    metric_repository.modify_metric(
        first_id, "First Renamed", METRIC_QUERY, False, True, False, 2, ds_ids
    )

    keys = list(metric_repository.metrics)
    assert len(keys) == 2
    assert keys[0] != first_id
    assert metric_repository.metrics[keys[0]].name == "First Renamed"
    assert metric_repository.metrics[keys[1]].name == "Second"


def test_duplicate_creates_distinct_content_id(data_repository, metric_repository):
    _create_metric(data_repository, metric_repository)
    original_id = next(iter(metric_repository.metrics))
    original = metric_repository.metrics[original_id]

    metric_repository.duplicate_metric(original_id)

    assert len(metric_repository.metrics) == 2
    assert original_id in metric_repository.metrics
    copy = next(m for m in metric_repository.metrics.values() if m is not original)
    assert copy.uid != original_id
    assert copy.name != original.name


def test_data_source_edit_chains_metric_id_remap(data_repository, metric_repository):
    ds_ids = list(data_repository.data_sources.keys())
    _create_metric(data_repository, metric_repository, data_source_ids=ds_ids)
    old_metric_id = next(iter(metric_repository.metrics))
    old_ds_id = ds_ids[0]

    seen_remaps = []
    metric_repository.subscribe(lambda change_ids, remaps: seen_remaps.append(remaps))

    updated = data_repository.update_data_source(old_ds_id, label="Renamed")
    new_ds_id = updated.uid

    new_metric_id = next(iter(metric_repository.metrics))
    assert new_metric_id != old_metric_id

    # A single merged notification carries both the upstream DataSourceID
    # remap and the chained MetricID remap computed by this repository.
    assert seen_remaps == [
        {
            DataSourceID: {old_ds_id: new_ds_id},
            MetricID: {old_metric_id: new_metric_id},
        }
    ]

    metric = metric_repository.metrics[new_metric_id]
    assert metric.data_source_ids == [new_ds_id]
    assert old_metric_id not in metric_repository.metrics


def test_unrelated_data_source_edit_does_not_churn_ids(
    data_repository, metric_repository, tmp_path: Path
):
    extra_path = tmp_path / "extra.csv"
    extra_path.write_text("credit_score\n1\n", encoding="utf-8")
    extra_ds = data_repository.add_data_source("Extra", extra_path, ReadConfig())

    metric_repository.create_metric(
        name="Unrelated",
        query="`credit_score`.mean()",
        is_cumulative=False,
        use_thousand_sep=True,
        is_percentage=False,
        decimal_places=2,
        data_source_ids=[extra_ds.uid],
    )
    metric_id = next(iter(metric_repository.metrics))

    other_ds_id = next(
        ds_id for ds_id in data_repository.data_sources if ds_id != extra_ds.uid
    )
    data_repository.update_data_source(other_ds_id, label="Renamed")

    assert next(iter(metric_repository.metrics)) == metric_id
    assert metric_repository.metrics[metric_id].data_source_ids == [extra_ds.uid]


def test_metric_vm_follows_metric_id_remap(data_repository, metric_repository):
    vm = MetricViewModel(data_repository, metric_repository)
    _create_metric(data_repository, metric_repository)
    old_id = next(iter(metric_repository.metrics))
    ds_ids = list(metric_repository.metrics[old_id].data_source_ids)

    vm.set_mode("edit", old_id)
    assert vm.metric_cache.uid == old_id
    assert vm.is_verified

    metric_repository.modify_metric(
        old_id, "Avg Credit Edited", "`credit_score`.max()", False, True, False, 2, ds_ids
    )

    new_id = next(iter(metric_repository.metrics))
    assert vm.metric_cache.uid == new_id
    assert vm.metric_cache.name == "Avg Credit Edited"
    assert vm.is_verified


def test_metric_vm_draft_resets_on_dependency_update(
    data_repository, metric_repository
):
    """Unsaved drafts carry no derived identity and follow the filters
    convention: any dependency update resets the editor placeholder."""
    vm = MetricViewModel(data_repository, metric_repository)
    vm.set_mode("edit")
    ds_id = next(iter(data_repository.data_sources))
    vm.selected_data_source_ids = [ds_id]
    assert vm.selected_data_source_ids == [ds_id]

    data_repository.update_data_source(ds_id, label="Renamed")

    assert vm.metric_cache.uid is MetricID.EMPTY
    assert vm.metric_cache.query == ""
    assert vm.selected_data_source_ids == []
    assert vm.is_verified is False


def test_metric_vm_saved_edit_survives_dependency_updates(
    data_repository, metric_repository
):
    vm = MetricViewModel(data_repository, metric_repository)
    _create_metric(data_repository, metric_repository)
    metric_id = next(iter(metric_repository.metrics))

    vm.set_mode("edit", metric_id)

    data_repository.update_data_source(
        next(iter(data_repository.data_sources)), label="Renamed Data"
    )

    new_metric_id = next(iter(metric_repository.metrics))
    assert vm.metric_cache.uid == new_metric_id
    assert vm.is_verified
