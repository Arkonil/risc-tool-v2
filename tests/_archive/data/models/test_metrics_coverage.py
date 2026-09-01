import math
from typing import Any

import polars as pl
import pytest

from risc_tool.data.models.metric import Metric
from risc_tool.data.models.uid import DataSourceID, MetricID

# ─── Helpers ───────────────────────────────────────────────────────────────────


def _m(
    query: str,
    columns: list[str],
    data_source_ids: list[DataSourceID] | None = None,
) -> Metric:
    """Build and validate a Metric, returning it ready for execution."""
    if data_source_ids is None:
        data_source_ids = [DataSourceID(1)]
    m = Metric(
        uid=MetricID(1),
        name="test",
        query=query,
        data_source_ids=data_source_ids,
        is_cumulative=False,
    )
    m.validate_query(available_columns=columns)
    assert m.metric_expr is not None
    return m


def _eval(m: Metric, lf: pl.LazyFrame) -> Any:
    """Evaluate a metric expression against a LazyFrame and return the scalar result."""
    return lf.select(m.metric_expr).collect().item(0, 0)


def _eval_grouped(m: Metric, lf: pl.LazyFrame, group_by: str) -> dict[str, Any]:
    """Evaluate a metric grouped by a column, returning a {group: value} dict."""
    return dict(
        lf.group_by(group_by).agg(m.metric_expr).sort(group_by).collect().iter_rows()
    )


# ─── Unary Operators ──────────────────────────────────────────────────────────


def test_unary_operators() -> None:
    lf = pl.LazyFrame({
        "val": [10.0, -20.0, 30.0, -40.0],
        "flag": [True, False, True, False],
    })

    # unary invert (~flag).sum() — count of True values
    m = _m("(~`flag`).sum()", ["flag"])
    assert _eval(m, lf) == 2.0

    # unary negate (-val).sum()
    m = _m("(-`val`).sum()", ["val"])
    assert _eval(m, lf) == 20.0  # -10 + 20 + -30 + 40 = 20

    # unary plus (+val).sum()
    m = _m("(+`val`).sum()", ["val"])
    assert _eval(m, lf) == -20.0  # 10 + -20 + 30 + -40 = -20


# ─── Extended Binary Operators ────────────────────────────────────────────────


def test_binary_operators_floor_mod_pow() -> None:
    lf = pl.LazyFrame({"a": [10.0, 20.0, 30.0], "b": [3.0, 6.0, 4.0]})

    # floor division: sum(a)=60, sum(b)=13, 60//13 = 4
    m = _m("(`a`.sum() // `b`.sum())", ["a", "b"])
    assert _eval(m, lf) == 4.0

    # modulo
    m = _m("(`a`.sum() % `b`.sum())", ["a", "b"])
    assert _eval(m, lf) == 8.0  # 60 % 13 = 8

    # power
    lf2 = pl.LazyFrame({"val": [1.0, 2.0, 3.0]})
    m = _m("(`val`.sum() ** 2)", ["val"])
    assert _eval(m, lf2) == 36.0  # 6^2


def test_binary_bitwise_operators_blocked_by_validator() -> None:
    # lf = pl.LazyFrame({
    #     "b1": [1, 0, 1, 0],
    #     "b2": [1, 1, 0, 0],
    # })
    # NOTE: The compiler handles `BitAnd`/`BitOr`/`BitXor` (metric.py:389-394)
    #       but the validator's `allowed_operators` tuple excludes them (metric.py:53-61).
    #       This is an inconsistency — the validator should be updated to include them.
    for expr in ["(`b1` & `b2`).sum()", "(`b1` | `b2`).sum()", "(`b1` ^ `b2`).sum()"]:
        with pytest.raises(TypeError, match="Unsupported binary operator"):
            _m(expr, ["b1", "b2"])


# ─── Comparison Operators ─────────────────────────────────────────────────────


def test_comparison_equality() -> None:
    lf = pl.LazyFrame({"val": [1, 2, 3, 1]})

    # ==
    m = _m("(`val` == 1).sum()", ["val"])
    assert _eval(m, lf) == 2.0

    # !=
    m = _m("(`val` != 1).sum()", ["val"])
    assert _eval(m, lf) == 2.0

    # cross-column equality
    lf2 = pl.LazyFrame({"a": [1, 2, 3], "b": [1, 0, 3]})
    m = _m("(`a` == `b`).sum()", ["a", "b"])
    assert _eval(m, lf2) == 2.0


def test_comparison_ordering() -> None:
    lf = pl.LazyFrame({"val": [5, 10, 15, 20]})

    # <
    m = _m("(`val` < 15).sum()", ["val"])
    assert _eval(m, lf) == 2.0

    # <=
    m = _m("(`val` <= 15).sum()", ["val"])
    assert _eval(m, lf) == 3.0

    # >
    m = _m("(`val` > 15).sum()", ["val"])
    assert _eval(m, lf) == 1.0

    # >=
    m = _m("(`val` >= 15).sum()", ["val"])
    assert _eval(m, lf) == 2.0


def test_comparison_membership() -> None:
    lf = pl.LazyFrame({"val": [1, 2, 3, 4, 5]})

    # in with list
    m = _m("(`val`.isin([1, 3, 5])).sum()", ["val"])
    assert _eval(m, lf) == 3.0

    # in with tuple — uses ast.Tuple literal
    m = _m("(`val`.isin((1, 3, 5))).sum()", ["val"])
    assert _eval(m, lf) == 3.0

    # not in
    m = _m("(~`val`.isin([1, 3, 5])).sum()", ["val"])
    assert _eval(m, lf) == 2.0


def test_comparison_compare_in_not_in() -> None:
    lf = pl.LazyFrame({"val": [1, 2, 3, 4, 5]})

    # ast.Compare with Eq + List — translated to is_in
    m = _m("(`val` == [1, 3, 5]).sum()", ["val"])
    assert _eval(m, lf) == 3.0

    # ast.Compare with NotEq + List — translated to ~is_in
    m = _m("(`val` != [1, 3, 5]).sum()", ["val"])
    assert _eval(m, lf) == 2.0

    # ast.Compare with In
    m = _m("(`val` in [1, 3, 5]).sum()", ["val"])
    assert _eval(m, lf) == 3.0

    # ast.Compare with NotIn
    m = _m("(`val` not in [1, 3, 5]).sum()", ["val"])
    assert _eval(m, lf) == 2.0


def test_chained_comparison() -> None:
    lf = pl.LazyFrame({"val": [5, 15, 25, 35]})

    # chained: 10 < val <= 30 → (val > 10) & (val <= 30)
    m = _m("(10 < `val` <= 30).sum()", ["val"])
    assert _eval(m, lf) == 2.0  # 15 and 25


# ─── Horizontal Functions ─────────────────────────────────────────────────────


def test_horizontal_functions() -> None:
    lf = pl.LazyFrame({
        "a": [1.0, 10.0],
        "b": [2.0, 20.0],
        "c": [3.0, 30.0],
    })

    # horizontal min
    m = _m("min(a, b, c).sum()", ["a", "b", "c"])
    assert _eval(m, lf) == 11.0  # min per row: 1 + 10 = 11

    # horizontal max: row0 max(1,2,3)=3, row1 max(10,20,30)=30, sum=33
    m = _m("max(a, b, c).sum()", ["a", "b", "c"])
    assert _eval(m, lf) == 33.0

    # horizontal std
    m = _m("std(a, b, c).sum()", ["a", "b", "c"])
    res = _eval(m, lf)
    # Row 0 std of [1,2,3] = 1.0, Row 1 std of [10,20,30] = 10.0 → sum = 11.0
    assert abs(res - 11.0) < 1e-5


# ─── Math Functions ───────────────────────────────────────────────────────────


def test_math_functions_single_arg() -> None:
    lf = pl.LazyFrame({"val": [4.0, 9.0, 16.0, 1.0]})

    # sqrt then aggregate
    m = _m("sqrt(`val`).sum()", ["val"])
    assert abs(_eval(m, lf) - 10.0) < 1e-6  # 2 + 3 + 4 + 1

    # log then aggregate
    m = _m("log(`val`).sum()", ["val"])
    res = _eval(m, lf)
    expected = math.log(4) + math.log(9) + math.log(16) + math.log(1)
    assert abs(res - expected) < 1e-6

    # abs then aggregate
    lf2 = pl.LazyFrame({"val": [-5.0, 3.0, -2.0]})
    m = _m("abs(`val`).sum()", ["val"])
    assert _eval(m, lf2) == 10.0

    # exp then sum
    m = _m("exp(`val`).sum()", ["val"])
    res = _eval(m, lf)
    expected = math.exp(4) + math.exp(9) + math.exp(16) + math.exp(1)
    assert abs(res - expected) < 1e-4

    # log1p, sinh, cosh, tanh
    for fn in ["log1p", "sinh", "cosh", "tanh"]:
        m = _m(f"{fn}(`val`).sum()", ["val"])
        assert m.metric_expr is not None

    # arccosh requires x >= 1, so use values >= 2
    lf3 = pl.LazyFrame({"val": [2.0, 3.0, 4.0]})
    m = _m("arccosh(`val`).sum()", ["val"])
    res = _eval(m, lf3)
    expected = math.acosh(2) + math.acosh(3) + math.acosh(4)
    assert abs(res - expected) < 1e-6

    # arcsin, arccos, arctan, arcsinh, arctanh
    # lf4 = pl.LazyFrame({"val": [0.5, 0.75, 0.25]})
    for fn in ["arcsin", "arccos", "arctan", "arcsinh", "arctanh"]:
        m = _m(f"{fn}(`val`).sum()", ["val"])
        assert m.metric_expr is not None

    # log10
    m = _m("log10(`val`).sum()", ["val"])
    res = _eval(m, lf)
    expected = math.log10(4) + math.log10(9) + math.log10(16) + math.log10(1)
    assert abs(res - expected) < 1e-6

    # expm1
    m = _m("expm1(`val`).sum()", ["val"])
    res = _eval(m, lf)
    expected = (
        (math.exp(4) - 1) + (math.exp(9) - 1) + (math.exp(16) - 1) + (math.exp(1) - 1)
    )
    assert abs(res - expected) < 1e-4


def test_arctan2_math_function() -> None:
    lf = pl.LazyFrame({"x": [1.0, 1.0], "y": [1.0, -1.0]})
    m = _m("arctan2(`y`, `x`).sum()", ["x", "y"])
    res = _eval(m, lf)
    expected = math.atan2(1.0, 1.0) + math.atan2(-1.0, 1.0)
    assert abs(res - expected) < 1e-6


# ─── Series Methods (comprehensive) ──────────────────────────────────────────


@pytest.fixture
def series_lf() -> pl.LazyFrame:
    return pl.LazyFrame({
        "a": [1.0, 2.0, 3.0, 4.0, 5.0],
        "b": [2.0, 3.0, 5.0, 7.0, 11.0],
        "__TOTAL_SIZE__": [5, 5, 5, 5, 5],
    })


def test_series_method_basic_aggregations(series_lf: pl.LazyFrame) -> None:
    # .sum() — already tested in original, but verify standalone
    m = _m("`a`.sum()", ["a"])
    assert _eval(m, series_lf) == 15.0

    # .mean()
    m = _m("`a`.mean()", ["a"])
    assert _eval(m, series_lf) == 3.0

    # .median()
    m = _m("`a`.median()", ["a"])
    assert _eval(m, series_lf) == 3.0

    # .min()
    m = _m("`a`.min()", ["a"])
    assert _eval(m, series_lf) == 1.0

    # .max()
    m = _m("`a`.max()", ["a"])
    assert _eval(m, series_lf) == 5.0

    # .std()
    m = _m("`a`.std()", ["a"])
    res = _eval(m, series_lf)
    # std of [1,2,3,4,5] = sqrt(2.5) ≈ 1.5811
    assert abs(res - 1.58113883) < 1e-5

    # .var()
    m = _m("`a`.var()", ["a"])
    res = _eval(m, series_lf)
    assert abs(res - 2.5) < 1e-5

    # .count()
    m = _m("`a`.count()", ["a"])
    assert _eval(m, series_lf) == 5.0


def test_series_method_skew_kurt(series_lf: pl.LazyFrame) -> None:
    # .skew()
    m = _m("`a`.skew()", ["a"])
    res = _eval(m, series_lf)
    assert abs(res - 0.0) < 1e-4  # symmetric distribution

    # .kurt()
    m = _m("`a`.kurt()", ["a"])
    res = _eval(m, series_lf)
    assert res is not None

    # .kurtosis() (alias)
    m = _m("`a`.kurtosis()", ["a"])
    res2 = _eval(m, series_lf)
    assert abs(res - res2) < 1e-10


def test_series_method_prod_sem(series_lf: pl.LazyFrame) -> None:
    # .prod()
    m = _m("`a`.prod()", ["a"])
    assert _eval(m, series_lf) == 120.0  # 1*2*3*4*5

    # .sem()
    m = _m("`a`.sem()", ["a"])
    res = _eval(m, series_lf)
    # sem = std / sqrt(n) ≈ 1.5811 / sqrt(5) ≈ 0.7071
    assert abs(res - 0.70710678) < 1e-5


def test_series_method_mode_all_any(series_lf: pl.LazyFrame) -> None:
    # .mode()
    lf = pl.LazyFrame({"x": [1.0, 1.0, 2.0, 3.0, 3.0, 3.0]})
    m = _m("`x`.mode()", ["x"])
    assert _eval(m, lf) == 3.0

    # .all() — all non-zero?
    lf2 = pl.LazyFrame({"x": [1, 0, 1]})
    m = _m("`x`.all()", ["x"])
    assert _eval(m, lf2) is False

    # .any()
    m = _m("`x`.any()", ["x"])
    assert _eval(m, lf2) is True


def test_series_method_autocorr(series_lf: pl.LazyFrame) -> None:
    # .autocorr() — correlation with lag-1
    m = _m("`a`.autocorr()", ["a"])
    res = _eval(m, series_lf)
    # autocorr of [1,2,3,4,5] with lag 1
    # x = [1,2,3,4,5], x_shifted = [None,1,2,3,4]
    # corr of [1,2,3,4] with [2,3,4,5] = 1.0 (perfect linear)
    assert abs(res - 1.0) < 1e-5


def test_series_method_isna_notna() -> None:
    lf = pl.LazyFrame({"x": [1.0, None, 3.0]})

    # .isna()
    m = _m("`x`.isna().sum()", ["x"])
    assert _eval(m, lf) == 1.0

    # .notna()
    m = _m("`x`.notna().sum()", ["x"])
    assert _eval(m, lf) == 2.0


def test_series_method_is_in_variant(series_lf: pl.LazyFrame) -> None:
    # .is_in() (alternative spelling of isin)
    m = _m("`a`.is_in([1, 3, 5]).sum()", ["a"])
    assert _eval(m, series_lf) == 3.0


def test_series_method_n_unique_blocked_by_validator(series_lf: pl.LazyFrame) -> None:
    # NOTE: The compiler handles `n_unique` (metric.py:533) but the validator's
    #       `allowed_series_methods` (metric.py:27-51) only includes `nunique`.
    #       The scalar check fails first since `n_unique` is not in the allowed set.
    with pytest.raises(ValueError, match="does not appear to be a scalar"):
        _m("`x`.n_unique()", ["x"])


def test_series_method_product_blocked_by_validator(series_lf: pl.LazyFrame) -> None:
    # NOTE: The compiler handles `product` (metric.py:548-549) but the validator's
    #       `allowed_series_methods` only includes `prod`.
    #       The scalar check fails first since `product` is not in the allowed set.
    with pytest.raises(ValueError, match="does not appear to be a scalar"):
        _m("`a`.product()", ["a"])


# ─── Attribute Access (.isna / .notna) ────────────────────────────────────────


def test_attribute_isna_notna() -> None:
    lf = pl.LazyFrame({"x": [1.0, None, 3.0, None]})

    # .isna attribute (not method) — aggregated
    m = _m("(`x`.isna).sum()", ["x"])
    assert _eval(m, lf) == 2.0

    # .notna attribute (not method) — aggregated
    m = _m("(`x`.notna).sum()", ["x"])
    assert _eval(m, lf) == 2.0


# ─── Special Names and Literals ──────────────────────────────────────────────


def test_special_name_true_false() -> None:
    lf = pl.LazyFrame({"val": [1, 0, 1, 1]})

    # The expression (`val` == True).sum() uses both ast.Constant(True) and
    # ast.Name('True') depending on how Python parses it.
    # ast.parse("`val` == True", mode="eval") → Compare with Name('True')
    # Compare handler → compile_sub for comparator → Name handler → pl.lit(True)
    m = _m("(`val` == True).sum()", ["val"])
    assert _eval(m, lf) == 3.0  # rows where val == 1 (True treated as 1)

    m = _m("(`val` == False).sum()", ["val"])
    assert _eval(m, lf) == 1.0  # row where val == 0


def test_special_name_none() -> None:
    # None as a constant literal (pl.lit(None)) — produces null in output
    lf = pl.LazyFrame({"dummy": [1]})
    m = _m("None", ["dummy"])
    assert _eval(m, lf) is None


def test_special_name_missing() -> None:
    # __MISSING__ is a valid scalar name → pl.lit(None)
    lf = pl.LazyFrame({"dummy": [1]})
    m = _m("__MISSING__", ["dummy"])
    assert _eval(m, lf) is None


def test_special_name_total_size() -> None:
    lf = pl.LazyFrame({
        "val": [1.0, 2.0, 3.0],
        "__TOTAL_SIZE__": [10, 10, 10],
    })
    m = _m("`val`.sum() / __TOTAL_SIZE__", ["val"])
    assert abs(_eval(m, lf) - 0.6) < 1e-6


# ─── Backtick Special Characters ──────────────────────────────────────────────


def test_backtick_special_characters() -> None:
    lf = pl.LazyFrame({
        "col name": [1.0, 2.0, 3.0],
        "field.with.dots": [4.0, 5.0, 6.0],
        "年收入": [7.0, 8.0, 9.0],
    })

    # Column name with space
    m = _m("`col name`.sum()", ["col name"])
    assert _eval(m, lf) == 6.0

    # Column name with dots
    m = _m("`field.with.dots`.sum()", ["field.with.dots"])
    assert _eval(m, lf) == 15.0

    # Column name with unicode
    m = _m("`年收入`.sum()", ["年收入"])
    assert _eval(m, lf) == 24.0


# ─── Edge Cases for is_result_scalar ──────────────────────────────────────────


def test_is_result_scalar_edge_cases() -> None:
    lf = pl.LazyFrame({"val": [1.0, 2.0, 3.0]})

    # Plain constant is scalar
    m = _m("5", ["val"])
    assert m.metric_expr is not None

    # BinOp of two constants is scalar
    m = _m("5 + 3", ["val"])
    assert _eval(m, lf) == 8.0

    # BinOp of constant and aggregated expression
    m = _m("`val`.sum() + 10", ["val"])
    assert _eval(m, lf) == 16.0  # 6 + 10

    # Complex nested BinOp
    m = _m("(`val`.sum() * 2) - (`val`.mean() / 3)", ["val"])
    res = _eval(m, lf)
    expected = (6.0 * 2) - (2.0 / 3)
    assert abs(res - expected) < 1e-6
