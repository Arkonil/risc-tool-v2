"""Tests for FilterID reference remapping when filters and outlier rules change.

Filter identities are content-addressed, so editing a filter re-derives
its ID. The repository publishes old->new remaps; dependent components
use them to rewrite stored references.
"""

import pytest

from risc_tool_v2.data.core.uid import FilterID
from risc_tool_v2.ui.data_source.data_explorer.data_explorer_vm import (
    DataExplorerViewModel,
)


def test_create_filter_uses_content_addressed_id(data_repository, filter_repository):
    filter_repository.create_filter("Filter 1", "credit_score > 600")
    filters = filter_repository.get_filters()
    assert len(filters) == 1
    fid = next(iter(filters.keys()))
    assert fid == next(iter(filters.values())).create_hash()


def test_create_filter_rejects_duplicate_content(data_repository, filter_repository):
    filter_repository.create_filter("Filter 1", "credit_score > 600")

    with pytest.raises(ValueError, match="already exists"):
        filter_repository.create_filter("Filter 2", "credit_score > 600")


def test_modify_publishes_remap_only_when_id_changes(
    data_repository, filter_repository
):
    filter_repository.create_filter("Filter 1", "credit_score > 600")
    old_fid = next(iter(filter_repository.filters.keys()))

    seen_remaps = []
    filter_repository.subscribe(lambda change_ids, remaps: seen_remaps.append(remaps))

    # Rename only: new identity.
    filter_repository.modify_filter(
        old_fid, name="Filter 1 Modified", query="credit_score > 650"
    )
    new_fid = next(iter(filter_repository.filters.keys()))
    assert len(filter_repository.filters) == 1
    assert new_fid != old_fid
    assert seen_remaps == [{FilterID: {old_fid: new_fid}}]

    # Re-modifying with identical content keeps the ID: no remap.
    seen_remaps.clear()
    filter_repository.modify_filter(
        new_fid, name="Filter 1 Modified", query="credit_score > 650"
    )
    assert seen_remaps == [None]
    assert next(iter(filter_repository.filters.keys())) == new_fid


def test_modify_preserves_registration_order(data_repository, filter_repository):
    filter_repository.create_filter("First", "credit_score > 600")
    filter_repository.create_filter("Second", "income > 50000")
    first_id = next(iter(filter_repository.filters.keys()))

    filter_repository.modify_filter(
        first_id, name="First Renamed", query="credit_score > 650"
    )

    keys = list(filter_repository.filters.keys())
    assert len(keys) == 2
    assert keys[0] != first_id
    assert filter_repository.filters[keys[0]].name == "First Renamed"
    assert filter_repository.filters[keys[1]].name == "Second"


def test_duplicate_creates_distinct_content_id(data_repository, filter_repository):
    filter_repository.create_filter("Filter 1", "credit_score > 600")
    original_id = next(iter(filter_repository.filters.keys()))
    original = filter_repository.filters[original_id]

    filter_repository.duplicate_filter(original_id)

    assert len(filter_repository.filters) == 2
    assert original_id in filter_repository.filters
    copy = next(f for f in filter_repository.filters.values() if f is not original)
    assert copy.uid != original_id
    assert copy.name != original.name


def test_outlier_rule_recalculation_keeps_repo_identity(
    data_repository, filter_repository
):
    """Recalculating thresholds doesn't change the outlier rule's identity."""
    filter_repository.create_outlier_rule(
        variable_name="income",
        comparison_op=">",
        comparison_base="PERC_99",
    )
    outlier_id = next(
        fid for fid, f in filter_repository.filters.items() if f.is_outlier
    )
    original_uid = filter_repository.filters[outlier_id].uid

    # Recalculate with same data - identity should stay the same
    lf = data_repository.get_lazyframe(limit_per_source=10)
    filter_repository.filters[outlier_id].recalculate_thresholds(lf)

    # Identity preserved because parameters didn't change
    assert filter_repository.filters[outlier_id].uid == original_uid


def test_modify_outlier_publishes_remap_only_when_params_change(
    data_repository, filter_repository
):
    filter_repository.create_outlier_rule(
        variable_name="income",
        comparison_op=">",
        comparison_base="PERC_99",
    )
    old_oid = next(fid for fid, f in filter_repository.filters.items() if f.is_outlier)

    seen_remaps = []
    filter_repository.subscribe(lambda change_ids, remaps: seen_remaps.append(remaps))

    # Change comparison base: new identity.
    filter_repository.modify_outlier_rule(
        old_oid, variable_name="income", comparison_op=">", comparison_base="PERC_95"
    )
    new_oid = next(fid for fid, f in filter_repository.filters.items() if f.is_outlier)
    assert len(filter_repository.filters) == 1
    assert new_oid != old_oid
    assert seen_remaps == [{FilterID: {old_oid: new_oid}}]

    # Re-modifying with identical parameters keeps the ID: no remap.
    seen_remaps.clear()
    filter_repository.modify_outlier_rule(
        new_oid, variable_name="income", comparison_op=">", comparison_base="PERC_95"
    )
    assert seen_remaps == [None]
    assert (
        next(fid for fid, f in filter_repository.filters.items() if f.is_outlier)
        == new_oid
    )


def test_create_outlier_rule_rejects_duplicate_params(
    data_repository, filter_repository
):
    filter_repository.create_outlier_rule(
        variable_name="income",
        comparison_op=">",
        comparison_base="PERC_99",
    )

    with pytest.raises(ValueError, match="already exists"):
        filter_repository.create_outlier_rule(
            variable_name="income",
            comparison_op=">",
            comparison_base="PERC_99",
        )


def test_filter_vm_follows_filter_id_remap(data_repository, filter_repository):
    from risc_tool_v2.ui.filter.filter_editor.filter_vm import FilterViewModel

    vm = FilterViewModel(data_repository, filter_repository)

    # Create filter
    filter_repository.create_filter("Filter 1", "credit_score > 600")
    fid = next(iter(filter_repository.filters.keys()))

    # Load into VM
    vm.set_mode("edit", fid)
    assert vm.filter_cache.uid == fid

    # Modify filter in repo -> ID changes -> VM adopts
    filter_repository.modify_filter(
        fid, name="Filter 1 Modified", query="credit_score > 650"
    )
    new_fid = next(iter(filter_repository.filters.keys()))
    assert new_fid != fid

    assert vm.filter_cache.uid == new_fid


def test_filter_vm_unaffected_by_data_source_remaps(data_repository, filter_repository):

    from risc_tool_v2.ui.filter.filter_editor.filter_vm import FilterViewModel

    vm = FilterViewModel(data_repository, filter_repository)
    filter_repository.create_filter("Filter 1", "credit_score > 600")
    fid = next(iter(filter_repository.filters.keys()))

    vm.set_mode("edit", fid)
    assert vm.filter_cache.uid == fid

    # Data source edit shouldn't affect filter (filters reference columns by name)
    old_ds_id = next(iter(data_repository.data_sources.keys()))
    data_repository.update_data_source(old_ds_id, label="Renamed Data Source")

    # Filter VM should still have the same filter (no remap needed)
    assert vm.filter_cache.uid == fid


def test_data_explorer_remaps_iv_filters_on_edit(data_repository, filter_repository):
    vm = DataExplorerViewModel(data_repository, filter_repository)
    filter_repository.create_filter("Filter 1", "credit_score > 600")
    fid = next(iter(filter_repository.filters.keys()))
    vm.iv_current_filter_ids = [fid]

    # Modify filter in repo -> ID changes
    filter_repository.modify_filter(
        fid, name="Filter 1 Modified", query="credit_score > 650"
    )
    new_fid = next(iter(filter_repository.filters.keys()))

    assert vm.iv_current_filter_ids == [new_fid]
    assert fid not in vm.iv_current_filter_ids


def test_data_explorer_keeps_temporary_outlier_errors_through_remap(
    data_repository, filter_repository
):
    from risc_tool_v2.data.core.uid import FilterID
    from risc_tool_v2.ui.data_source.data_explorer.data_explorer_vm import (
        DataExplorerViewModel,
    )

    vm = DataExplorerViewModel(data_repository, filter_repository)

    # Create an outlier rule
    filter_repository.create_outlier_rule(
        variable_name="income",
        comparison_op=">",
        comparison_base="PERC_99",
    )
    oid = next(fid for fid, f in filter_repository.filters.items() if f.is_outlier)

    # Simulate a validation error on a temporary outlier
    vm.ol_errors[FilterID.TEMPORARY] = ValueError("temp error")

    # Modify the outlier -> ID changes
    filter_repository.modify_outlier_rule(
        oid, variable_name="income", comparison_op=">", comparison_base="PERC_95"
    )
    new_oid = next(fid for fid, f in filter_repository.filters.items() if f.is_outlier)

    # TEMPORARY error should remain (not remappable)
    assert FilterID.TEMPORARY in vm.ol_errors
    # But the specific outlier error should be remapped
    assert oid not in vm.ol_errors
    assert new_oid in vm.ol_errors
    assert vm.ol_errors[new_oid] is vm.ol_errors[FilterID.TEMPORARY]
