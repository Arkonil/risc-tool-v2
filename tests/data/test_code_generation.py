"""Tests for Python and SAS code generation from iterations.

Covers the model-level templates (iteration.generate_*_code), the
repository-level code builders (get_code_templates / get_python_code /
get_sas_code), the ExportViewModel delegation, and executing the generated
Python against a real data source to verify the risk segment assignments.
"""

from collections import OrderedDict
from pathlib import Path
from string import Template

import pytest

from risc_tool.data.models.config import RiskSegmentConfig
from risc_tool.data.models.data_source import ReadConfig
from risc_tool.data.models.enums import (
    ExportTabName,
    LossRateTypes,
    VariableType,
)
from risc_tool.data.models.iteration import (
    CategoricalSingleVarIteration,
    NumericalDoubleVarIteration,
    NumericalSingleVarIteration,
)
from risc_tool.data.models.iteration_group import (
    CategoricalGroup,
    NumericalGroup,
)
from risc_tool.data.models.types import GroupID, IterationID, RiskSegmentID
from risc_tool.data.repositories.data import DataRepository
from risc_tool.data.repositories.filter import FilterRepository
from risc_tool.data.repositories.iterations import IterationsRepository
from risc_tool.data.repositories.metric import MetricRepository
from risc_tool.data.repositories.options import OptionRepository
from risc_tool.data.repositories.scalar import ScalarRepository
from risc_tool.data.session import Session
from risc_tool.ui.export.export_vm import ExportViewModel

# ---------------------------------------------------------------------------
# Model-level helpers
# ---------------------------------------------------------------------------

SINGLE_SUBSTITUTES = {
    "VARIABLE_NAME": "credit_score",
    "OUTPUT_VARIABLE_NAME": "Risk_Seg_0_custom",
    "PREV_ITER_OUT_NAME": "",
    "MISSING": '""',
    "DATA": "data",
    "GROUP_INDEX_0": '"1A"',
    "GROUP_INDEX_1": '"1B"',
    "GROUP_INDEX_2": '"2A"',
}

DOUBLE_SUBSTITUTES = {
    **SINGLE_SUBSTITUTES,
    "VARIABLE_NAME": "income",
    "OUTPUT_VARIABLE_NAME": "Risk_Seg_1_custom",
    "PREV_ITER_OUT_NAME": "Risk_Seg_0_custom",
}


def _numerical_groups() -> OrderedDict[GroupID, NumericalGroup]:
    return OrderedDict([
        (GroupID(0), NumericalGroup(lower_bound=float("-inf"), upper_bound=600.0)),
        (GroupID(1), NumericalGroup(lower_bound=600.0, upper_bound=750.0)),
        (GroupID(2), NumericalGroup(lower_bound=750.0, upper_bound=float("inf"))),
    ])


def _categorical_groups() -> OrderedDict[GroupID, CategoricalGroup]:
    return OrderedDict([
        (GroupID(0), CategoricalGroup(categories={"Employed"})),
        (GroupID(1), CategoricalGroup(categories={"Self-employed", "Contract"})),
        (GroupID(2), CategoricalGroup(categories={"Unemployed"})),
    ])


def _single_numerical_iteration() -> NumericalSingleVarIteration:
    iteration = NumericalSingleVarIteration(
        uid=IterationID(0),
        name="Score Iteration",
        variable_name="credit_score",
        risk_segment_details=RiskSegmentConfig(),
    )
    iteration.set_default_groups(_numerical_groups())
    return iteration


def _single_categorical_iteration() -> CategoricalSingleVarIteration:
    iteration = CategoricalSingleVarIteration(
        uid=IterationID(1),
        name="Employment Iteration",
        variable_name="employment_status",
        risk_segment_details=RiskSegmentConfig(),
    )
    iteration.set_default_groups(_categorical_groups())
    return iteration


def _double_numerical_iteration() -> NumericalDoubleVarIteration:
    iteration = NumericalDoubleVarIteration(
        uid=IterationID(2),
        name="Income Iteration",
        variable_name="income",
    )
    iteration.set_default_groups(_numerical_groups())

    segment_ids = [RiskSegmentID(0), RiskSegmentID(1), RiskSegmentID(2)]
    iteration.groups_mask = {gid: True for gid in iteration.groups}
    identity_grid = {gid: {seg: seg for seg in segment_ids} for gid in iteration.groups}
    iteration.risk_segment_grid = identity_grid
    iteration.default_risk_segment_grid = identity_grid
    return iteration


def _render(template: Template, substitutes: dict) -> str:
    return template.safe_substitute(substitutes)


# ---------------------------------------------------------------------------
# Model-level: Python templates
# ---------------------------------------------------------------------------


def test_single_numerical_python_template():
    code = _render(
        _single_numerical_iteration().generate_python_code(False), SINGLE_SUBSTITUTES
    )

    assert "iter_0_map = {" in code
    assert "pd.Interval(float('-inf'), 600.0, closed='right'): \"1A\"," in code
    assert "pd.Interval(600.0, 750.0, closed='right'): \"1B\"," in code
    assert "pd.Interval(750.0, float('inf'), closed='right'): \"2A\"," in code
    assert (
        "iter_0_map = pd.Series(data=iter_0_map.values(), index=list(iter_0_map.keys()))"
        in code
    )
    assert 'create_mapped_variable(data["credit_score"], iter_0_map)' in code


def test_single_categorical_python_template():
    code = _render(
        _single_categorical_iteration().generate_python_code(False),
        {**SINGLE_SUBSTITUTES, "VARIABLE_NAME": "employment_status"},
    )

    assert '("Employed",): "1A",' in code
    assert '("Contract", "Self-employed",): "1B",' in code
    assert '("Unemployed",): "2A",' in code
    assert 'create_mapped_variable(data["employment_status"], iter_1_map)' in code


def test_double_var_python_template():
    code = _render(
        _double_numerical_iteration().generate_python_code(False), DOUBLE_SUBSTITUTES
    )

    assert "iter_2_grid = pd.DataFrame(" in code
    assert 'columns=["1A", "1B", "2A"]' in code
    assert "pd.Interval(float('-inf'), 600.0, closed='right')," in code
    assert (
        'create_grid_mapped_variable(data["income"], data["Risk_Seg_0_custom"], iter_2_grid)'
        in code
    )


# ---------------------------------------------------------------------------
# Model-level: SAS templates
# ---------------------------------------------------------------------------


def test_single_numerical_sas_template():
    code = _render(
        _single_numerical_iteration().generate_sas_code(False), SINGLE_SUBSTITUTES
    )

    assert "format Risk_Seg_0_custom $50.;" in code
    assert 'if missing(credit_score) then Risk_Seg_0_custom = "";' in code
    assert "(-inf < credit_score <= 600.0)" in code
    assert "(600.0 < credit_score <= 750.0)" in code
    assert "(750.0 < credit_score <= inf)" in code
    assert 'Risk_Seg_0_custom = "1A";' in code
    assert 'else Risk_Seg_0_custom = "";' in code


def test_single_categorical_sas_template():
    code = _render(
        _single_categorical_iteration().generate_sas_code(False),
        {**SINGLE_SUBSTITUTES, "VARIABLE_NAME": "employment_status"},
    )

    assert '(employment_status in ("Employed"))' in code
    assert '(employment_status in ("Contract", "Self-employed"))' in code
    assert '(employment_status in ("Unemployed"))' in code


def test_double_var_sas_template():
    code = _render(
        _double_numerical_iteration().generate_sas_code(False), DOUBLE_SUBSTITUTES
    )

    assert (
        'if missing(income) or missing(Risk_Seg_0_custom) then Risk_Seg_1_custom = "";'
        in code
    )
    assert 'else if Risk_Seg_0_custom = "1A" then do;' in code
    assert 'else if Risk_Seg_0_custom = "1B" then do;' in code
    assert 'else if Risk_Seg_0_custom = "2A" then do;' in code
    assert "end;" in code
    assert 'else Risk_Seg_1_custom = "";' in code


# ---------------------------------------------------------------------------
# Repository-level helpers / fixture
# ---------------------------------------------------------------------------


def _write_csv(path: Path, contents: str) -> None:
    path.write_text(contents, encoding="utf-8")


@pytest.fixture
def code_session(tmp_path) -> Session:
    csv_path = tmp_path / "data.csv"
    _write_csv(
        csv_path,
        "credit_score,income,employment_status\n"
        "100,1000,Employed\n"
        "200,2000,Self-employed\n"
        "700,7000,Employed\n"
        "800,8000,Unemployed\n",
    )

    session = Session()
    session.data_repository.add_data_source("Dev Data", csv_path, ReadConfig())

    metric_repo = session.metric_repository
    metric_repo.dev_data_source_ids = list(session.data_repository.data_sources.keys())
    metric_repo.var_dev_dlr_bad = "credit_score"
    metric_repo.var_dev_avg_bal = "credit_score"
    metric_repo.current_rate_mob = 12

    iterations_vm = session.iterations_view_model
    iterations_vm.add_single_var_iteration(
        name="Num Iter",
        variable_name="credit_score",
        variable_dtype=VariableType.NUMERICAL,
        selected_segment_ids=[RiskSegmentID(0), RiskSegmentID(1), RiskSegmentID(2)],
        loss_rate_type=LossRateTypes.DLR,
        filter_ids=[],
        auto_band=False,
        use_scalar=False,
        remove_outliers=False,
    )
    iterations_vm.add_single_var_iteration(
        name="Cat Iter",
        variable_name="employment_status",
        variable_dtype=VariableType.CATEGORICAL,
        selected_segment_ids=[RiskSegmentID(0), RiskSegmentID(1), RiskSegmentID(2)],
        loss_rate_type=LossRateTypes.DLR,
        filter_ids=[],
        auto_band=False,
        use_scalar=False,
        remove_outliers=False,
    )
    num_iter = _iteration_by_name(session, "Num Iter")
    iterations_vm.add_double_var_iteration(
        name="Double Iter",
        previous_iteration_id=num_iter.uid,
        variable_name="income",
        variable_dtype=VariableType.NUMERICAL,
        auto_band=False,
        use_scalar=False,
        remove_outliers=False,
    )

    return session


def _iteration_by_name(session: Session, name: str):
    for iteration in session.iterations_repository.iterations.values():
        if iteration.name == name:
            return iteration
    raise AssertionError(f"iteration named {name!r} not found")


def _expected_assignments(values, groups, segments) -> list[str | None]:
    expected: list[str | None] = []
    for value in values:
        assigned = None
        for group_id, group in groups.items():
            if not group.is_valid():
                continue
            if isinstance(group, NumericalGroup):
                if group.lower_bound < value <= group.upper_bound:
                    assigned = segments[RiskSegmentID(group_id.value)].name
                    break
            elif value in group.categories:
                assigned = segments[RiskSegmentID(group_id.value)].name
                break
        expected.append(assigned)
    return expected


# ---------------------------------------------------------------------------
# Repository-level: code templates
# ---------------------------------------------------------------------------


def test_get_code_templates_single_chain(code_session):
    repo = code_session.iterations_repository
    num_iter = _iteration_by_name(code_session, "Num Iter")

    templates = repo.get_code_templates(num_iter.uid, default=False, language="python")

    assert len(templates) == 1
    substitute = templates[0]["substitute"]
    assert substitute["VARIABLE_NAME"] == "credit_score"
    assert substitute["OUTPUT_VARIABLE_NAME"] == f"Risk_Seg_{num_iter.uid}_custom"
    assert substitute["PREV_ITER_OUT_NAME"] == ""
    assert substitute["GROUP_INDEX_0"] == '"1A"'
    assert substitute["GROUP_INDEX_2"] == '"2A"'


def test_get_code_templates_double_chain_links_previous_output(code_session):
    repo = code_session.iterations_repository
    num_iter = _iteration_by_name(code_session, "Num Iter")
    double_iter = _iteration_by_name(code_session, "Double Iter")

    templates = repo.get_code_templates(
        double_iter.uid, default=False, language="python"
    )

    assert [t["node_id"] for t in templates] == [num_iter.uid, double_iter.uid]
    assert templates[0]["substitute"]["VARIABLE_NAME"] == "credit_score"
    assert templates[0]["substitute"]["OUTPUT_VARIABLE_NAME"] == (
        f"Risk_Seg_{num_iter.uid}_custom"
    )
    assert templates[1]["substitute"]["VARIABLE_NAME"] == "income"
    assert (
        templates[1]["substitute"]["PREV_ITER_OUT_NAME"]
        == (templates[0]["substitute"]["OUTPUT_VARIABLE_NAME"])
    )
    assert templates[1]["substitute"]["OUTPUT_VARIABLE_NAME"] == (
        f"Risk_Seg_{double_iter.uid}_custom"
    )


def test_get_code_templates_default_flag_names_output(code_session):
    repo = code_session.iterations_repository
    num_iter = _iteration_by_name(code_session, "Num Iter")

    default_templates = repo.get_code_templates(
        num_iter.uid, default=True, language="sas"
    )
    custom_templates = repo.get_code_templates(
        num_iter.uid, default=False, language="sas"
    )

    assert default_templates[0]["substitute"]["OUTPUT_VARIABLE_NAME"] == (
        f"Risk_Seg_{num_iter.uid}_default"
    )
    assert custom_templates[0]["substitute"]["OUTPUT_VARIABLE_NAME"] == (
        f"Risk_Seg_{num_iter.uid}_custom"
    )


# ---------------------------------------------------------------------------
# Repository-level: Python code
# ---------------------------------------------------------------------------


def test_get_python_code_structure(code_session):
    repo = code_session.iterations_repository
    num_iter = _iteration_by_name(code_session, "Num Iter")

    code = repo.get_python_code(num_iter.uid, default=False)

    assert "import numpy as np" in code
    assert "import pandas as pd" in code
    assert "pd.read_csv(" in code
    assert "pd.concat(data_sources, axis=0, keys=range(len(data_sources)))" in code
    assert "def create_mapped_variable(" in code
    assert "def create_grid_mapped_variable(" in code
    assert f"## Iteration {num_iter.uid}" in code


def test_get_python_code_uses_custom_groups_when_not_default(code_session):
    repo = code_session.iterations_repository
    num_iter = _iteration_by_name(code_session, "Num Iter")

    num_iter.set_group(GroupID(0), 0.0, 500.0, set())
    num_iter.set_group(GroupID(1), 500.0, 750.0, set())
    num_iter.set_group(GroupID(2), 750.0, 1000.0, set())

    custom_code = repo.get_python_code(num_iter.uid, default=False)
    default_code = repo.get_python_code(num_iter.uid, default=True)

    assert "pd.Interval(0.0, 500.0, closed='right')" in custom_code
    assert "pd.Interval(0.0, 500.0, closed='right')" not in default_code
    assert "pd.Interval(float('-inf')," in default_code


# ---------------------------------------------------------------------------
# Repository-level: SAS code
# ---------------------------------------------------------------------------


def test_get_sas_code_with_macro(code_session):
    repo = code_session.iterations_repository
    num_iter = _iteration_by_name(code_session, "Num Iter")

    code = repo.get_sas_code(num_iter.uid, default=False, use_macro=True)

    assert "/* Macro Definitions: */" in code
    assert "%let variable_0_ = credit_score;" in code
    assert f"%let result_0_ = Risk_Seg_{num_iter.uid}_custom;" in code
    assert "format &result_0_. $50.;" in code
    assert 'if missing(&variable_0_.) then &result_0_. = "";' in code


def test_get_sas_code_without_macro(code_session):
    repo = code_session.iterations_repository
    num_iter = _iteration_by_name(code_session, "Num Iter")

    code = repo.get_sas_code(num_iter.uid, default=False, use_macro=False)

    assert "%let" not in code
    assert "&variable_0_." not in code
    assert "if missing(credit_score) then" in code
    assert f"format Risk_Seg_{num_iter.uid}_custom $50.;" in code


def test_get_sas_code_wraps_in_data_step(code_session):
    repo = code_session.iterations_repository
    num_iter = _iteration_by_name(code_session, "Num Iter")

    code = repo.get_sas_code(num_iter.uid, default=False, use_macro=False)

    assert "data result;" in code
    assert "set source;" in code
    assert "run;" in code


def test_get_sas_code_double_iteration_chain(code_session):
    repo = code_session.iterations_repository
    double_iter = _iteration_by_name(code_session, "Double Iter")

    code = repo.get_sas_code(double_iter.uid, default=False, use_macro=False)

    assert "if missing(income) or missing(" in code
    assert "then do;" in code
    assert "end;" in code
    assert "/* Iteration" in code


# ---------------------------------------------------------------------------
# Executing the generated Python code
# ---------------------------------------------------------------------------


def test_python_code_executes_single_var_numerical(code_session):
    repo = code_session.iterations_repository
    num_iter = _iteration_by_name(code_session, "Num Iter")

    namespace = {}
    exec(repo.get_python_code(num_iter.uid, default=False), namespace)  # noqa: S102

    data = namespace["data"]
    output_col = f"Risk_Seg_{num_iter.uid}_custom"
    segments = num_iter.risk_segment_details.segments

    assert output_col in data.columns
    assert data[output_col].notna().all()
    assert list(data[output_col].astype(str)) == _expected_assignments(
        data["credit_score"], num_iter.groups, segments
    )


def test_python_code_executes_single_var_categorical(code_session):
    repo = code_session.iterations_repository
    cat_iter = _iteration_by_name(code_session, "Cat Iter")

    namespace = {}
    exec(repo.get_python_code(cat_iter.uid, default=False), namespace)  # noqa: S102

    data = namespace["data"]
    output_col = f"Risk_Seg_{cat_iter.uid}_custom"
    segments = cat_iter.risk_segment_details.segments

    assert output_col in data.columns
    assert data[output_col].notna().all()
    assert list(data[output_col].astype(str)) == _expected_assignments(
        data["employment_status"], cat_iter.groups, segments
    )


def test_python_code_executes_double_var_chain(code_session):
    repo = code_session.iterations_repository
    num_iter = _iteration_by_name(code_session, "Num Iter")
    double_iter = _iteration_by_name(code_session, "Double Iter")

    namespace = {}
    exec(repo.get_python_code(double_iter.uid, default=False), namespace)  # noqa: S102

    data = namespace["data"]
    output_col = f"Risk_Seg_{double_iter.uid}_custom"

    assert output_col in data.columns
    assert data[output_col].notna().all()
    # Identity grid: the double variable maps each row to the parent segment.
    assert list(data[output_col]) == list(data[f"Risk_Seg_{num_iter.uid}_custom"])


def test_python_code_executes_with_default_groups(code_session):
    repo = code_session.iterations_repository
    num_iter = _iteration_by_name(code_session, "Num Iter")

    namespace = {}
    exec(repo.get_python_code(num_iter.uid, default=True), namespace)  # noqa: S102

    data = namespace["data"]
    output_col = f"Risk_Seg_{num_iter.uid}_default"
    segments = num_iter.risk_segment_details.segments

    assert output_col in data.columns
    assert data[output_col].notna().all()
    assert list(data[output_col].astype(str)) == _expected_assignments(
        data["credit_score"], num_iter.default_groups, segments
    )


# ---------------------------------------------------------------------------
# ExportViewModel delegation
# ---------------------------------------------------------------------------


@pytest.fixture
def export_vm(code_session) -> ExportViewModel:
    return ExportViewModel(code_session.iterations_repository)


def test_export_vm_no_iteration():
    data_repo = DataRepository()
    filter_repo = FilterRepository(data_repo)
    metric_repo = MetricRepository(data_repo)
    option_repo = OptionRepository()
    scalar_repo = ScalarRepository()
    empty_repo = IterationsRepository(
        data_repo, filter_repo, metric_repo, option_repo, scalar_repo
    )

    assert ExportViewModel(empty_repo).no_iteration is True
    assert ExportViewModel(empty_repo).tab_names == [
        ExportTabName.SESSION_ARCHIVE,
        ExportTabName.PYTHON_CODE,
        ExportTabName.SAS_CODE,
    ]


def test_export_vm_no_iteration_false(export_vm):
    assert export_vm.no_iteration is False


def test_export_vm_get_python_code(export_vm, code_session):
    num_iter = _iteration_by_name(code_session, "Num Iter")

    code = export_vm.get_python_code(num_iter.uid, default=False)

    assert isinstance(code, str)
    assert f"## Iteration {num_iter.uid}" in code


def test_export_vm_get_sas_code(export_vm, code_session):
    num_iter = _iteration_by_name(code_session, "Num Iter")

    with_macro = export_vm.get_sas_code(num_iter.uid, default=False, use_macro=True)
    without_macro = export_vm.get_sas_code(num_iter.uid, default=False, use_macro=False)

    assert "%let variable_0_ = credit_score;" in with_macro
    assert "%let" not in without_macro
