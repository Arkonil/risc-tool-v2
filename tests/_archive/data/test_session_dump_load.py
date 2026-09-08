"""Tests for the Session JSON dump and load feature.

Covers the full export/import pipeline:
    Session.to_dict() -> SessionJSON -> model_dump_json (dump)
    model_validate_json -> Session.rebuild_from_json (load)

plus the backend portions of the import UI (HomeViewModel), schema
validation errors, data source corrections, and column validation.
"""

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from risc_tool.data.models.data_source import DataSource, ReadConfig
from risc_tool.data.models.enums import IterationType, LossRateTypes, VariableType
from risc_tool.data.models.json_models import SessionJSON
from risc_tool.data.models.uid import (
    DataSourceID,
    FilterID,
    MetricID,
    RiskSegmentID,
)
from risc_tool.data.session import Session
from risc_tool.ui.home.home_vm import HomeViewModel


def _write_csv(path: Path, contents: str) -> None:
    path.write_text(contents, encoding="utf-8")


def _make_csv(tmp_path: Path) -> Path:
    csv_path = tmp_path / "data.csv"
    _write_csv(
        csv_path,
        (
            "credit_score,income,age,employment_status,credit_default_flag,"
            "credit_default_amount,average_balance\n"
            "700,50000,35,Employed,1,3404.78,6497.22\n"
            "600,40000,40,Employed,0,0.0,8719.34\n"
            "750,60000,30,Self-employed,1,1200.00,2500.00\n"
            "650,45000,50,Employed,0,0.0,5000.00\n"
        ),
    )
    return csv_path


class _FakeUploadedFile:
    """Minimal stand-in for streamlit's UploadedFile."""

    def __init__(self, name: str, content: bytes) -> None:
        self.name = name
        self._content = content
        self._read_count = 0

    def read(self) -> bytes:
        self._read_count += 1
        return self._content


def _make_loaded_session(tmp_path: Path) -> Session:
    csv_path = _make_csv(tmp_path)
    session = Session()

    session.data_repository.add_data_source("Dev Data", csv_path, ReadConfig())
    ds_ids = list(session.data_repository.data_sources.keys())

    # Metric repository variables used by the default metrics.
    metric_repo = session.metric_repository
    metric_repo.dev_data_source_ids = ds_ids
    metric_repo.tst_data_source_ids = ds_ids
    metric_repo.var_dev_dlr_bad = "credit_default_flag"
    metric_repo.var_dev_avg_bal = "average_balance"
    metric_repo.var_dev_unt_bad = "credit_default_flag"
    metric_repo.var_tst_dlr_bad = "credit_default_flag"
    metric_repo.var_tst_avg_bal = "average_balance"
    metric_repo.var_tst_unt_bad = "credit_default_flag"
    metric_repo.current_rate_mob = 12
    metric_repo.lifetime_rate_mob = 36

    metric_repo.create_metric(
        name="Avg Credit Score",
        query="`credit_score`.mean()",
        is_cumulative=False,
        use_thousand_sep=True,
        is_percentage=False,
        decimal_places=2,
        data_source_ids=ds_ids,
    )

    session.filter_repository.create_filter("Score Filter", "`credit_score` > 500")

    session.scalar_repository.set_current_rate(LossRateTypes.DLR, 0.05)
    session.scalar_repository.set_lifetime_rate(LossRateTypes.DLR, 0.15)

    session.option_repository.set_risk_seg_name(RiskSegmentID(0), "Custom1")

    iterations_vm = session.iterations_view_model
    single = iterations_vm.add_single_var_iteration(
        name="Credit Score Iteration",
        variable_name="credit_score",
        variable_dtype=VariableType.NUMERICAL,
        selected_segment_ids=[RiskSegmentID(0), RiskSegmentID(1), RiskSegmentID(2)],
        loss_rate_type=LossRateTypes.DLR,
        filter_ids=[],
        auto_band=False,
        use_scalar=False,
        remove_outliers=False,
    )
    iterations_vm.add_double_var_iteration(
        name="Income Double Iteration",
        previous_iteration_id=single.uid,
        variable_name="income",
        variable_dtype=VariableType.NUMERICAL,
        auto_band=False,
        use_scalar=False,
        remove_outliers=False,
    )
    iterations_vm.add_single_var_iteration(
        name="Employment Iteration",
        variable_name="employment_status",
        variable_dtype=VariableType.CATEGORICAL,
        selected_segment_ids=[RiskSegmentID(0), RiskSegmentID(1), RiskSegmentID(2)],
        loss_rate_type=LossRateTypes.DLR,
        filter_ids=[],
        auto_band=False,
        use_scalar=False,
        remove_outliers=False,
    )

    summary_vm = session.summary_view_model
    summary_vm.set_overview_metrics([MetricID.DEV_VOLUME])
    summary_vm.set_comparison_metrics([MetricID.DEV_DLR_BAD_RATE])
    summary_vm.add_iteration_view(single.uid, True)
    summary_vm.set_pivot_metrics([MetricID.DEV_VOLUME])
    summary_vm.set_pivot_variables("row", ["credit_score"])
    summary_vm.set_pivot_variables("col", ["income"])

    data_explorer_vm = session.data_explorer_view_model
    data_explorer_vm.iv_data_sources = ds_ids
    data_explorer_vm.iv_current_target = "credit_score"
    data_explorer_vm.iv_current_variables = ["income", "age"]
    data_explorer_vm.iv_current_filter_ids = list(
        session.filter_repository.filters.keys()
    )
    data_explorer_vm.iv_remove_outliers = False

    return session


def _dump_bytes(session: Session) -> bytes:
    return session.to_dict().model_dump_json(indent=2).encode("utf-8")


def _json_dict(session: Session) -> dict:
    return session.to_dict().model_dump(mode="json")


def _restore_session(json_bytes: bytes | str) -> Session:
    session_json = SessionJSON.model_validate_json(json_bytes)
    restored = Session()
    restored.rebuild_from_json(session_json)
    return restored


@pytest.fixture
def loaded_session(tmp_path) -> Session:
    return _make_loaded_session(tmp_path)


# ---------------------------------------------------------------------------
# Dump / load round trips
# ---------------------------------------------------------------------------


def test_empty_session_json_roundtrip():
    original = Session()

    restored = _restore_session(_dump_bytes(original))

    assert restored.to_dict().model_dump() == original.to_dict().model_dump()


def test_full_session_json_roundtrip(loaded_session):
    restored = _restore_session(_dump_bytes(loaded_session))

    assert restored.to_dict().model_dump() == loaded_session.to_dict().model_dump()


def test_roundtrip_preserves_identifiers_and_graph(loaded_session):
    restored = _restore_session(_dump_bytes(loaded_session))

    assert set(restored.data_repository.data_sources) == set(
        loaded_session.data_repository.data_sources
    )
    assert set(restored.filter_repository.filters) == set(
        loaded_session.filter_repository.filters
    )
    assert set(restored.iterations_repository.iterations) == set(
        loaded_session.iterations_repository.iterations
    )
    assert (
        restored.iterations_repository.graph.connections
        == loaded_session.iterations_repository.graph.connections
    )


def test_roundtrip_preserves_user_defined_metric(loaded_session):
    restored = _restore_session(_dump_bytes(loaded_session))

    assert (
        restored.metric_repository.to_dict()
        == loaded_session.metric_repository.to_dict()
    )


def test_roundtrip_preserves_scalars_and_options(loaded_session):
    restored = _restore_session(_dump_bytes(loaded_session))

    assert (
        restored.scalar_repository.get_scalar(LossRateTypes.DLR).current_rate
        == loaded_session.scalar_repository.get_scalar(LossRateTypes.DLR).current_rate
    )
    assert (
        restored.scalar_repository.get_scalar(LossRateTypes.DLR).lifetime_rate
        == loaded_session.scalar_repository.get_scalar(LossRateTypes.DLR).lifetime_rate
    )
    assert (
        restored.option_repository.segments[RiskSegmentID(0)].name
        == loaded_session.option_repository.segments[RiskSegmentID(0)].name
    )


def test_roundtrip_preserves_summary_state(loaded_session):
    restored = _restore_session(_dump_bytes(loaded_session))

    assert restored.summary_view_model.ov_metric_ids == [MetricID.DEV_VOLUME]
    assert restored.summary_view_model.cv_metric_ids == [MetricID.DEV_DLR_BAD_RATE]
    assert restored.summary_view_model.cv_selected_iterations == (
        loaded_session.summary_view_model.cv_selected_iterations
    )
    assert restored.summary_view_model.pv_metric_ids == [MetricID.DEV_VOLUME]
    assert restored.summary_view_model.pv_row_vars == ["credit_score"]
    assert restored.summary_view_model.pv_col_vars == ["income"]


def test_roundtrip_preserves_data_explorer_state(loaded_session):
    restored = _restore_session(_dump_bytes(loaded_session))

    original_de = loaded_session.data_explorer_view_model
    restored_de = restored.data_explorer_view_model

    assert restored_de.iv_data_sources == original_de.iv_data_sources
    assert restored_de.iv_current_target == original_de.iv_current_target
    assert restored_de.iv_current_variables == original_de.iv_current_variables
    assert restored_de.iv_current_filter_ids == original_de.iv_current_filter_ids
    assert restored_de.iv_remove_outliers == original_de.iv_remove_outliers


def test_dump_is_valid_json_document(loaded_session):
    dumped = _dump_bytes(loaded_session)
    parsed = json.loads(dumped)

    assert set(parsed) == {
        "data_repository",
        "filter_repository",
        "metric_repository",
        "scalar_repository",
        "options_repository",
        "iterations_repository",
        "iterations_view_model",
        "summary_view_model",
        "data_explorer_view_model",
    }


def test_roundtrip_via_uploaded_file_ui_path(loaded_session):
    home_vm = HomeViewModel()
    home_vm.uploaded_file = _FakeUploadedFile(
        "session_archive.json", _dump_bytes(loaded_session)
    )

    _, validated = home_vm.get_jsons()

    (
        invalid_filters,
        invalid_metrics,
        missing_metric_variables,
        invalid_iterations,
        missing_data_explorer_variables,
        missing_summary_variables,
    ) = home_vm.validate_columns()

    assert invalid_filters == {}
    assert invalid_metrics == {}
    assert missing_metric_variables == []
    assert invalid_iterations == {}
    assert missing_data_explorer_variables == []
    assert missing_summary_variables == []

    restored = Session()
    restored.rebuild_from_json(validated)

    assert restored.to_dict().model_dump() == loaded_session.to_dict().model_dump()


def test_restore_does_not_mutate_original_session(loaded_session):
    original_dump = loaded_session.to_dict().model_dump()

    restored = _restore_session(_dump_bytes(loaded_session))
    restored.filter_repository.create_filter("New Filter", "`age` > 30")

    assert loaded_session.to_dict().model_dump() == original_dump


# ---------------------------------------------------------------------------
# Schema validation errors
# ---------------------------------------------------------------------------


def test_invalid_json_raises_validation_error():
    with pytest.raises(ValidationError):
        SessionJSON.model_validate_json("{not valid json")


def test_get_jsons_raises_on_invalid_json(loaded_session):
    home_vm = HomeViewModel()
    home_vm.uploaded_file = _FakeUploadedFile("bad.json", b"not valid json")

    with pytest.raises(ValidationError):
        home_vm.get_jsons()


def test_missing_top_level_field_raises_validation_error(loaded_session):
    dumped = _json_dict(loaded_session)
    del dumped["scalar_repository"]

    with pytest.raises(ValidationError):
        SessionJSON.model_validate_json(json.dumps(dumped))


def test_wrong_field_type_raises_validation_error(loaded_session):
    dumped = _json_dict(loaded_session)
    dumped["summary_view_model"]["ov_scalars_enabled"] = "not-a-bool"

    with pytest.raises(ValidationError):
        SessionJSON.model_validate_json(json.dumps(dumped))


def test_single_var_iteration_requires_risk_segment_details(loaded_session):
    dumped = _json_dict(loaded_session)
    single = next(
        it
        for it in dumped["iterations_repository"]["iterations"]
        if it["iter_type"] == IterationType.SINGLE.value
    )
    del single["risk_segment_details"]

    with pytest.raises(ValidationError):
        SessionJSON.model_validate_json(json.dumps(dumped))


def test_double_var_iteration_requires_grid_fields(loaded_session):
    dumped = _json_dict(loaded_session)
    double = next(
        it
        for it in dumped["iterations_repository"]["iterations"]
        if it["iter_type"] == IterationType.DOUBLE.value
    )
    del double["groups_mask"]

    with pytest.raises(ValidationError):
        SessionJSON.model_validate_json(json.dumps(dumped))


# ---------------------------------------------------------------------------
# Data source corrections
# ---------------------------------------------------------------------------


def test_get_data_source_corrections_reports_missing_file(loaded_session, tmp_path):
    dumped = _json_dict(loaded_session)
    ds_uid = next(iter(dumped["data_repository"]["data_sources"]))
    dumped["data_repository"]["data_sources"][ds_uid]["filepath"] = str(
        tmp_path / "missing.csv"
    )

    home_vm = HomeViewModel()
    home_vm.uploaded_file = _FakeUploadedFile(
        "session_archive.json", json.dumps(dumped).encode("utf-8")
    )
    home_vm.get_jsons()

    corrections = home_vm.get_data_source_corrections()

    assert DataSourceID(ds_uid) in corrections
    assert isinstance(corrections[DataSourceID(ds_uid)], Exception)


def test_validate_data_source_clears_correction(loaded_session, tmp_path):
    csv_path = _make_csv(tmp_path)
    dumped = _json_dict(loaded_session)
    ds_uid = next(iter(dumped["data_repository"]["data_sources"]))
    raw_ds = dumped["data_repository"]["data_sources"][ds_uid]
    dumped["data_repository"]["data_sources"][ds_uid]["filepath"] = str(
        tmp_path / "missing.csv"
    )

    home_vm = HomeViewModel()
    home_vm.uploaded_file = _FakeUploadedFile(
        "session_archive.json", json.dumps(dumped).encode("utf-8")
    )
    home_vm.get_jsons()

    updated_ds = DataSource(
        uid=DataSourceID(ds_uid),
        label=raw_ds["label"],
        filepath=csv_path,
        read_config=ReadConfig(),
    )
    home_vm.validate_data_source(updated_ds)

    corrections = home_vm.get_data_source_corrections()

    assert corrections[DataSourceID(ds_uid)] is None


# ---------------------------------------------------------------------------
# Column validation
# ---------------------------------------------------------------------------


def test_validate_columns_clean_for_valid_session(loaded_session):
    home_vm = HomeViewModel()
    home_vm.uploaded_file = _FakeUploadedFile(
        "session_archive.json", _dump_bytes(loaded_session)
    )
    home_vm.get_jsons()

    (
        invalid_filters,
        invalid_metrics,
        missing_metric_variables,
        invalid_iterations,
        missing_data_explorer_variables,
        missing_summary_variables,
    ) = home_vm.validate_columns()

    assert invalid_filters == {}
    assert invalid_metrics == {}
    assert missing_metric_variables == []
    assert invalid_iterations == {}
    assert missing_data_explorer_variables == []
    assert missing_summary_variables == []


def test_validate_columns_reports_invalid_references(loaded_session):
    dumped = _json_dict(loaded_session)
    filter_uid = next(iter(dumped["filter_repository"]["filters"]))
    dumped["filter_repository"]["filters"][filter_uid]["query"] = "`missing_col` > 0"
    dumped["filter_repository"]["filters"][filter_uid]["used_columns"] = ["missing_col"]

    dumped["summary_view_model"]["pv_row_vars"] = ["missing_pv_var"]

    home_vm = HomeViewModel()
    home_vm.uploaded_file = _FakeUploadedFile(
        "session_archive.json", json.dumps(dumped).encode("utf-8")
    )
    home_vm.get_jsons()

    (
        invalid_filters,
        _invalid_metrics,
        _missing_metric_variables,
        _invalid_iterations,
        _missing_data_explorer_variables,
        missing_summary_variables,
    ) = home_vm.validate_columns()

    assert FilterID(filter_uid) in invalid_filters
    assert missing_summary_variables == ["missing_pv_var"]


# ---------------------------------------------------------------------------
# Rebuild robustness (errors="ignore")
# ---------------------------------------------------------------------------


def test_rebuild_drops_invalid_filters(loaded_session):
    dumped = _json_dict(loaded_session)
    filter_uid = next(iter(dumped["filter_repository"]["filters"]))
    dumped["filter_repository"]["filters"][filter_uid]["query"] = "`missing_col` > 0"
    dumped["filter_repository"]["filters"][filter_uid]["used_columns"] = ["missing_col"]

    restored = _restore_session(json.dumps(dumped))

    assert FilterID(filter_uid) not in restored.filter_repository.filters
    assert set(restored.filter_repository.filters) == {
        fid
        for fid in loaded_session.filter_repository.filters
        if fid != FilterID(filter_uid)
    }


def test_rebuild_drops_invalid_metrics(loaded_session):
    dumped = _json_dict(loaded_session)
    metric_uid = next(iter(dumped["metric_repository"]["metrics"]))
    dumped["metric_repository"]["metrics"][metric_uid]["query"] = "`missing_col`.mean()"
    dumped["metric_repository"]["metrics"][metric_uid]["used_columns"] = ["missing_col"]

    restored = _restore_session(json.dumps(dumped))

    assert metric_uid not in restored.metric_repository.to_dict().metrics
