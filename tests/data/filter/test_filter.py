import pytest

from risc_tool_v2.data.core.exceptions import InvalidFilterError
from risc_tool_v2.data.core.uid import FilterID
from risc_tool_v2.data.filter.models.filter import Filter


def test_filter_content_hash():
    f1 = Filter(name="Score Filter", query="credit_score > 600")
    f2 = Filter(name="Score Filter", query="credit_score > 600")
    f3 = Filter(name="Other Filter", query="credit_score > 600")

    assert f1.uid == f2.uid
    assert f1.uid != f3.uid
    assert f1.uid != FilterID.UNSET


def test_filter_validation_and_compilation():
    f = Filter(name="Test", query="credit_score > 600")
    f.validate_query(available_columns=["credit_score", "income"])
    assert f.filter_expr is not None
    assert f.used_columns == ["credit_score"]


def test_filter_invalid_query():
    f = Filter(name="Test", query="credit_score == ")
    with pytest.raises(InvalidFilterError):
        f.validate_query(available_columns=["credit_score"])
