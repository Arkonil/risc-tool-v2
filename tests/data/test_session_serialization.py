"""Unit tests for Session to_dict and from_dict serialization."""

from pathlib import Path

from risc_tool.data.models.data_source import ReadConfig
from risc_tool.data.models.json_models import SessionJSON
from risc_tool.data.models.object_id import MetricID
from risc_tool.data.session import Session


def _write_csv(path: Path, contents: str) -> None:
    path.write_text(contents, encoding="utf-8")


def test_session_to_dict_empty_session():
    session = Session()
    session_json = session.to_dict()

    assert isinstance(session_json, SessionJSON)
    json_bytes = session_json.model_dump_json()
    assert len(json_bytes) > 0


def test_session_serialization_roundtrip(tmp_path):
    csv_path = tmp_path / "sample.csv"
    _write_csv(csv_path, "score,group\n10,A\n20,B\n30,A\n40,B\n")

    session = Session()
    session.data_repository.add_data_source("Dev Data", csv_path, ReadConfig())
    session.metric_repository.dev_data_source_ids = list(
        session.data_repository.data_sources.keys()
    )

    session.filter_repository.create_filter("Score Filter", "`score` > 15")
    session.summary_view_model.set_pivot_metrics([MetricID.DEV_VOLUME])
    session.summary_view_model.set_pivot_variables("row", ["group"])

    # Export to dict / JSON
    session_json = session.to_dict()
    dumped_json = session_json.model_dump()

    # Restore from dict
    new_session = Session()
    restored_json = SessionJSON.model_validate(dumped_json)
    new_session.rebuild_from_json(restored_json)
    restored_session = new_session

    assert restored_session.data_repository.has_valid_sources is True
    assert len(restored_session.filter_repository.filters) == 1
    assert restored_session.summary_view_model.pv_metric_ids == [MetricID.DEV_VOLUME]
    assert restored_session.summary_view_model.pv_row_vars == ["group"]
