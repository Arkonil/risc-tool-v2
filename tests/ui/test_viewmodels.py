from risc_tool_v2.data.data_source.models.data_source import ReadConfig
from risc_tool_v2.ui.data_source.data_explorer.data_explorer_vm import (
    DataExplorerViewModel,
)
from risc_tool_v2.ui.data_source.data_importer.data_importer_vm import (
    DataImporterViewModel,
)
from risc_tool_v2.ui.filter.filter_editor.filter_vm import FilterViewModel
from risc_tool_v2.ui.metric.metric_editor.metric_vm import MetricViewModel


def test_data_importer_vm(data_repository, sample_csv):
    vm = DataImporterViewModel(data_repository)
    assert not vm.is_empty

    first_ds_id = next(iter(data_repository.data_sources.keys()))
    vm.update_data_source(
        data_source_id=first_ds_id,
        filepath=sample_csv,
        label="Updated Dev",
        read_config=ReadConfig(),
    )


def test_data_explorer_vm(data_repository, filter_repository):
    vm = DataExplorerViewModel(data_repository, filter_repository)
    assert vm.data_loaded

    # Test IV DataFrame computation
    ds_ids = list(data_repository.data_sources.keys())
    vm.iv_data_sources = ds_ids
    df = vm.get_iv_df(
        target_variable="unt_bad", input_variables=["credit_score", "income"]
    )
    assert df is not None
    assert df.height == 2


def test_filter_vm_crud(data_repository, filter_repository):
    vm = FilterViewModel(data_repository, filter_repository)
    vm.set_mode("edit")
    vm.set_filter_property(name="High Income", query="income > 60000")
    vm.validate_filter("High Income", "income > 60000", "test_id")
    assert vm.is_verified
    vm.save_filter()

    assert len(filter_repository.filters) == 1


def test_metric_vm_crud(data_repository, metric_repository):
    vm = MetricViewModel(data_repository, metric_repository)
    vm.set_mode("edit")
    ds_ids = list(data_repository.data_sources.keys())
    vm.selected_data_source_ids = ds_ids
    vm.set_metric_property(name="Mean Score", query="credit_score.mean()")
    vm.validate_metric("Mean Score", "credit_score.mean()", "test_id")
    assert vm.is_verified
    vm.save_metric()

    assert len(metric_repository.metrics) == 1
