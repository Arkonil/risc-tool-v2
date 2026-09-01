"""Tests for FilterID reference remapping when filters and outlier rules change.

Filter identities are content-addressed, so editing a filter re-derives its
ID. The repository publishes an old->new remap that dependent components use
to rewrite stored references; DataSourceID remaps must flow through without
disturbing filter state.
"""

import pytest

from risc_tool.data.models.enums import ComparisonOperation, PercentileOptions
from risc_tool.data.models.filter import Filter
from risc_tool.data.models.uid import FilterID
from risc_tool.ui.data_explorer.data_explorer_vm import DataExplorerViewModel
from risc_tool.ui.filters.filters_vm import FilterViewModel

FILTER_QUERY = "`credit_score` > 600"
FILTER_QUERY_ALT = "`credit_score` < 900"


def test_create_filter_uses_content_addressed_id(filter_repository) -> None:
    filter_repository.create_filter("F1", FILTER_QUERY)

    filter_id = next(iter(filter_repository.filters))
    expected = Filter(name="F1", query=FILTER_QUERY).uid

    assert filter_id == expected


def test_create_filter_rejects_duplicate_content(filter_repository) -> None:
    filter_repository.create_filter("F1", FILTER_QUERY)

    with pytest.raises(ValueError, match="already exists"):
        filter_repository.create_filter("F1", FILTER_QUERY)


def test_modify_publishes_remap_only_when_id_changes(filter_repository) -> None:
    filter_repository.create_filter("F1", FILTER_QUERY)
    old_id = next(iter(filter_repository.filters))

    seen_remaps = []
    filter_repository.subscribe(lambda change_ids, remaps: seen_remaps.append(remaps))

    filter_repository.modify_filter(old_id, "F2", FILTER_QUERY)

    new_id = next(iter(filter_repository.filters))
    assert len(filter_repository.filters) == 1
    assert new_id != old_id
    assert seen_remaps == [{FilterID: {old_id: new_id}}]

    # Re-modifying with identical content keeps the ID: no remap.
    seen_remaps.clear()
    filter_repository.modify_filter(new_id, "F2", FILTER_QUERY)
    assert seen_remaps == [None]
    assert next(iter(filter_repository.filters)) == new_id


def test_modify_preserves_registration_order(filter_repository) -> None:
    filter_repository.create_filter("F1", FILTER_QUERY)
    filter_repository.create_filter("F2", FILTER_QUERY_ALT)
    first_id = next(iter(filter_repository.filters))

    filter_repository.modify_filter(first_id, "F1 Renamed", "`income` > 1000")

    keys = list(filter_repository.filters)
    assert len(keys) == 2
    assert keys[0] != first_id
    assert filter_repository.filters[keys[0]].name == "F1 Renamed"
    assert filter_repository.filters[keys[1]].name == "F2"


def test_duplicate_creates_distinct_content_id(filter_repository) -> None:
    filter_repository.create_filter("F1", FILTER_QUERY)
    original_id = next(iter(filter_repository.filters))
    original = filter_repository.filters[original_id]

    filter_repository.duplicate_filter(original_id)

    assert len(filter_repository.filters) == 2
    assert original_id in filter_repository.filters
    copy = next(f for f in filter_repository.filters.values() if f is not original)
    assert copy.uid != original_id
    assert copy.query == original.query
    assert copy.name != original.name


def test_outlier_rule_recalculation_keeps_repo_identity(
    data_repository, filter_repository
) -> None:
    filter_repository.create_outlier_rule(
        "credit_score", ComparisonOperation.GT, PercentileOptions.PERC_90
    )
    outlier_id = next(iter(filter_repository.filters))
    rule = filter_repository.filters[outlier_id]

    rule.recalculate_thresholds(data_repository.get_lazyframe())

    assert rule.uid == outlier_id


def test_modify_outlier_publishes_remap_only_when_params_change(
    filter_repository,
) -> None:
    filter_repository.create_outlier_rule(
        "credit_score", ComparisonOperation.GT, PercentileOptions.PERC_90
    )
    old_id = next(iter(filter_repository.filters))

    seen_remaps = []
    filter_repository.subscribe(lambda change_ids, remaps: seen_remaps.append(remaps))

    filter_repository.modify_outlier_rule(
        old_id, "credit_score", ComparisonOperation.GT, PercentileOptions.PERC_95
    )

    new_id = next(iter(filter_repository.filters))
    assert new_id != old_id
    assert seen_remaps == [{FilterID: {old_id: new_id}}]

    seen_remaps.clear()
    filter_repository.modify_outlier_rule(
        new_id, "credit_score", ComparisonOperation.GT, PercentileOptions.PERC_95
    )
    assert seen_remaps == [None]


def test_create_outlier_rule_rejects_duplicate_params(filter_repository) -> None:
    filter_repository.create_outlier_rule(
        "credit_score", ComparisonOperation.GT, PercentileOptions.PERC_90
    )

    with pytest.raises(ValueError, match="already exists"):
        filter_repository.create_outlier_rule(
            "credit_score", ComparisonOperation.GT, PercentileOptions.PERC_90
        )


def test_filter_vm_follows_filter_id_remap(data_repository, filter_repository) -> None:
    vm = FilterViewModel(data_repository, filter_repository)
    filter_repository.create_filter("F1", FILTER_QUERY)
    old_id = next(iter(filter_repository.filters))

    vm.set_mode("edit", old_id)
    assert vm.filter_cache.uid == old_id
    assert vm.is_verified

    filter_repository.modify_filter(old_id, "F1 edited", "`credit_score` > 650")

    new_id = next(iter(filter_repository.filters))
    assert vm.filter_cache.uid == new_id
    assert vm.filter_cache.name == "F1 edited"
    assert vm.is_verified


def test_filter_vm_unaffected_by_data_source_remaps(
    data_repository, filter_repository
) -> None:
    vm = FilterViewModel(data_repository, filter_repository)
    filter_repository.create_filter("F1", FILTER_QUERY)
    filter_id = next(iter(filter_repository.filters))

    vm.set_mode("edit", filter_id)
    ds_id = next(iter(data_repository.data_sources))

    data_repository.update_data_source(ds_id, label="Renamed Data")

    assert vm.filter_cache.uid == filter_id
    assert filter_id in filter_repository.filters
    assert vm.is_verified


def test_data_explorer_remaps_iv_filters_on_edit(
    data_repository, filter_repository
) -> None:
    vm = DataExplorerViewModel(data_repository, filter_repository)
    filter_repository.create_filter("F1", FILTER_QUERY)
    old_id = next(iter(filter_repository.filters))

    vm.iv_current_filter_ids = [old_id]
    error = ValueError("boom")
    vm.ol_errors[old_id] = error

    filter_repository.modify_filter(old_id, "F1 edited", "`credit_score` > 650")

    new_id = next(iter(filter_repository.filters))
    assert vm.iv_current_filter_ids == [new_id]
    assert vm.ol_errors == {new_id: error}


def test_data_explorer_keeps_temporary_outlier_errors_through_remap(
    data_repository, filter_repository
) -> None:
    from risc_tool.data.models.uid import FilterID as FID

    vm = DataExplorerViewModel(data_repository, filter_repository)
    filter_repository.create_filter("F1", FILTER_QUERY)
    filter_id = next(iter(filter_repository.filters))
    temporary_error = ValueError("draft")
    saved_error = ValueError("saved")
    vm.ol_errors[FID.TEMPORARY] = temporary_error
    vm.ol_errors[filter_id] = saved_error

    filter_repository.modify_filter(filter_id, "F1 edited", "`income` > 10")

    new_id = next(iter(filter_repository.filters))
    assert vm.ol_errors == {FID.TEMPORARY: temporary_error, new_id: saved_error}
