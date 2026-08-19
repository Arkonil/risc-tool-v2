"""Lightweight tests for the iteration code generator component."""

from unittest.mock import MagicMock, patch

from risc_tool.data.models.data_source import ReadConfig
from risc_tool.data.models.enums import LossRateTypes, VariableType
from risc_tool.data.models.object_id import RiskSegmentID
from risc_tool.data.session import Session
from risc_tool.ui.export.code_generator import iteration_code_generator


def _make_session_with_iteration(tmp_path) -> tuple[Session, object]:
    csv_path = tmp_path / "data.csv"
    csv_path.write_text("credit_score,income\n500,1000\n700,3000\n", encoding="utf-8")
    session = Session()
    session.data_repository.add_data_source("Dev Data", csv_path, ReadConfig())

    iteration = session.iterations_view_model.add_single_var_iteration(
        name="Test Iteration",
        variable_name="credit_score",
        variable_dtype=VariableType.NUMERICAL,
        selected_segment_ids=[RiskSegmentID(0), RiskSegmentID(1), RiskSegmentID(2)],
        loss_rate_type=LossRateTypes.DLR,
        filter_ids=[],
        auto_band=False,
        use_scalar=False,
        remove_outliers=False,
    )
    return session, iteration


@patch("streamlit.checkbox", return_value=True)
@patch("streamlit.session_state")
@patch("streamlit.warning")
@patch("streamlit.info")
@patch("streamlit.markdown")
@patch("streamlit.columns", return_value=[MagicMock(), MagicMock()])
@patch("streamlit.code")
@patch("risc_tool.ui.export.code_generator.iteration_selector")
def test_python_code_generation(
    mock_selector,
    mock_code,
    mock_columns,
    mock_markdown,
    mock_info,
    mock_warning,
    mock_session_state,
    mock_checkbox,
    tmp_path,
):
    session, iteration = _make_session_with_iteration(tmp_path)
    mock_session_state.__getitem__.return_value = session
    mock_selector.return_value = (iteration.uid, False)

    iteration_code_generator("python")

    mock_selector.assert_called_once_with(key="python-code-iteration-selector")
    mock_code.assert_called_once()
    assert mock_code.call_args.kwargs["language"] == "python"
    code = mock_code.call_args.args[0]
    assert f"iter_{iteration.uid}_map = {{" in code
    assert (
        f'create_mapped_variable(data["credit_score"], iter_{iteration.uid}_map)'
        in code
    )


@patch("streamlit.checkbox", return_value=True)
@patch("streamlit.session_state")
@patch("streamlit.warning")
@patch("streamlit.info")
@patch("streamlit.markdown")
@patch("streamlit.columns", return_value=[MagicMock(), MagicMock()])
@patch("streamlit.code")
@patch("risc_tool.ui.export.code_generator.iteration_selector")
def test_sas_code_generation_with_macro(
    mock_selector,
    mock_code,
    mock_columns,
    mock_markdown,
    mock_info,
    mock_warning,
    mock_session_state,
    mock_checkbox,
    tmp_path,
):
    session, iteration = _make_session_with_iteration(tmp_path)
    mock_session_state.__getitem__.return_value = session
    mock_selector.return_value = (iteration.uid, False)

    iteration_code_generator("sas")

    mock_checkbox.assert_called_once()
    mock_code.assert_called_once()
    assert mock_code.call_args.kwargs["language"] == "sas"
    code = mock_code.call_args.args[0]
    assert "/* Macro Definitions: */" in code
    assert "%let variable_0_ = credit_score;" in code


@patch("streamlit.checkbox", return_value=False)
@patch("streamlit.session_state")
@patch("streamlit.warning")
@patch("streamlit.info")
@patch("streamlit.markdown")
@patch("streamlit.columns", return_value=[MagicMock(), MagicMock()])
@patch("streamlit.code")
@patch("risc_tool.ui.export.code_generator.iteration_selector")
def test_sas_code_generation_without_macro(
    mock_selector,
    mock_code,
    mock_columns,
    mock_markdown,
    mock_info,
    mock_warning,
    mock_session_state,
    mock_checkbox,
    tmp_path,
):
    session, iteration = _make_session_with_iteration(tmp_path)
    mock_session_state.__getitem__.return_value = session
    mock_selector.return_value = (iteration.uid, False)

    iteration_code_generator("sas")

    code = mock_code.call_args.args[0]
    assert "/* Macro Definitions: */" not in code
    assert "%let variable_0_ = credit_score;" not in code
    assert "set source;" in code
    assert "credit_score" in code
    assert f"Risk_Seg_{iteration.uid}_custom" in code


@patch("streamlit.session_state")
@patch("streamlit.warning")
@patch("streamlit.info")
@patch("streamlit.columns", return_value=[MagicMock(), MagicMock()])
@patch("streamlit.code")
@patch("risc_tool.ui.export.code_generator.iteration_selector")
def test_no_iteration_shows_info(
    mock_selector,
    mock_code,
    mock_columns,
    mock_info,
    mock_warning,
    mock_session_state,
):
    session = Session()
    mock_session_state.__getitem__.return_value = session

    iteration_code_generator("python")

    mock_info.assert_called_once()
    mock_code.assert_not_called()
    mock_selector.assert_not_called()


@patch("streamlit.checkbox", return_value=True)
@patch("streamlit.session_state")
@patch("streamlit.warning")
@patch("streamlit.info")
@patch("streamlit.markdown")
@patch("streamlit.columns", return_value=[MagicMock(), MagicMock()])
@patch("streamlit.code")
@patch("risc_tool.ui.export.code_generator.iteration_selector")
def test_invalid_iteration_shows_warning(
    mock_selector,
    mock_code,
    mock_columns,
    mock_markdown,
    mock_info,
    mock_warning,
    mock_session_state,
    mock_checkbox,
    tmp_path,
):
    session, _iteration = _make_session_with_iteration(tmp_path)
    mock_session_state.__getitem__.return_value = session
    mock_selector.return_value = (None, False)

    iteration_code_generator("python")

    mock_warning.assert_called_once()
    mock_code.assert_not_called()
