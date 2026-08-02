"""Unit tests for Pydantic iteration data models."""

from collections import OrderedDict

from risc_tool.data.models.enums import IterationType, VariableType
from risc_tool.data.models.iteration import (
    CategoricalGroup,
    CategoricalSingleVarIteration,
    NumericalGroup,
    NumericalSingleVarIteration,
)
from risc_tool.data.models.iteration_graph import IterationGraph
from risc_tool.data.models.iteration_metadata import IterationMetadata
from risc_tool.data.models.types import GroupID, IterationID


def test_numerical_group_validation():
    g = NumericalGroup(lower_bound=0.0, upper_bound=10.0)
    assert g.is_valid()

    g_invalid = NumericalGroup(lower_bound=10.0, upper_bound=5.0)
    assert not g_invalid.is_valid()

    # None is normalized to -inf by field validators and remains a valid open interval.
    g_nan = NumericalGroup.model_validate({"lower_bound": None, "upper_bound": 10.0})
    assert g_nan.lower_bound == float("-inf")
    assert g_nan.is_valid()


def test_categorical_group_validation():
    cg = CategoricalGroup(categories={"A", "B"})
    assert cg.is_valid()

    cg_empty = CategoricalGroup(categories=set())
    assert not cg_empty.is_valid()


def test_single_var_iteration_create():
    iter_obj = NumericalSingleVarIteration.model_validate({
        "uid": IterationID(1),
        "name": "Test Single Var",
        "variable_name": "score",
        "groups": OrderedDict([
            (GroupID(0), NumericalGroup(lower_bound=0.0, upper_bound=50.0)),
            (GroupID(1), NumericalGroup(lower_bound=50.0, upper_bound=100.0)),
        ]),
    })
    assert iter_obj.uid == IterationID(1)
    assert iter_obj.iter_type == IterationType.SINGLE
    assert iter_obj.var_type == VariableType.NUMERICAL
    assert len(iter_obj.groups) == 2


def test_iteration_serialization_roundtrip():
    iter_obj = CategoricalSingleVarIteration.model_validate({
        "uid": IterationID(2),
        "name": "Cat Var",
        "variable_name": "grade",
        "groups": OrderedDict([
            (GroupID(0), CategoricalGroup(categories={"A", "B"})),
        ]),
    })
    dumped = iter_obj.model_dump()
    reconstructed = CategoricalSingleVarIteration.model_validate(dumped)
    assert reconstructed.uid == iter_obj.uid
    assert reconstructed.name == iter_obj.name


def test_iteration_graph_add_parent_child():
    graph = IterationGraph()
    parent = IterationID(1)
    child = IterationID(2)

    graph.add_child(parent, child)
    assert graph.get_parent(child) == parent
    assert graph.is_root(parent)
    assert not graph.is_root(child)
    assert graph.is_leaf(child)


def test_iteration_graph_get_descendants():
    graph = IterationGraph()
    graph.add_child(IterationID(1), IterationID(2))
    graph.add_child(IterationID(2), IterationID(3))

    desc = graph.get_descendants(IterationID(1))
    assert IterationID(2) in desc
    assert IterationID(3) in desc


def test_iteration_metadata_defaults():
    meta = IterationMetadata()
    assert meta.editable is True
    assert meta.scalars_enabled is True
    assert meta.remove_outliers is True


def test_iteration_graph_dag_invariants():
    import pytest

    graph = IterationGraph()
    parent = IterationID(1)
    child = IterationID(2)

    graph.add_child(parent, child)

    # Self-link should raise ValueError
    with pytest.raises(ValueError, match="Cannot add self-link"):
        graph.add_child(parent, parent)

    # Multi-parent should raise ValueError
    parent2 = IterationID(3)
    with pytest.raises(ValueError, match="already has parent"):
        graph.add_child(parent2, child)

    # Cycle creation should raise ValueError
    with pytest.raises(ValueError, match="creates a cycle"):
        graph.add_child(child, parent)


def test_double_var_iteration_type_matching():
    import polars as pl

    from risc_tool.data.models.iteration import NumericalDoubleVarIteration
    from risc_tool.data.models.types import RiskSegmentID

    double_iter = NumericalDoubleVarIteration(
        uid=IterationID(2),
        name="Double Iter",
        variable_name="score",
        groups=OrderedDict([
            (GroupID(0), NumericalGroup(lower_bound=0.0, upper_bound=100.0)),
        ]),
        groups_mask={GroupID(0): True},
        risk_segment_grid={GroupID(0): {RiskSegmentID(1): RiskSegmentID(2)}},
        default_risk_segment_grid={GroupID(0): {RiskSegmentID(1): RiskSegmentID(2)}},
    )
    expr = double_iter.get_risk_segment_expr(default=False, prev_seg_col="prev_seg")
    # Verify expression builds cleanly
    assert isinstance(expr, pl.Expr)
    assert str(expr) is not None

    expr_default = double_iter.get_risk_segment_expr(
        default=True, prev_seg_col="prev_seg"
    )
    assert isinstance(expr_default, pl.Expr)

    # prev_seg_col is required for double variable iterations
    import pytest

    with pytest.raises(ValueError, match="prev_seg_col"):
        double_iter.get_risk_segment_expr(default=False, prev_seg_col=None)
