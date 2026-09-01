from pathlib import Path
from typing import Any, cast

import pytest

from risc_tool.data.models.data_source import ReadConfig
from risc_tool.data.models.exceptions import MissingColumnError
from risc_tool.data.models.uid import DataSourceID
from risc_tool.data.repositories.data import DataRepository
from risc_tool.data.repositories.metric import MetricRepository
from risc_tool.ui.components.variable_selector_vm import VariableSelectorViewModel


def write_csv(path: Path, contents: str) -> None:
    path.write_text(contents, encoding="utf-8")


def _make_csv_pair(tmp_path: Path) -> tuple[Path, Path]:
    csv_a = tmp_path / "dev.csv"
    csv_b = tmp_path / "tst.csv"
    write_csv(
        csv_a,
        "id,num_col,cat_col,unt_bad,dlr_bad,avg_bal\n1,10.0,A,100,1000,500\n2,20.0,B,200,2000,1000\n",
    )
    write_csv(
        csv_b,
        "id,num_col,cat_col,unt_bad,dlr_bad,avg_bal\n3,30.0,A,300,3000,1500\n4,40.0,B,400,4000,2000\n",
    )
    return csv_a, csv_b


def _make_repos_and_vm(
    tmp_path: Path,
) -> tuple[DataRepository, MetricRepository, VariableSelectorViewModel]:
    csv_a, csv_b = _make_csv_pair(tmp_path)
    data_repo = DataRepository()
    data_repo.add_data_source("dev_src", csv_a, ReadConfig())
    data_repo.add_data_source("tst_src", csv_b, ReadConfig())
    metric_repo = MetricRepository(data_repo)
    vm = VariableSelectorViewModel(data_repo, metric_repo)
    return data_repo, metric_repo, vm


class TestVariableSelectorViewModel:
    def test_initial_state_no_data_sources(self):
        data_repo = DataRepository()
        metric_repo = MetricRepository(data_repo)
        vm = VariableSelectorViewModel(data_repo, metric_repo)

        assert vm.all_data_source_ids == []
        assert vm.selected_data_source_ids("dev") == []
        assert vm.selected_data_source_ids("tst") == []

        assert vm.get_variable("dev", "unt_bad") is None
        assert vm.get_variable("dev", "dlr_bad") is None
        assert vm.get_variable("dev", "avg_bal") is None
        assert vm.get_variable("tst", "unt_bad") is None
        assert vm.get_variable("tst", "dlr_bad") is None
        assert vm.get_variable("tst", "avg_bal") is None

        assert vm.get_mob("current") == 12
        assert vm.get_mob("lifetime") == 36

    def test_all_data_source_ids(self, tmp_path: Path):
        _, _, vm = _make_repos_and_vm(tmp_path)
        ids = vm.all_data_source_ids
        assert len(ids) == 2

    def test_get_data_source_label(self, tmp_path: Path):
        _, _, vm = _make_repos_and_vm(tmp_path)
        ids = vm.all_data_source_ids
        assert vm.get_data_source_label(ids[0]) == "dev_src"
        assert vm.get_data_source_label(ids[1]) == "tst_src"

    def test_get_data_source_label_unknown_id(self, tmp_path: Path):
        _, _, vm = _make_repos_and_vm(tmp_path)
        with pytest.raises(KeyError):
            vm.get_data_source_label(DataSourceID(9999))

    def test_set_data_source_ids_dev(self, tmp_path: Path):
        _, _, vm = _make_repos_and_vm(tmp_path)
        ids = vm.all_data_source_ids

        vm.set_data_source_ids("dev", [ids[0]])
        assert vm.selected_data_source_ids("dev") == [ids[0]]
        assert vm.selected_data_source_ids("tst") == []

        vm.set_data_source_ids("dev", ids)
        assert vm.selected_data_source_ids("dev") == ids

        vm.set_data_source_ids("dev", [])
        assert vm.selected_data_source_ids("dev") == []

    def test_set_data_source_ids_tst(self, tmp_path: Path):
        _, _, vm = _make_repos_and_vm(tmp_path)
        ids = vm.all_data_source_ids

        vm.set_data_source_ids("tst", [ids[1]])
        assert vm.selected_data_source_ids("tst") == [ids[1]]
        assert vm.selected_data_source_ids("dev") == []

    def test_set_data_source_ids_invalid_type(self, tmp_path: Path):
        _, _, vm = _make_repos_and_vm(tmp_path)
        ids = vm.all_data_source_ids
        invalid = cast(Any, "invalid")

        with pytest.raises(ValueError, match="Invalid data source type"):
            vm.set_data_source_ids(invalid, ids)

    def test_selected_data_source_ids_invalid_type(self, tmp_path: Path):
        _, _, vm = _make_repos_and_vm(tmp_path)
        invalid = cast(Any, "invalid")
        with pytest.raises(ValueError, match="Invalid data source type"):
            vm.selected_data_source_ids(invalid)

    def test_get_variable_defaults(self, tmp_path: Path):
        _, _, vm = _make_repos_and_vm(tmp_path)

        assert vm.get_variable("dev", "unt_bad") is None
        assert vm.get_variable("dev", "dlr_bad") is None
        assert vm.get_variable("dev", "avg_bal") is None
        assert vm.get_variable("tst", "unt_bad") is None
        assert vm.get_variable("tst", "dlr_bad") is None
        assert vm.get_variable("tst", "avg_bal") is None

    def test_get_variable_invalid(self, tmp_path: Path):
        _, _, vm = _make_repos_and_vm(tmp_path)
        invalid = cast(Any, "invalid")

        with pytest.raises(ValueError, match="Invalid data source type"):
            vm.get_variable(invalid, "unt_bad")
        with pytest.raises(ValueError, match="Invalid data source type or usage"):
            vm.get_variable("dev", invalid)

    def test_set_and_get_variable(self, tmp_path: Path):
        _, _, vm = _make_repos_and_vm(tmp_path)
        ids = vm.all_data_source_ids
        vm.set_data_source_ids("dev", ids)
        vm.set_data_source_ids("tst", ids)

        vm.set_variable("dev", "unt_bad", "unt_bad")
        assert vm.get_variable("dev", "unt_bad") == "unt_bad"

        vm.set_variable("dev", "dlr_bad", "dlr_bad")
        assert vm.get_variable("dev", "dlr_bad") == "dlr_bad"

        vm.set_variable("dev", "avg_bal", "avg_bal")
        assert vm.get_variable("dev", "avg_bal") == "avg_bal"

        vm.set_variable("tst", "unt_bad", "unt_bad")
        assert vm.get_variable("tst", "unt_bad") == "unt_bad"

        vm.set_variable("tst", "dlr_bad", "dlr_bad")
        assert vm.get_variable("tst", "dlr_bad") == "dlr_bad"

        vm.set_variable("tst", "avg_bal", "avg_bal")
        assert vm.get_variable("tst", "avg_bal") == "avg_bal"

    def test_set_variable_to_none(self, tmp_path: Path):
        _, _, vm = _make_repos_and_vm(tmp_path)
        ids = vm.all_data_source_ids
        vm.set_data_source_ids("dev", ids)

        vm.set_variable("dev", "unt_bad", "unt_bad")
        assert vm.get_variable("dev", "unt_bad") == "unt_bad"

        vm.set_variable("dev", "unt_bad", None)
        assert vm.get_variable("dev", "unt_bad") is None

    def test_set_variable_invalid_ds_type(self, tmp_path: Path):
        _, _, vm = _make_repos_and_vm(tmp_path)
        invalid = cast(Any, "invalid")
        with pytest.raises(ValueError, match="Invalid data source type or usage"):
            vm.set_variable(invalid, "unt_bad", "x")

    def test_set_variable_invalid_usage(self, tmp_path: Path):
        _, _, vm = _make_repos_and_vm(tmp_path)
        invalid = cast(Any, "invalid")
        with pytest.raises(ValueError, match="Invalid data source type or usage"):
            vm.set_variable("dev", invalid, "x")

    def test_set_variable_unknown_column_raises(self, tmp_path: Path):
        _, _, vm = _make_repos_and_vm(tmp_path)
        ids = vm.all_data_source_ids
        vm.set_data_source_ids("dev", ids)

        with pytest.raises(MissingColumnError, match="nonexistent_col"):
            vm.set_variable("dev", "unt_bad", "nonexistent_col")

    def test_get_mob_defaults(self, tmp_path: Path):
        _, _, vm = _make_repos_and_vm(tmp_path)
        assert vm.get_mob("current") == 12
        assert vm.get_mob("lifetime") == 36

    def test_get_mob_invalid_type(self, tmp_path: Path):
        _, _, vm = _make_repos_and_vm(tmp_path)
        invalid = cast(Any, "invalid")
        assert vm.get_mob(invalid) is None

    def test_set_and_get_mob(self, tmp_path: Path):
        _, _, vm = _make_repos_and_vm(tmp_path)

        vm.set_mob("current", 6)
        assert vm.get_mob("current") == 6
        assert vm.get_mob("lifetime") == 36

        vm.set_mob("lifetime", 24)
        assert vm.get_mob("current") == 6
        assert vm.get_mob("lifetime") == 24

        vm.set_mob("current", 1)
        assert vm.get_mob("current") == 1

        vm.set_mob("lifetime", 100)
        assert vm.get_mob("lifetime") == 100

    def test_get_available_columns(self, tmp_path: Path):
        _, _, vm = _make_repos_and_vm(tmp_path)
        ids = vm.all_data_source_ids
        vm.set_data_source_ids("dev", ids)

        columns = vm.get_available_columns("dev")
        assert columns[0] is None
        assert "num_col" in columns
        assert "unt_bad" in columns
        assert "dlr_bad" in columns
        assert "avg_bal" in columns
        assert "cat_col" not in columns

    def test_get_available_columns_no_sources(self, tmp_path: Path):
        data_repo = DataRepository()
        metric_repo = MetricRepository(data_repo)
        vm = VariableSelectorViewModel(data_repo, metric_repo)

        columns = vm.get_available_columns("dev")
        assert columns == [None]

    def test_get_available_columns_invalid_ds_type(self, tmp_path: Path):
        _, _, vm = _make_repos_and_vm(tmp_path)
        invalid = cast(Any, "invalid")
        with pytest.raises(ValueError, match="Invalid data source type"):
            vm.get_available_columns(invalid)

    def test_signature(self, tmp_path: Path):
        _, _, vm = _make_repos_and_vm(tmp_path)
        assert vm.signature.value == "VARIABLE_SELECTOR_VIEW_MODEL"

    def test_on_dependency_update_noop(self, tmp_path: Path):
        _, _, vm = _make_repos_and_vm(tmp_path)
        assert vm.on_dependency_update(set()) is None
