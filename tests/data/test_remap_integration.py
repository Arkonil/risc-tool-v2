from risc_tool_v2.data.core.uid import DataSourceID, FilterID
from risc_tool_v2.ui.data_source.data_explorer.data_explorer_vm import (
    DataExplorerViewModel,
)
from risc_tool_v2.ui.filter.filter_editor.filter_vm import FilterViewModel
from risc_tool_v2.ui.metric.metric_editor.metric_vm import MetricViewModel


def test_filter_remap_flow(data_repository, filter_repository):
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


def test_filter_vm_draft_resets_on_dependency_update(
    data_repository, filter_repository
):
    """Unsaved drafts carry no derived identity and follow the filters
    convention: any dependency update resets the editor placeholder."""
    vm = FilterViewModel(data_repository, filter_repository)
    vm.set_mode("edit")
    assert vm.filter_cache.uid is FilterID.EMPTY

    data_repository.update_data_source(
        next(iter(data_repository.data_sources)), label="Renamed Data"
    )

    assert vm.filter_cache.uid is FilterID.EMPTY
    assert vm.filter_cache.query == ""
    assert vm.is_verified is False


def test_filter_vm_saved_edit_survives_dependency_updates(
    data_repository, filter_repository
):
    vm = FilterViewModel(data_repository, filter_repository)
    filter_repository.create_filter("Filter 1", "credit_score > 600")
    fid = next(iter(filter_repository.filters.keys()))

    vm.set_mode("edit", fid)

    data_repository.update_data_source(
        next(iter(data_repository.data_sources)), label="Renamed Data"
    )

    new_fid = next(iter(filter_repository.filters.keys()))
    assert vm.filter_cache.uid == new_fid
    assert vm.is_verified


def test_metric_chained_remap_flow(data_repository, metric_repository, sample_csv):

    vm = MetricViewModel(data_repository, metric_repository)

    ds_ids = list(data_repository.data_sources.keys())
    metric_repository.create_metric(
        name="Bad Rate",
        query="unt_bad.sum() / unt_bad.size",
        is_cumulative=False,
        use_thousand_sep=False,
        is_percentage=True,
        decimal_places=2,
        data_source_ids=ds_ids,
    )
    mid = next(iter(metric_repository.metrics.keys()))

    vm.set_mode("edit", mid)
    assert vm.metric_cache.uid == mid

    # Edit data source -> DataSourceID changes -> chains into MetricID change -> VM adopts
    old_ds_id = ds_ids[0]
    data_repository.update_data_source(old_ds_id, label="Renamed Data Source")

    new_ds_id = next(iter(data_repository.data_sources.keys()))
    assert new_ds_id != old_ds_id

    new_mid = next(iter(metric_repository.metrics.keys()))
    assert new_mid != mid
    assert vm.metric_cache.uid == new_mid


def test_data_explorer_iv_remap_merged_payload(
    data_repository, filter_repository, metric_repository
):
    """Verify merged {DataSourceID, FilterID} payload when both remap."""

    vm = DataExplorerViewModel(data_repository, filter_repository)

    # Setup: create filter and select it for IV
    filter_repository.create_filter("IV Filter", "credit_score > 600")
    fid = next(iter(filter_repository.filters.keys()))
    vm.iv_data_sources = list(data_repository.data_sources.keys())
    vm.iv_current_filter_ids = [fid]
    vm.iv_current_target = "unt_bad"
    vm.iv_current_variables = ["credit_score"]

    # Track remaps published by filter_repository
    seen_remaps = []
    filter_repository.subscribe(lambda change_ids, remaps: seen_remaps.append(remaps))

    # Edit data source -> DataSourceID changes
    old_ds_id = next(iter(data_repository.data_sources.keys()))
    updated = data_repository.update_data_source(old_ds_id, label="Renamed DS")
    new_ds_id = updated.uid

    # Filter repo should emit chained remap: {DataSourceID: {old->new}, FilterID: {old->new}}
    assert seen_remaps
    remap = seen_remaps[-1]
    assert DataSourceID in remap
    assert old_ds_id in remap[DataSourceID]
    assert remap[DataSourceID][old_ds_id] == new_ds_id
    # Filter repo may also emit FilterID remap if filter was affected
    # (in this case filters reference columns by name, so not affected)

    # Now also modify filter to trigger FilterID remap
    seen_remaps.clear()
    fid = next(iter(filter_repository.filters.keys()))
    filter_repository.modify_filter(fid, name="Modified", query="credit_score > 650")
    new_fid = next(iter(filter_repository.filters.keys()))

    remap = seen_remaps[-1]
    assert FilterID in remap
    assert remap[FilterID][fid] == new_fid


def test_outlier_vm_follows_filter_id_remap(data_repository, filter_repository):
    """Outlier rules are filters; their VM should follow FilterID remaps."""
    from risc_tool_v2.ui.filter.filter_editor.filter_vm import FilterViewModel

    vm = FilterViewModel(data_repository, filter_repository)

    # Create outlier rule
    filter_repository.create_outlier_rule(
        variable_name="income",
        comparison_op=">",
        comparison_base="PERC_99",
    )
    oid = next(fid for fid, f in filter_repository.filters.items() if f.is_outlier)

    vm.set_mode("edit", oid)
    assert vm.filter_cache.uid == oid

    # Modify outlier -> ID changes -> VM adopts
    filter_repository.modify_outlier_rule(
        oid, variable_name="income", comparison_op=">", comparison_base="PERC_95"
    )
    new_oid = next(fid for fid, f in filter_repository.filters.items() if f.is_outlier)
    assert new_oid != oid

    assert vm.filter_cache.uid == new_oid
    assert vm.is_verified
