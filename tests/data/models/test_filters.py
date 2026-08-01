import math
from pathlib import Path

import polars as pl
import pytest

from risc_tool.data.models.enums import ComparisonOperation, PercentileOptions
from risc_tool.data.models.exceptions import InvalidFilterError
from risc_tool.data.models.filter import Filter
from risc_tool.data.models.outlier import OutlierRule
from risc_tool.data.models.types import FilterID

# ─── Helpers ─────────────────────────────────────────────────────────────────


def _f(query: str, columns: list[str]) -> Filter:
    """Build and validate a Filter, returning it ready for execution.

    Args:
        query: The filter expression string.
        columns: List of available column names for validation.

    Returns:
        A Filter with uid=1, name="test", and the given query, validated
        against the provided columns.
    """
    f = Filter(FilterID(1), "test", query)
    f.validate_query(available_columns=columns)
    assert f.filter_expr is not None
    return f


def _expr(expr: pl.Expr | None) -> pl.Expr:
    """Narrow an optional expression to a concrete Polars expression."""
    assert expr is not None
    return expr


def _apply(f: Filter, lf: pl.LazyFrame, col_name: str | None = None) -> list:
    """Apply a filter to a LazyFrame and return the specified column as a list.

    Args:
        f: The Filter with a compiled filter_expr.
        lf: The Polars LazyFrame to filter.
        col_name: Column name to extract from the result. Defaults to the
            first column of the LazyFrame.

    Returns:
        A list of values from the specified column after filtering.
    """
    if col_name is None:
        col_name = lf.collect_schema().names()[0]
    return lf.filter(_expr(f.filter_expr)).collect()[col_name].to_list()


def test_filter_compilation_and_execution() -> None:
    # 1. Test basic equality & inequality
    f1 = Filter(FilterID(1), "f1", "value == 10")
    f1.validate_query(available_columns=["value"])
    assert f1.filter_expr is not None

    lf = pl.LazyFrame({"value": [5, 10, 15]})
    res = lf.filter(_expr(f1.filter_expr)).collect()
    assert len(res) == 1
    assert res.item(0, "value") == 10

    # 2. Test backticked variable with spaces
    f2 = Filter(FilterID(2), "f2", "`Credit Score` >= 700")
    f2.validate_query(available_columns=["Credit Score"])
    lf = pl.LazyFrame({"Credit Score": [650, 700, 750]})
    res = lf.filter(_expr(f2.filter_expr)).collect()
    assert len(res) == 2
    assert list(res["Credit Score"]) == [700, 750]

    # 3. Test chained comparison
    f3 = Filter(FilterID(3), "f3", "100 < value <= 200")
    f3.validate_query(available_columns=["value"])
    lf = pl.LazyFrame({"value": [50, 150, 250]})
    res = lf.filter(_expr(f3.filter_expr)).collect()
    assert len(res) == 1
    assert res.item(0, "value") == 150

    # 4. Test membership check (in / not in)
    f4 = Filter(FilterID(4), "f4", "status in ('Approved', 'Pending')")
    f4.validate_query(available_columns=["status"])
    lf = pl.LazyFrame({"status": ["Approved", "Rejected", "Pending"]})
    res = lf.filter(_expr(f4.filter_expr)).collect()
    assert len(res) == 2
    assert list(res["status"]) == ["Approved", "Pending"]

    # 5. Test missing value checks (.isna() / .notna())
    f5 = Filter(FilterID(5), "f5", "value.isna()")
    f5.validate_query(available_columns=["value"])
    lf = pl.LazyFrame({"value": [1.0, None, 3.0]})
    res = lf.filter(_expr(f5.filter_expr)).collect()
    assert len(res) == 1
    assert res.item(0, "value") is None

    f6 = Filter(FilterID(6), "f6", "~value.isna()")
    f6.validate_query(available_columns=["value"])
    res = lf.filter(_expr(f6.filter_expr)).collect()
    assert len(res) == 2


def test_invalid_filter_queries() -> None:
    # Query cannot be empty
    with pytest.raises(InvalidFilterError):
        f = Filter(FilterID(1), "test", "")
        f.validate_query()

    # Query cannot contain assignments
    with pytest.raises(InvalidFilterError):
        f = Filter(FilterID(1), "test", "x = 10")
        f.validate_query(available_columns=["x"])

    # Query must be likely boolean (non-boolean expressions raise error)
    with pytest.raises(InvalidFilterError):
        f = Filter(FilterID(1), "test", "x + 10")
        f.validate_query(available_columns=["x"])

    # Columns must exist in schema
    with pytest.raises(InvalidFilterError):
        f = Filter(FilterID(1), "test", "missing_col > 5")
        f.validate_query(available_columns=["existing_col"])


def test_outlier_rule_thresholds_and_frequency() -> None:
    # 10 values, mode is 0 (occurs 5 times)
    # Rest are [1, 2, 3, 10, 100]. Non-mode values are [1, 2, 3, 10, 100].
    # Quantile 0.90 of non-mode: [1, 2, 3, 10, 100] -> index 4 (100) or interpolates to near 100.
    lf = pl.LazyFrame({"score": [0, 0, 0, 0, 0, 1, 2, 3, 10, 100]})

    # Outlier rule: flag values > 90th percentile as outliers
    rule = OutlierRule(
        uid=FilterID(1),
        variable_name="score",
        comparison_op=ComparisonOperation.GT,
        comparison_base=PercentileOptions.PERC_90,
    )

    # Recalculate thresholds
    rule.recalculate_thresholds(lf)

    assert rule.mode == 0
    assert rule.threshold_val is not None
    # Threshold for 90th percentile of [1, 2, 3, 10, 100] should be around 64.0 (interpolated) or near 100.
    assert rule.threshold_val > 10.0

    # Test frequency (outlier count)
    # The outlier (greater than threshold ~46-100) is 100 (1 row)
    assert rule.frequency == 1

    # Check that applying the rule filters out the outlier row
    filtered_lf = lf.filter(_expr(rule.filter_expr)).collect()
    assert 100 not in list(filtered_lf["score"])
    assert len(filtered_lf) == 9


def test_filter_repository_validation_execution(tmp_path: Path) -> None:
    from risc_tool.data.models.data_source import ReadConfig
    from risc_tool.data.repositories.data import DataRepository
    from risc_tool.data.repositories.filter import FilterRepository

    csv_path = tmp_path / "data.csv"
    csv_path.write_text("id,val,name\n1,10.0,Alice\n2,20.0,Bob\n", encoding="utf-8")

    data_repo = DataRepository()
    data_repo.add_data_source("src1", csv_path, ReadConfig())

    filter_repo = FilterRepository(data_repo)

    # Valid execution filter
    f = filter_repo.validate_filter("valid_f", "val > 15")
    assert f.filter_expr is not None

    # Invalid execution filter (type mismatch during Polars execution)
    with pytest.raises(InvalidFilterError) as exc_info:
        filter_repo.validate_filter("invalid_f", "val == name")

    assert "failed execution check" in str(exc_info.value)


# ─── Comprehensive Feature Tests ─────────────────────────────────────────────


def test_comprehensive_arithmetic_operations() -> None:
    # Test basic arithmetic operations (+, -, *, /, //, %, **)
    lf = pl.LazyFrame({"x": [10.0, 20.0, 30.0], "y": [2.0, 3.0, 4.0]})

    # addition & subtraction & comparison
    f1 = _f("(x + y) - 5 > 10", ["x", "y"])
    assert _apply(f1, lf) == [20.0, 30.0]

    # multiplication & division
    f2 = _f("(x * y) / 10 >= 6.0", ["x", "y"])
    assert _apply(f2, lf) == [20.0, 30.0]

    # floor division, modulo, and exponentiation
    f3 = _f(
        "(x // y) % 2 == 0", ["x", "y"]
    )  # 10//2=5 (mod 2 = 1), 20//3=6 (mod 2 = 0), 30//4=7 (mod 2 = 1)
    assert _apply(f3, lf) == [20.0]

    # power (exponentiation)
    f4 = _f("y ** 2 > 5", ["y"])
    assert _apply(f4, lf, "y") == [3.0, 4.0]


def test_comprehensive_comparison_operations() -> None:
    # Test simple and chained comparisons
    lf = pl.LazyFrame({"x": [5, 15, 25, 35]})

    # standard comparisons
    f1 = _f("x < 15", ["x"])
    assert _apply(f1, lf) == [5]

    f2 = _f("x <= 15", ["x"])
    assert _apply(f2, lf) == [5, 15]

    f3 = _f("x > 25", ["x"])
    assert _apply(f3, lf) == [35]

    f4 = _f("x >= 25", ["x"])
    assert _apply(f4, lf) == [25, 35]

    # chained comparisons
    f5 = _f("10 < x <= 30", ["x"])
    assert _apply(f5, lf) == [15, 25]


def test_comprehensive_equality_operations() -> None:
    # Test equality and inequality
    lf = pl.LazyFrame({"x": [1, 2, 3], "y": [1, 4, 3]})

    f1 = _f("x == y", ["x", "y"])
    assert _apply(f1, lf) == [1, 3]

    f2 = _f("x != y", ["x", "y"])
    assert _apply(f2, lf) == [2]


def test_comprehensive_boolean_operations() -> None:
    # Test Boolean AND / OR and short-circuiting behaviour
    lf = pl.LazyFrame({
        "id": [1, 2, 3, 4],
        "x": [True, True, False, False],
        "y": [True, False, True, False],
    })

    f1 = _f("x and y", ["x", "y"])
    assert _apply(f1, lf) == [1]

    f2 = _f("x or y", ["x", "y"])
    assert _apply(f2, lf) == [1, 2, 3]

    # Bitwise operators (which are used for boolean expression compositions)
    f3 = _f("x & y", ["x", "y"])
    assert _apply(f3, lf) == [1]

    f4 = _f("x | y", ["x", "y"])
    assert _apply(f4, lf) == [1, 2, 3]


def test_comprehensive_membership_checks() -> None:
    # Test `in` and `not in` syntax variants
    lf = pl.LazyFrame({"x": [1, 2, 3, 4]})

    # 'in' with a list/tuple
    f1 = _f("x in [1, 3]", ["x"])
    assert _apply(f1, lf) == [1, 3]

    f2 = _f("x in (2, 4)", ["x"])
    assert _apply(f2, lf) == [2, 4]

    # 'not in' with a list/tuple
    f3 = _f("x not in [1, 3]", ["x"])
    assert _apply(f3, lf) == [2, 4]

    f4 = _f("x not in (2, 4)", ["x"])
    assert _apply(f4, lf) == [1, 3]

    # pandas-style equality with lists/tuples resolved in reference
    f5 = _f("x == [1, 3]", ["x"])
    assert _apply(f5, lf) == [1, 3]

    f6 = _f("x != [1, 3]", ["x"])
    assert _apply(f6, lf) == [2, 4]


def test_comprehensive_null_comparisons() -> None:
    # Test checking for nulls via .isna() and .notna()
    lf = pl.LazyFrame({"x": [1.0, None, 3.0]})

    f1 = _f("x.isna()", ["x"])
    assert _apply(f1, lf) == [None]

    f2 = _f("x.notna()", ["x"])
    assert _apply(f2, lf) == [1.0, 3.0]


def test_comprehensive_backtick_identifiers() -> None:
    # Test backticked names with spaces and special characters
    lf = pl.LazyFrame({
        "first name": ["Alice", "Bob", "Charlie"],
        "age-years!": [25, 30, 35],
    })

    f1 = _f("`first name` == 'Bob'", ["first name"])
    assert _apply(f1, lf) == ["Bob"]

    f2 = _f("`age-years!` > 28", ["age-years!"])
    # Note that first column in lf is "first name" so _apply returns list of that column
    assert _apply(f2, lf) == ["Bob", "Charlie"]


def test_comprehensive_unary_operations() -> None:
    # Test unary operators: not, ~, -, +
    lf = pl.LazyFrame({"x": [True, False], "val": [10, -20]})

    f1 = _f("not x", ["x"])
    assert _apply(f1, lf, "x") == [False]

    f2 = _f("~x", ["x"])
    assert _apply(f2, lf, "x") == [False]

    f3 = _f("-val < 0", ["val"])  # -10 < 0 is True, -(-20) = 20 < 0 is False
    assert _apply(f3, lf, "val") == [10]


def test_comprehensive_string_methods() -> None:
    # Test string operations (flat single-method syntax: name.contains, name.startswith, name.endswith)
    lf = pl.LazyFrame({"name": ["Alice", "Bob", "Charlie"]})

    # contains
    f1 = _f("name.contains('li')", ["name"])
    assert _apply(f1, lf) == ["Alice", "Charlie"]

    # startswith / starts_with
    f2 = _f("name.startswith('Al')", ["name"])
    assert _apply(f2, lf) == ["Alice"]

    f2_alt = _f("name.starts_with('Al')", ["name"])
    assert _apply(f2_alt, lf) == ["Alice"]

    # endswith / ends_with
    f3 = _f("name.endswith('ie')", ["name"])
    assert _apply(f3, lf) == ["Charlie"]

    f3_alt = _f("name.ends_with('ie')", ["name"])
    assert _apply(f3_alt, lf) == ["Charlie"]

    # Disallowed syntax: .str namespace explicitly fails validation
    with pytest.raises(InvalidFilterError):
        f_invalid = Filter(FilterID(1), "invalid", "name.str.contains('li')")
        f_invalid.validate_query(available_columns=["name"])


@pytest.mark.parametrize(
    "func_name, expr_str, val_list, expected_matches",
    [
        ("sin", "sin(val) > 0.0", [0.5, 2.5, -1.5], [0.5, 2.5]),
        ("cos", "cos(val) < 0.0", [0.5, 2.5, -1.5], [2.5]),
        ("exp", "exp(val) > 10.0", [0.5, 2.5, -1.5], [2.5]),
        ("log", "log(val) > 0.0", [0.5, 2.5, 0.1], [2.5]),
        ("expm1", "expm1(val) > 10.0", [0.5, 2.5, -1.5], [2.5]),
        ("log1p", "log1p(val) > 1.0", [0.5, 2.5, 0.1], [2.5]),
        ("sqrt", "sqrt(val) > 1.0", [0.5, 2.5, 0.1], [2.5]),
        ("sinh", "sinh(val) > 1.0", [0.5, 2.5, -1.5], [2.5]),
        ("cosh", "cosh(val) > 1.0", [0.5, 2.5, -1.5], [0.5, 2.5, -1.5]),
        ("tanh", "tanh(val) > 0.5", [0.5, 2.5, -1.5], [2.5]),
        ("arcsin", "arcsin(val) > 0.0", [0.5, 0.9, -0.5], [0.5, 0.9]),
        ("arccos", "arccos(val) > 1.0", [0.1, 0.9, -0.5], [0.1, -0.5]),
        ("arctan", "arctan(val) > 0.0", [0.5, 2.5, -1.5], [0.5, 2.5]),
        ("arccosh", "arccosh(val) > 1.0", [1.5, 2.5, 3.5], [2.5, 3.5]),
        ("arcsinh", "arcsinh(val) > 0.0", [0.5, 2.5, -1.5], [0.5, 2.5]),
        ("arctanh", "arctanh(val) > 0.5", [0.5, 0.8, -0.5], [0.5, 0.8]),
        ("abs", "abs(val) > 1.0", [0.5, 2.5, -1.5], [2.5, -1.5]),
        ("log10", "log10(val) > 0.0", [0.5, 2.5, 0.1], [2.5]),
    ],
)
def test_comprehensive_math_functions(
    func_name: str, expr_str: str, val_list: list[float], expected_matches: list[float]
) -> None:
    lf = pl.LazyFrame({"val": val_list})
    f = _f(expr_str, ["val"])
    # filter and check
    res = lf.filter(_expr(f.filter_expr)).collect()["val"].to_list()
    # Check that matches are close to expected
    assert len(res) == len(expected_matches)
    for v in expected_matches:
        assert any(math.isclose(v, r, rel_tol=1e-5) for r in res)


def test_arctan2_math_function() -> None:
    lf = pl.LazyFrame({"y": [1.0, -1.0], "x": [1.0, 1.0]})
    f = _f("arctan2(y, x) > 0.0", ["y", "x"])
    assert _apply(f, lf, "y") == [1.0]


def test_complex_combined_queries() -> None:
    # Set up a dataset with diverse types and names
    lf = pl.LazyFrame({
        "id": [1, 2, 3, 4],
        "x": [10, 20, 30, 40],
        "y": [2.0, 5.0, None, 10.0],
        "status": ["A", "B", "A", "C"],
        "Score Value": [700, 650, 800, 500],
    })

    # Complex Query 1: Arithmetic + comparison + null check + membership check + boolean and
    f1 = _f(
        "((x / 10) + y >= 7) and y.notna() and status in ('A', 'C')",
        ["x", "y", "status"],
    )
    assert _apply(f1, lf, "id") == [4]

    # Complex Query 2: Chained comparison + backticked column + unary not + boolean and
    f2 = _f("15 < x <= 35 and not `Score Value` < 700", ["x", "Score Value"])
    assert _apply(f2, lf, "id") == [3]

    # Complex Query 3: Multi-layer boolean logic + arithmetic + inequality
    f3 = _f(
        "((status == 'A') or (status == 'B')) and (x * y != 100)", ["status", "x", "y"]
    )
    # Row 1: status='A', x*y=20 != 100 (True) -> Keep
    # Row 2: status='B', x*y=100 != 100 (False) -> Filter
    # Row 3: status='A', x*y=None != 100 (Null/False in filter context) -> Filter
    # Row 4: status='C' -> Filter
    assert _apply(f3, lf, "id") == [1]
