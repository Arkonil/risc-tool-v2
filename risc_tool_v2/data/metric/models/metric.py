"""Metric model with query validation and Polars expression compilation."""

import ast
import json
import logging
import re
import typing as t
from uuid import NAMESPACE_URL, uuid5

import numpy as np
import polars as pl
from pydantic import BaseModel, ConfigDict, PrivateAttr, model_validator

from risc_tool_v2.data.core.uid import DataSourceID, MetricID
from risc_tool_v2.data.core.utils.logging import get_logger
from risc_tool_v2.data.metric.json.metric_json import MetricJSON

MISSING = None
Scalar = int | float | str | bool | None


class MetricQueryValidator(ast.NodeVisitor):
    allowed_functions: t.ClassVar[set[str]] = {
        "sum",
        "mean",
        "median",
        "min",
        "max",
        "std",
    }

    allowed_series_methods: t.ClassVar[set[str]] = {
        "all",
        "any",
        "autocorr",
        "corr",
        "count",
        "cov",
        "kurt",
        "max",
        "mean",
        "median",
        "min",
        "mode",
        "prod",
        "quantile",
        "sem",
        "skew",
        "std",
        "sum",
        "var",
        "kurtosis",
        "nunique",
        "isin",
        "is_in",
    }

    allowed_operators: t.ClassVar[tuple[type[ast.AST], ...]] = (
        ast.Add,
        ast.Sub,
        ast.Mult,
        ast.Div,
        ast.Pow,
        ast.Mod,
        ast.FloorDiv,
    )

    allowed_names: t.ClassVar[set[str]] = {"__MISSING__", "__TOTAL_SIZE__"}
    allowed_series_attributes: t.ClassVar[set[str]] = {"size"}

    def __init__(self, placeholder_map: dict[str, str]):
        self.found_columns: set[str] = set()
        self.placeholder_map = placeholder_map

    def _resolve_and_add_name(self, identifier: str):
        if identifier.startswith("@"):
            return

        if identifier in self.allowed_names:
            return

        original_name = self.placeholder_map.get(identifier, identifier)
        if (
            identifier.startswith("__BACKTICKED_")
            and identifier not in self.placeholder_map
        ):
            return

        self.found_columns.add(original_name)
        self.placeholder_map[identifier] = original_name

    def visit_Name(self, node: ast.Name):
        self._resolve_and_add_name(node.id)

    def visit_Attribute(self, node: ast.Attribute):
        current_obj = node
        while isinstance(current_obj, ast.Attribute):
            current_obj = current_obj.value

        if isinstance(current_obj, ast.Name):
            self._resolve_and_add_name(current_obj.id)
        else:
            self.visit(current_obj)

    def visit_Call(self, node: ast.Call):
        if isinstance(node.func, ast.Name):
            if node.func.id not in self.allowed_functions:
                math_fns = {
                    "sin",
                    "cos",
                    "exp",
                    "log",
                    "log1p",
                    "sqrt",
                    "sinh",
                    "cosh",
                    "tanh",
                    "arcsin",
                    "arccos",
                    "arctan",
                    "arccosh",
                    "arcsinh",
                    "arctanh",
                    "abs",
                    "arctan2",
                    "log10",
                    "expm1",
                }
                if node.func.id not in math_fns:
                    raise ValueError(f"Unsupported function: {node.func.id}")
        else:
            self.visit(node.func)

        for arg in node.args:
            self.visit(arg)

        for kwarg in node.keywords:
            self.visit(kwarg.value)

    def visit_BinOp(self, node: ast.BinOp):
        if not isinstance(node.op, self.allowed_operators):
            raise TypeError(f"Unsupported binary operator: {type(node.op).__name__}")

        self.visit(node.left)
        self.visit(node.right)

    def is_result_scalar(self, expr_node: ast.AST) -> bool:
        if isinstance(expr_node, ast.Name):
            return expr_node.id in self.allowed_names

        if isinstance(expr_node, ast.Constant):
            return True

        if isinstance(expr_node, ast.BinOp):
            return all([
                isinstance(expr_node.op, self.allowed_operators),
                self.is_result_scalar(expr_node.left),
                self.is_result_scalar(expr_node.right),
            ])

        if isinstance(expr_node, ast.Call):
            if isinstance(expr_node.func, ast.Name):
                return all(self.is_result_scalar(arg) for arg in expr_node.args)
            elif isinstance(expr_node.func, ast.Attribute):
                func_name = expr_node.func.attr

                if func_name == "quantile":
                    if expr_node.args:
                        return isinstance(expr_node.args[0], ast.Constant)

                    if expr_node.keywords:
                        for kw in expr_node.keywords:
                            if kw.arg == "quantile":
                                return isinstance(kw.value, ast.Constant)

                return func_name in self.allowed_series_methods

        if isinstance(expr_node, ast.Attribute):
            return expr_node.attr in self.allowed_series_attributes

        return False


class Metric(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    uid: MetricID = MetricID.UNSET
    name: str
    query: str
    data_source_ids: list[DataSourceID]
    is_cumulative: bool
    use_thousand_sep: bool = True
    is_percentage: bool = False
    decimal_places: int = 2

    _logger: logging.Logger = PrivateAttr(default_factory=lambda: get_logger("Metric"))
    _used_columns: list[str] = PrivateAttr(default_factory=list)
    _processed_query: str = PrivateAttr(default="")
    _placeholder_map: dict[str, str] = PrivateAttr(default_factory=dict)
    _metric_expr: pl.Expr | None = PrivateAttr(default=None)

    @model_validator(mode="after")
    def _derive_uid(self) -> "Metric":
        if not self._processed_query:
            object.__setattr__(self, "_processed_query", self.query)

        if self.uid is MetricID.UNSET:
            object.__setattr__(self, "uid", self.create_hash())
        return self

    def create_hash(self) -> MetricID:
        payload = json.dumps(
            {
                "name": self.name,
                "query": self.query,
                "data_source_ids": sorted(str(ds_id) for ds_id in self.data_source_ids),
                "is_cumulative": self.is_cumulative,
                "use_thousand_sep": self.use_thousand_sep,
                "is_percentage": self.is_percentage,
                "decimal_places": self.decimal_places,
            },
            sort_keys=True,
        )
        return MetricID(uuid5(NAMESPACE_URL, payload))

    def with_updates(self, **updates: t.Any) -> "Metric":
        fields: dict[str, t.Any] = {
            "name": self.name,
            "query": self.query,
            "data_source_ids": list(self.data_source_ids),
            "is_cumulative": self.is_cumulative,
            "use_thousand_sep": self.use_thousand_sep,
            "is_percentage": self.is_percentage,
            "decimal_places": self.decimal_places,
        }
        content_changed = any(
            key in updates and updates[key] != fields[key] for key in fields
        )
        fields.update(updates)

        uid: MetricID | None
        if "uid" in updates:
            uid = fields.pop("uid")
        elif content_changed and self.uid not in (MetricID.EMPTY, MetricID.TEMPORARY):
            uid = None
        else:
            uid = self.uid

        new_metric = Metric(**({"uid": uid} if uid is not None else {}), **fields)

        if new_metric.query == self.query:
            new_metric._used_columns = list(self.used_columns)
            new_metric._processed_query = self.processed_query
            new_metric._placeholder_map = dict(self.placeholder_map)
            new_metric._metric_expr = self.metric_expr

        return new_metric

    @property
    def pretty_name(self) -> str:
        return self.name

    def format(self, value: float | None) -> str | float | None:
        if value is None or (isinstance(value, float) and np.isnan(value)):
            return value

        formatter = f"{{:{',' if self.use_thousand_sep else ''}.{self.decimal_places}f}}{'%' if self.is_percentage else ''}"
        return formatter.format(value)

    @property
    def used_columns(self) -> list[str]:
        return self._used_columns

    @property
    def processed_query(self) -> str:
        return self._processed_query

    @property
    def placeholder_map(self) -> dict[str, str]:
        return self._placeholder_map

    @property
    def metric_expr(self) -> pl.Expr | None:
        return self._metric_expr

    def validate_query(self, available_columns: list[str] | None = None) -> None:
        self._logger.info(
            "Validating metric query '%s' for metric '%s'", self.query, self.name
        )

        if not self.query.strip():
            raise ValueError("Query cannot be empty.")

        backticked_map: dict[str, str] = {}

        def replace_backtick(match: re.Match[str]) -> str:
            name_inside_ticks = match.group(1)
            placeholder = f"__BACKTICKED_{len(backticked_map)}__"
            backticked_map[placeholder] = name_inside_ticks
            return placeholder

        processed_expression = re.sub(r"`([^`]+)`", replace_backtick, self.query)

        try:
            expr_node = ast.parse(processed_expression, mode="eval").body
        except SyntaxError as e:
            self._logger.warning("Syntax error in metric query '%s': %s", self.query, e)
            raise ValueError(f"Syntax error in expression: {e}")

        validator = MetricQueryValidator(backticked_map)

        if not validator.is_result_scalar(expr_node):
            node_type_name = type(expr_node).__name__
            self._logger.error(
                "Metric query validation failed: expression is not a scalar"
            )
            raise ValueError(
                f"Expression does not appear to be a scalar value; top-level operation is '{node_type_name}'."
            )

        validator.visit(expr_node)

        self._used_columns = sorted(validator.found_columns)
        self._placeholder_map = validator.placeholder_map
        self._processed_query = processed_expression

        if available_columns is not None:
            available_set = set(available_columns)
            used_set = set(self.used_columns)
            missing_columns = sorted(used_set - available_set)
            if missing_columns:
                self._logger.error(
                    "Metric query validation failed: missing columns %s",
                    missing_columns,
                )
                raise ValueError(
                    f"Following columns are not found in the data: {', '.join(missing_columns)}"
                )

        try:
            self._metric_expr = self._compile_expression(expr_node, backticked_map)
        except (ValueError, TypeError) as e:
            self._logger.error("Failed to compile metric query '%s': %s", self.query, e)
            raise ValueError(f"Failed to compile to Polars expression: {e}")

    def _compile_expression(
        self, node: ast.AST, backticked_map: dict[str, str]
    ) -> pl.Expr:
        def require_expr(value: t.Any, context: str) -> pl.Expr:
            if isinstance(value, pl.Expr):
                return value
            raise ValueError(f"{context} expects an expression operand")

        def eval_lit_value(n: ast.AST) -> t.Any:
            if isinstance(n, ast.Constant):
                return n.value
            elif isinstance(n, (ast.List, ast.Tuple)):
                return [eval_lit_value(el) for el in n.elts]
            elif isinstance(n, ast.Name):
                name = backticked_map.get(n.id, n.id)
                if name == "True":
                    return True
                elif name == "False":
                    return False
                elif name == "None":
                    return None
            raise ValueError("Not a literal value")

        def compile_sub(n: ast.AST) -> t.Any:
            if isinstance(n, ast.Name):
                name = backticked_map.get(n.id, n.id)
                if name == "True":
                    return pl.lit(True)
                elif name == "False":
                    return pl.lit(False)
                elif name == "None" or name == "__MISSING__":
                    return pl.lit(None)
                elif name == "__TOTAL_SIZE__":
                    return pl.col("__TOTAL_SIZE__").first()
                return pl.col(name)

            elif isinstance(n, ast.Constant):
                return pl.lit(n.value)

            elif isinstance(n, ast.UnaryOp):
                operand = require_expr(compile_sub(n.operand), "Unary operator")
                if isinstance(n.op, (ast.Not, ast.Invert)):
                    return ~operand
                elif isinstance(n.op, ast.USub):
                    return -operand
                elif isinstance(n.op, ast.UAdd):
                    return operand
                raise ValueError(f"Unsupported unary operator: {type(n.op).__name__}")

            elif isinstance(n, ast.BinOp):
                left = require_expr(compile_sub(n.left), "Binary operator LHS")
                right = require_expr(compile_sub(n.right), "Binary operator RHS")
                op = n.op
                if isinstance(op, ast.Add):
                    return left + right
                elif isinstance(op, ast.Sub):
                    return left - right
                elif isinstance(op, ast.Mult):
                    return left * right
                elif isinstance(op, ast.Div):
                    return left / right
                elif isinstance(op, ast.FloorDiv):
                    return left // right
                elif isinstance(op, ast.Mod):
                    return left % right
                elif isinstance(op, ast.Pow):
                    return left**right
                elif isinstance(op, ast.BitAnd):
                    return left & right
                elif isinstance(op, ast.BitOr):
                    return left | right
                elif isinstance(op, ast.BitXor):
                    return left ^ right
                raise ValueError(f"Unsupported binary operator: {type(op).__name__}")

            elif isinstance(n, ast.Compare):
                left_compiled = require_expr(compile_sub(n.left), "Comparison LHS")
                exprs: list[pl.Expr] = []
                curr_left_compiled = left_compiled

                for idx, (op, comparator) in enumerate(zip(n.ops, n.comparators)):
                    right_compiled = compile_sub(comparator)
                    is_list_or_tuple = isinstance(comparator, (ast.List, ast.Tuple))

                    if isinstance(op, ast.Eq):
                        if is_list_or_tuple:
                            term = curr_left_compiled.is_in(right_compiled)
                        else:
                            term = curr_left_compiled == require_expr(
                                right_compiled, "Equality RHS"
                            )
                    elif isinstance(op, ast.NotEq):
                        if is_list_or_tuple:
                            term = ~curr_left_compiled.is_in(right_compiled)
                        else:
                            term = curr_left_compiled != require_expr(
                                right_compiled, "Inequality RHS"
                            )
                    elif isinstance(op, ast.Lt):
                        term = curr_left_compiled < require_expr(
                            right_compiled, "Lt RHS"
                        )
                    elif isinstance(op, ast.LtE):
                        term = curr_left_compiled <= require_expr(
                            right_compiled, "LtE RHS"
                        )
                    elif isinstance(op, ast.Gt):
                        term = curr_left_compiled > require_expr(
                            right_compiled, "Gt RHS"
                        )
                    elif isinstance(op, ast.GtE):
                        term = curr_left_compiled >= require_expr(
                            right_compiled, "GtE RHS"
                        )
                    elif isinstance(op, ast.In):
                        term = curr_left_compiled.is_in(right_compiled)
                    elif isinstance(op, ast.NotIn):
                        term = ~curr_left_compiled.is_in(right_compiled)
                    else:
                        raise TypeError(
                            f"Unsupported comparison operator: {type(op).__name__}"
                        )

                    exprs.append(term)
                    if idx < len(n.ops) - 1:
                        curr_left_compiled = require_expr(
                            right_compiled, "Chained comparison"
                        )

                if len(exprs) == 1:
                    return exprs[0]
                res = exprs[0]
                for e in exprs[1:]:
                    res = res & e
                return res

            elif isinstance(n, ast.Call):
                if isinstance(n.func, ast.Name):
                    fn_name = n.func.id
                    compiled_args = [compile_sub(arg) for arg in n.args]
                    if fn_name == "sum":
                        return pl.sum_horizontal(*compiled_args)
                    elif fn_name == "mean":
                        return pl.mean_horizontal(*compiled_args)
                    elif fn_name == "median":
                        return pl.concat_list(compiled_args).list.median()
                    elif fn_name == "min":
                        return pl.min_horizontal(*compiled_args)
                    elif fn_name == "max":
                        return pl.max_horizontal(*compiled_args)
                    elif fn_name == "std":
                        return pl.concat_list(compiled_args).list.std()
                    elif fn_name in (
                        "sin",
                        "cos",
                        "exp",
                        "log",
                        "log1p",
                        "sqrt",
                        "sinh",
                        "cosh",
                        "tanh",
                        "arcsin",
                        "arccos",
                        "arctan",
                        "arccosh",
                        "arcsinh",
                        "arctanh",
                        "abs",
                        "log10",
                    ):
                        if len(compiled_args) != 1:
                            raise ValueError(f"{fn_name} requires exactly 1 argument")
                        return getattr(compiled_args[0], fn_name)()
                    elif fn_name == "arctan2":
                        if len(compiled_args) != 2:
                            raise ValueError("arctan2 requires exactly 2 arguments")
                        return pl.arctan2(compiled_args[0], compiled_args[1])
                    elif fn_name == "expm1":
                        if len(compiled_args) != 1:
                            raise ValueError("expm1 requires exactly 1 argument")
                        return compiled_args[0].exp() - 1

                    raise ValueError(f"Unsupported function call: {fn_name}")

                elif isinstance(n.func, ast.Attribute):
                    target = require_expr(compile_sub(n.func.value), "Method target")
                    method_name = n.func.attr
                    compiled_args = [compile_sub(arg) for arg in n.args]

                    if method_name == "sum":
                        return target.sum()
                    elif method_name == "mean":
                        return target.mean()
                    elif method_name == "median":
                        return target.median()
                    elif method_name == "min":
                        return target.min()
                    elif method_name == "max":
                        return target.max()
                    elif method_name == "std":
                        return target.std()
                    elif method_name == "var":
                        return target.var()
                    elif method_name == "skew":
                        return target.skew()
                    elif method_name in ("kurt", "kurtosis"):
                        return target.kurtosis()
                    elif method_name == "count":
                        return target.count()
                    elif method_name in ("nunique", "n_unique"):
                        return target.n_unique()
                    elif method_name == "quantile":
                        kw_args = {}
                        for kw in n.keywords:
                            try:
                                kw_args[kw.arg] = eval_lit_value(kw.value)
                            except ValueError:
                                kw_args[kw.arg] = compile_sub(kw.value)

                        if not compiled_args and not kw_args:
                            return target.quantile(0.5)

                        return target.quantile(*compiled_args, **kw_args)
                    elif method_name == "mode":
                        return target.mode().first()
                    elif method_name in ("prod", "product"):
                        return target.product()
                    elif method_name == "sem":
                        return target.std() / target.count().sqrt()
                    elif method_name == "cov":
                        if len(compiled_args) != 1:
                            raise ValueError("cov requires exactly 1 argument")
                        return pl.cov(target, compiled_args[0])
                    elif method_name == "corr":
                        if len(compiled_args) != 1:
                            raise ValueError("corr requires exactly 1 argument")
                        return pl.corr(target, compiled_args[0])
                    elif method_name == "autocorr":
                        return pl.corr(target, target.shift(1))
                    elif method_name == "all":
                        return target.all()
                    elif method_name == "any":
                        return target.any()
                    elif method_name in ("isin", "is_in"):
                        if len(compiled_args) != 1:
                            raise ValueError("isin/is_in requires exactly 1 argument")
                        return target.is_in(compiled_args[0])
                    elif method_name == "isna":
                        return target.is_null()
                    elif method_name == "notna":
                        return target.is_not_null()

                    raise ValueError(f"Unsupported method call: {method_name}")
                raise ValueError("Unsupported function call structure")

            elif isinstance(n, ast.Attribute):
                target = require_expr(compile_sub(n.value), "Attribute target")
                if n.attr == "size":
                    return target.len()
                elif n.attr == "isna":
                    return target.is_null()
                elif n.attr == "notna":
                    return target.is_not_null()
                raise ValueError(f"Unsupported attribute: {n.attr}")

            elif isinstance(n, (ast.List, ast.Tuple)):
                try:
                    return eval_lit_value(n)
                except ValueError:
                    return [compile_sub(el) for el in n.elts]

            raise ValueError(f"Unsupported AST node type: {type(n).__name__}")

        compiled = compile_sub(node)
        if not isinstance(compiled, pl.Expr):
            raise TypeError("Expression must compile to a Polars Expression object.")
        return compiled

    def duplicate(
        self, uid: MetricID | None = None, name: str | None = None
    ) -> "Metric":
        new_metric = Metric(
            **({"uid": uid} if uid is not None else {}),
            name=self.name if name is None else name,
            query=self.query,
            data_source_ids=list(self.data_source_ids),
            is_cumulative=self.is_cumulative,
            use_thousand_sep=self.use_thousand_sep,
            is_percentage=self.is_percentage,
            decimal_places=self.decimal_places,
        )
        new_metric._used_columns = list(self.used_columns)
        new_metric._processed_query = self.processed_query
        new_metric._placeholder_map = dict(self.placeholder_map)
        new_metric._metric_expr = self.metric_expr

        return new_metric

    def to_dict(self):
        return MetricJSON(
            uid=self.uid,
            name=self.name,
            query=self.query,
            data_source_ids=self.data_source_ids,
            used_columns=self.used_columns,
            is_cumulative=self.is_cumulative,
            use_thousand_sep=self.use_thousand_sep,
            is_percentage=self.is_percentage,
            decimal_places=self.decimal_places,
            processed_query=self.processed_query,
            placeholder_map=self.placeholder_map,
        )

    @classmethod
    def from_dict(cls, data: MetricJSON) -> "Metric":
        metric = cls(
            uid=data.uid,
            name=data.name,
            query=data.query,
            is_cumulative=data.is_cumulative,
            use_thousand_sep=data.use_thousand_sep,
            is_percentage=data.is_percentage,
            decimal_places=data.decimal_places,
            data_source_ids=data.data_source_ids,
        )

        metric._used_columns = list(data.used_columns)
        metric._processed_query = data.processed_query
        metric._placeholder_map = dict(data.placeholder_map)

        return metric


class UnitBadRate(Metric):
    """Unit bad rate metric computed from a unit bad column and current MOB.
    
    If var_unt_bad is None, the metric uses "__MISSING__" as a placeholder
    for user-provided data (default unit bad rate).
    """

    def __init__(
        self,
        var_unt_bad: str | None,
        current_rate_mob: int,
        data_source_ids: list[DataSourceID],
        uid: MetricID,
        name: str,
    ):
        """Initialize the unit bad rate metric.

        Args:
            var_unt_bad: Column name containing the unit bad indicator. 
                If None, uses "__MISSING__" as a placeholder for user-provided data.
            current_rate_mob: Current month-on-book value for annualization.
            data_source_ids: Data sources used to evaluate the metric.
            uid: Unique identifier for the metric.
            name: Human-readable metric name.
        """
        is_default = var_unt_bad is None
        query = "__MISSING__" if is_default else f"(`{var_unt_bad}`.sum() / `{var_unt_bad}`.size) * (12 / {current_rate_mob})"
        super().__init__(
            uid=uid,
            name=name,
            query=query,
            is_cumulative=False,
            use_thousand_sep=False,
            is_percentage=True,
            decimal_places=2,
            data_source_ids=data_source_ids,
        )
        self._var_unt_bad = var_unt_bad
        self.validate_query()

    @property
    def is_default(self) -> bool:
        """Return True if this is a default unit bad rate metric (no column specified)."""
        return self._var_unt_bad is None


class DollarBadRate(Metric):
    """Dollar bad rate metric computed from dollar bad and average balance columns.
    
    If var_dlr_bad or var_avg_bal is None, the metric uses "__MISSING__" as a placeholder
    for user-provided data (default dollar bad rate).
    """

    def __init__(
        self,
        var_dlr_bad: str | None,
        var_avg_bal: str | None,
        current_rate_mob: int,
        data_source_ids: list[DataSourceID],
        uid: MetricID,
        name: str,
    ):
        """Initialize the dollar bad rate metric.

        Args:
            var_dlr_bad: Column name containing the dollar bad indicator.
                If None, uses "__MISSING__" as a placeholder for user-provided data.
            var_avg_bal: Column name containing the average balance column.
                If None, uses "__MISSING__" as a placeholder for user-provided data.
            current_rate_mob: Current month-on-book value for annualization.
            data_source_ids: Data sources used to evaluate the metric.
            uid: Unique identifier for the metric.
            name: Human-readable metric name.
        """
        is_default = var_dlr_bad is None or var_avg_bal is None
        query = "__MISSING__" if is_default else f"(`{var_dlr_bad}`.sum() / `{var_avg_bal}`.sum()) * (12 / {current_rate_mob})"
        super().__init__(
            uid=uid,
            name=name,
            query=query,
            is_cumulative=False,
            use_thousand_sep=False,
            is_percentage=True,
            decimal_places=2,
            data_source_ids=data_source_ids,
        )
        self._var_dlr_bad = var_dlr_bad
        self._var_avg_bal = var_avg_bal
        self.validate_query()

    @property
    def is_default(self) -> bool:
        """Return True if this is a default dollar bad rate metric (no column specified)."""
        return self._var_dlr_bad is None or self._var_avg_bal is None


class Volume(Metric):
    """Volume metric computed as the row count (size) of a column.
    
    If column_name is None, the metric uses "__MISSING__" as a placeholder
    for user-provided data (default volume).
    """

    def __init__(
        self,
        column_name: str | None,
        data_source_ids: list[DataSourceID],
        uid: MetricID,
        name: str,
    ):
        """Initialize the volume metric.

        Args:
            column_name: Column used to count rows. If None, uses "__MISSING__"
                as a placeholder for user-provided data (default volume).
            data_source_ids: Data sources used to evaluate the metric.
            uid: Unique identifier for the metric.
            name: Human-readable metric name.
        """
        is_default = column_name is None
        query = "__MISSING__" if is_default else f"`{column_name}`.size"
        super().__init__(
            uid=uid,
            name=name,
            query=query,
            is_cumulative=False,
            use_thousand_sep=True,
            is_percentage=False,
            decimal_places=0,
            data_source_ids=data_source_ids,
        )
        self._column_name = column_name
        self.validate_query()

    @property
    def is_default(self) -> bool:
        """Return True if this is a default volume metric (no column specified)."""
        return self._column_name is None


__all__ = [
    "DollarBadRate",
    "Metric",
    "MetricQueryValidator",
    "UnitBadRate",
    "Volume",
]
