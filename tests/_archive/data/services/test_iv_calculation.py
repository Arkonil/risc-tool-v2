import polars as pl

from risc_tool.data.services.iv_calculation import calculate_iv


def test_calculate_iv_basic() -> None:
    # Set up basic data where input variable perfectly separates target
    # low variable values -> target 0, high variable values -> target 1
    variable = pl.Series("var", [1.0, 2.0, 10.0, 11.0])
    target = pl.Series("tgt", [0, 0, 1, 1])

    iv = calculate_iv(variable, target)
    assert iv > 0.0


def test_calculate_iv_with_categorical() -> None:
    variable = pl.Series("var", ["A", "A", "B", "B"])
    target = pl.Series("tgt", [0, 1, 0, 1])

    iv = calculate_iv(variable, target)
    # Since variable has identical distribution of good/bad (50% for A, 50% for B), IV should be near 0
    assert abs(iv) < 1e-4


def test_calculate_iv_boolean_target() -> None:
    variable = pl.Series("var", [1, 2, 3, 4])
    target = pl.Series("tgt", [False, False, True, True])

    iv = calculate_iv(variable, target)
    assert iv > 0.0


def test_calculate_iv_missing_class_returns_zero() -> None:
    # Target only contains one class (e.g. only 0s)
    variable = pl.Series("var", [1, 2, 3, 4])
    target = pl.Series("tgt", [0, 0, 0, 0])

    iv = calculate_iv(variable, target)
    assert iv == 0.0


def test_calculate_iv_empty_dataframe_returns_zero() -> None:
    variable = pl.Series("var", [])
    target = pl.Series("tgt", [])

    iv = calculate_iv(variable, target)
    assert iv == 0.0
