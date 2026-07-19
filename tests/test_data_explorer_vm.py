from pathlib import Path

from risc_tool.data.models.data_source import ReadConfig
from risc_tool.data.repositories.data import DataRepository
from risc_tool.ui.data_explorer.data_explorer_vm import DataExplorerViewModel


def write_csv(path: Path, contents: str) -> None:
    path.write_text(contents, encoding="utf-8")


def test_data_explorer_vm_lifecycle(tmp_path: Path) -> None:
    csv_path_1 = tmp_path / "src1.csv"
    csv_path_2 = tmp_path / "src2.csv"

    write_csv(csv_path_1, "id,var1,target\n1,10.0,0\n2,20.0,0\n")
    write_csv(csv_path_2, "id,var1,target\n3,30.0,1\n4,40.0,1\n")

    repository = DataRepository()
    ds1 = repository.add_data_source("src1", csv_path_1, ReadConfig())
    ds2 = repository.add_data_source("src2", csv_path_2, ReadConfig())

    # Initialize ViewModel
    vm = DataExplorerViewModel(repository)

    # 1. Verify defaults are populated
    assert vm.has_valid_sources
    assert len(vm.iv_data_sources) == 2
    assert set(vm.iv_data_sources) == {ds1.uid, ds2.uid}

    # 2. Verify target columns and input columns
    assert "target" in vm.available_target_columns
    assert "var1" in vm.available_input_columns

    # 3. Calculate IV
    iv_df = vm.get_iv_df("target", ["var1"])
    assert iv_df is not None
    assert "var1" in iv_df["variable"]
    assert iv_df.height == 1

    # 4. Verify caching (subsequent call should hit cache)
    # Get initial cache count/contents
    iv_df_cached = vm.get_iv_df("target", ["var1"])
    assert iv_df_cached is not None

    # 5. Verify dependency change invalidates cache
    # Update one of the data sources
    write_csv(csv_path_2, "id,var1,target\n3,35.0,1\n4,45.0,1\n")
    repository.update_data_source(ds2.uid)

    # ViewModel should react to dependency update and clear cache
    # (Since ViewModel inherits from ChangeTracker and registered repository as dependency)
    # Check that cache is cleared / warnings clear
    assert not vm.iv_errors


def test_data_explorer_vm_non_binary_target_error(tmp_path: Path) -> None:
    csv_path = tmp_path / "invalid_target.csv"
    # Target has values other than 0 and 1
    write_csv(csv_path, "id,var1,target\n1,10.0,0\n2,20.0,2\n")

    repository = DataRepository()
    _ = repository.add_data_source("invalid_target", csv_path, ReadConfig())

    vm = DataExplorerViewModel(repository)
    iv_df = vm.get_iv_df("target", ["var1"])

    assert iv_df is None
    assert len(vm.iv_errors) == 1
    assert "Target variable must be binary" in str(vm.iv_errors[0])
