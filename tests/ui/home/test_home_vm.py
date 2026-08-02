"""Lightweight unit tests for HomeViewModel (no streamlit widgets)."""

from pathlib import Path

import pytest

from risc_tool.data.models.data_source import ReadConfig
from risc_tool.data.models.json_models import SessionJSON
from risc_tool.data.session import Session
from risc_tool.ui.home.home_vm import HomeViewModel


class _FakeUploadedFile:
    """Minimal stand-in for streamlit's UploadedFile."""

    def __init__(self, name: str, content: bytes) -> None:
        self.name = name
        self._content = content
        self._read_count = 0

    def read(self) -> bytes:
        self._read_count += 1
        return self._content


def _dump_bytes(session: Session) -> bytes:
    return session.to_dict().model_dump_json(indent=2).encode("utf-8")


def _make_session_with_data(tmp_path: Path) -> Session:
    csv_path = tmp_path / "data.csv"
    csv_path.write_text("score,group\n10,A\n20,B\n", encoding="utf-8")
    session = Session()
    session.data_repository.add_data_source("Dev Data", csv_path, ReadConfig())
    return session


def test_initial_state():
    vm = HomeViewModel()

    assert vm.home_page_view == "welcome"
    assert vm.uploaded_file is None
    assert vm.raw_session_json is None
    assert vm.validated_session_json is None


def test_set_home_page_view():
    vm = HomeViewModel()

    vm.set_home_page_view("import-json")
    assert vm.home_page_view == "import-json"

    vm.set_home_page_view("welcome")
    assert vm.home_page_view == "welcome"


def test_clear_uploaded_file():
    vm = HomeViewModel()
    vm.uploaded_file = _FakeUploadedFile("session.json", _dump_bytes(Session()))
    vm.get_jsons()
    assert vm.raw_session_json is not None
    assert vm.validated_session_json is not None

    vm.clear_uploaded_file()

    assert vm.uploaded_file is None
    assert vm.raw_session_json is None
    assert vm.validated_session_json is None


def test_get_jsons_parses_uploaded_file():
    vm = HomeViewModel()
    vm.uploaded_file = _FakeUploadedFile("session.json", _dump_bytes(Session()))

    raw, validated = vm.get_jsons()

    assert isinstance(raw, SessionJSON)
    assert isinstance(validated, SessionJSON)
    assert raw == validated


def test_get_jsons_caches_parsed_result():
    session = Session()
    fake_file = _FakeUploadedFile("session.json", _dump_bytes(session))
    vm = HomeViewModel()
    vm.uploaded_file = fake_file

    first_raw, _ = vm.get_jsons()
    second_raw, _ = vm.get_jsons()

    assert fake_file._read_count == 1
    assert first_raw is second_raw


def test_validated_json_is_deep_copy(tmp_path):
    vm = HomeViewModel()
    vm.uploaded_file = _FakeUploadedFile(
        "session.json", _dump_bytes(_make_session_with_data(tmp_path))
    )

    raw, validated = vm.get_jsons()

    validated.data_repository.data_sources = {}
    assert raw.data_repository.data_sources != {}


def test_get_jsons_raises_without_uploaded_file():
    vm = HomeViewModel()

    with pytest.raises(ValueError):
        vm.get_jsons()


def test_get_data_source_corrections_requires_json():
    vm = HomeViewModel()

    with pytest.raises(ValueError):
        vm.get_data_source_corrections()


def test_validate_columns_requires_json():
    vm = HomeViewModel()

    with pytest.raises(ValueError):
        vm.validate_columns()
