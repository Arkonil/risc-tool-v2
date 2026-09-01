"""Metric model with query validation and Polars expression compilation.

This module defines the Metric class, which stores a raw metric query,
validates its syntax, structure, and column references, and compiles it
into a Polars expression. Metric is a frozen, content-addressed pydantic
model: its uid is derived as a UUIDv5 hash of its content fields (name,
query, data source IDs, and display settings), so two metrics with
identical content share an identity.

Concrete metric subclasses for common volume and bad-rate metrics are
retained; they derive their query strings from their parameters and share
the base compilation pipeline.
"""

import ast
import json
import logging
import re
import typing as t
from uuid import NAMESPACE_URL, uuid5

import numpy as np
import polars as pl
from pydantic import BaseModel, ConfigDict, PrivateAttr, model_validator

from risc_tool.data.models.json_models import MetricJSON
from risc_tool.data.models.uid import DataSourceID, MetricID
from risc_tool.utils.logging import get_logger

MISSING = None
Scalar = int | float | str | bool | None


def _content_str(
    name: str,
    query: str,
    data_source_ids: t.Sequence[DataSourceID],
    is_cumulative: bool,
    use_thousand_sep: bool,
    is_percentage: bool,
    decimal_places: int,
) -> str:
    """Build a canonical string from a metric's content for hashing.

    Data source IDs are sorted so list ordering does not affect identity.

    Args:
        name: The metric name.
        query: The raw metric expression string.
        data_source_ids: The data sources the metric applies to.
        is_cumulative: Whether the metric is cumulative.
        use_thousand_sep: Whether numbers use thousands separators.
        is_percentage: Whether the value displays as a percentage.
        decimal_places: Number of decimal places for formatted output.

    Returns:
        A deterministic string that uniquely represents the content.
    """
    payload = json.dumps(
        {
            "name": name,
            "query": query,
            "data_source_ids": sorted(str(ds_id) for ds_id in data_source_ids),
            "is_cumulative": is_cumulative,
            "use_thousand_sep": use_thousand_sep,
            "is_percentage": is_percentage,
            "decimal_places": decimal_places,
        },
        sort_keys=True,
    )
    return payload


def _uid_from_content(
    name: str,
    query: str,
    data_source_ids: t.Sequence[DataSourceID],
    is_cumulative: bool,
    use_thousand_sep: bool,
    is_percentage: bool,
    decimal_places: int,
) -> MetricID:
    """Derive a content-addressed MetricID from a metric's content.

    Args:
        name: The metric name.
        query: The raw metric expression string.
        data_source_ids: The data sources the metric applies to.
        is_cumulative: Whether the metric is cumulative.
        use_thousand_sep: Whether numbers use thousands separators.
        is_percentage: Whether the value displays as a percentage.
        decimal_places: Number of decimal places for formatted output.

    Returns:
        A MetricID whose value is a UUIDv5 hash of the content.
    """
    return MetricID(
        uuid5(
            NAMESPACE_URL,
            _content_str(
                name,
                query,
                data_source_ids,
                is_cumulative,
                use_thousand_sep,
                is_percentage,
                decimal_places,
            ),
        )
    )


class MetricQueryValidator(ast.NodeVisitor):
    """AST visitor to validate metric expressions and find columns.

    Attributes:
        allowed_functions: Set of allowed top-level function names.
        allowed_series_methods: Set of allowed series (column) method names.
        allowed_operators: Tuple of allowed AST binary operator types.
        allowed_names: Set of special allowed name identifiers.
        allowed_series_attributes: Set of allowed attribute names on series.
        found_columns: Set of discovered column names from the AST.
        placeholder_map: Mapping from placeholder names to original
            backticked column names.
    """

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
        """Initialize the validator with a placeholder map for backticked names.

        Args:
            placeholder_map: A dictionary mapping placeholder identifiers
                (e.g., __BACKTICKED_0__) to their original column names.
        """
        self.found_columns: set[str] = set()
        self.placeholder_map = placeholder_map

    def _resolve_and_add_name(self, identifier: str):
        """Resolve an identifier to its original column name and add to found_columns.

        Skips @-variables, allowed special names, and unmapped backtick
        placeholders.

        Args:
            identifier: The AST identifier string to resolve.
        """
        if identifier.startswith("@"):
            return  # Exclude @-variables

        if identifier in self.allowed_names:
            return

        original_name = self.placeholder_map.get(identifier, identifier)
        if (
            identifier.startswith("__BACKTICKED_")
            and identifier not in self.placeholder_map
        ):
            return  # Ignore unmapped placeholders

        self.found_columns.add(original_name)
        self.placeholder_map[identifier] = original_name

    def visit_Name(self, node: ast.Name):
        """Visit a Name AST node and add its resolved identifier to found_columns.

        Args:
            node: The AST Name node being visited.
        """
        self._resolve_and_add_name(node.id)

    def visit_Attribute(self, node: ast.Attribute):
        """Visit an Attribute AST node and extract the root object name.

        Walks through chained attribute accesses (e.g., df.col.x) to find
        the root Name node and resolves it.

        Args:
            node: The AST Attribute node being visited.
        """
        current_obj = node
        while isinstance(current_obj, ast.Attribute):
            current_obj = current_obj.value

        if isinstance(current_obj, ast.Name):
            self._resolve_and_add_name(current_obj.id)
        else:
            self.visit(current_obj)

    def visit_Call(self, node: ast.Call):
        """Visit a Call AST node, validating function names and visiting arguments.

        Allows only known aggregation and math functions. All positional
        arguments and keyword argument values are visited recursively.

        Args:
            node: The AST Call node being visited.

        Raises:
            ValueError: If a called function is not in the allowed set.
        """
        if isinstance(node.func, ast.Name):
            if node.func.id not in self.allowed_functions:
                # Allow standard mathematical functions from filters
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
        """Visit a BinOp AST node, rejecting disallowed binary operators.

        Args:
            node: The AST BinOp node being visited.

        Raises:
            TypeError: If the operator type is not in the allowed set.
        """
        if not isinstance(node.op, self.allowed_operators):
            raise TypeError(f"Unsupported binary operator: {type(node.op).__name__}")

        self.visit(node.left)
        self.visit(node.right)

    def is_result_scalar(self, expr_node: ast.AST) -> bool:
        """Determine whether an expression evaluates to a scalar value.

        Args:
            expr_node: The AST node to inspect.

        Returns:
            True if the expression is scalar (names, constants, arithmetic
            on scalars, or scalar-producing calls), False otherwise.
        """
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
    """Represents a metric query, parsed and compiled to a Polars expression.

    The model is frozen: compiled state lives in private attributes that are
    refreshed by :meth:`validate_query`.

    Attributes:
        uid: Content-addressed unique identifier for the metric.
        name: Human-readable metric name.
        query: The raw metric expression string.
        data_source_ids: Data sources used to evaluate the metric.
        is_cumulative: Whether the metric is cumulative over time.
        use_thousand_sep: Whether numbers use thousands separators.
        is_percentage: Whether the value is displayed as a percentage.
        decimal_places: Number of decimal places for formatted output.
        used_columns: Column names referenced by the query.
        processed_query: Query with placeholders resolved.
        placeholder_map: Mapping from placeholders to original expressions.
        metric_expr: Compiled Polars expression, or None if not yet validated.
        _logger: Private logger instance for this metric.
    """

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
        """Derive the content-addressed uid when it is left unset.

        An explicitly provided uid is preserved, which allows the
        EMPTY/TEMPORARY sentinels and deserialized identities to survive
        construction. Passing UNSET explicitly behaves like omission. Also
        seeds the processed-query cache used before validation.

        Returns:
            This instance with the uid derived if none was set.
        """
        if not self._processed_query:
            object.__setattr__(self, "_processed_query", self.query)

        if self.uid is MetricID.UNSET:
            # Frozen model: bypass immutability to fill in the derived uid.
            object.__setattr__(self, "uid", self.create_hash())
        return self

    def create_hash(self) -> MetricID:
        """Return a content-addressed MetricID derived from this content.

        The ID hashes all content fields except the uid itself, so identical
        content always produces the same identity. Data source IDs are
        sorted before hashing so list ordering does not affect identity.

        Returns:
            A MetricID whose value is a UUIDv5 hash of the content.
        """
        return _uid_from_content(
            self.name,
            self.query,
            self.data_source_ids,
            self.is_cumulative,
            self.use_thousand_sep,
            self.is_percentage,
            self.decimal_places,
        )

    def with_updates(self, **updates: t.Any) -> "Metric":
        """Return a copy of this metric with updated fields.

        Identity handling: an explicit ``uid`` update pins the copy's ID;
        otherwise a change to any content field re-derives the ID from the
        new content, and an unchanged content keeps this metric's ID (so
        EMPTY/TEMPORARY drafts stay stable across non-content edits).
        Compiled state is carried over whenever the query is unchanged.

        Args:
            **updates: Field values to override on the copy.

        Returns:
            A new Metric instance with the updates applied.
        """
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
            uid = None  # Re-derive from the new content.
        else:
            # Unchanged content or an unsaved sentinel draft keeps its ID.
            uid = self.uid

        new_metric = Metric(**({"uid": uid} if uid is not None else {}), **fields)

        # Compiled state depends only on the query; carry it when unchanged.
        if new_metric.query == self.query:
            new_metric._used_columns = list(self.used_columns)
            new_metric._processed_query = self.processed_query
            new_metric._placeholder_map = dict(self.placeholder_map)
            new_metric._metric_expr = self.metric_expr

        return new_metric

    @property
    def pretty_name(self) -> str:
        """Return the display name of the metric.

        Returns:
            The metric name string.
        """
        return self.name

    def format(self, value: float | None) -> str | float | None:
        """Format a metric value according to the configured display settings.

        Args:
            value: The raw numeric value to format, or None.

        Returns:
            The formatted string (with thousand separators and percentage
            symbol as configured), or None if the value is missing/NaN.
        """
        if value is None or (isinstance(value, float) and np.isnan(value)):
            return value

        formatter = f"{{:{',' if self.use_thousand_sep else ''}.{self.decimal_places}f}}{'%' if self.is_percentage else ''}"
        return formatter.format(value)

    @property
    def used_columns(self) -> list[str]:
        """Get the column names referenced by the query.

        Returns:
            A list of column names extracted by the last validation.
        """
        return self._used_columns

    @property
    def processed_query(self) -> str:
        """Get the query with placeholders resolved to actual expressions."""
        return self._processed_query

    @property
    def placeholder_map(self) -> dict[str, str]:
        """Get the mapping from placeholders to original expressions."""
        return self._placeholder_map

    @property
    def metric_expr(self) -> pl.Expr | None:
        """Get the compiled Polars expression.

        Returns:
            The compiled expression, or None if not yet validated.
        """
        return self._metric_expr

    def validate_query(self, available_columns: list[str] | None = None) -> None:
        """Parse, validate structure, extract used columns, and compile the query.

        Args:
            available_columns: Optional list of columns that may be referenced.
                If provided, missing columns raise a ValueError.

        Raises:
            ValueError: If the query is empty, has invalid syntax, is not a
                scalar expression, references missing columns, or fails to
                compile to a Polars expression.
        """
        self._logger.info(
            "Validating metric query '%s' for metric '%s'", self.query, self.name
        )

        if not self.query.strip():
            raise ValueError("Query cannot be empty.")

        # --- 1. Preprocess Backticked Identifiers ---
        backticked_map: dict[str, str] = {}

        def replace_backtick(match: re.Match[str]) -> str:
            """Replace a backticked identifier with a unique placeholder.

            Args:
                match: The regex match containing the backticked name.

            Returns:
                A placeholder string such as __BACKTICKED_0__.
            """
            name_inside_ticks = match.group(1)
            placeholder = f"__BACKTICKED_{len(backticked_map)}__"
            backticked_map[placeholder] = name_inside_ticks
            return placeholder

        processed_expression = re.sub(r"`([^`]+)`", replace_backtick, self.query)

        # --- 2. Parse AST ---
        try:
            expr_node = ast.parse(processed_expression, mode="eval").body
        except SyntaxError as e:
            self._logger.warning(
                "Syntax error in metric query '%s': %s", self.query, e
            )
            raise ValueError(f"Syntax error in expression: {e}")

        # --- 3. Validate Query Structure ---
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

        # --- 4. Extract Column Names and Compile ---
        self._used_columns = sorted(validator.found_columns)
        self._placeholder_map = validator.placeholder_map
        self._processed_query = processed_expression

        # Check Columns
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

        # Compile Expression
        try:
            self._metric_expr = self._compile_expression(expr_node, backticked_map)
        except (ValueError, TypeError) as e:
            self._logger.error(
                "Failed to compile metric query '%s': %s", self.query, e
            )
            raise ValueError(f"Failed to compile to Polars expression: {e}")

    def _compile_expression(
        self, node: ast.AST, backticked_map: dict[str, str]
    ) -> pl.Expr:
        """Recursively compile an AST node into a Polars expression.

        Supports binary/unary operators, comparisons (including chained),
        function calls, method calls, attribute access, and list/tuple
        literals, as well as backticked column identifiers.

        Args:
            node: The AST node to compile.
            backticked_map: Mapping from placeholder names to original
                backticked column names.

        Returns:
            A compiled Polars expression.

        Raises:
            ValueError: If the AST node type, function, method, or operator
                is unsupported.
        """

        def require_expr(value: t.Any, context: str) -> pl.Expr:
            """Ensure a compiled value is a Polars expression.

            Args:
                value: The compiled value to check.
                context: A description of where the value is used, for errors.

            Returns:
                The value itself if it is already a pl.Expr.

            Raises:
                ValueError: If the value is not a pl.Expr.
            """
            if isinstance(value, pl.Expr):
                return value
            raise ValueError(f"{context} expects an expression operand")

        def eval_lit_value(n: ast.AST) -> t.Any:
            """Evaluate an AST node to a Python literal value.

            Args:
                n: The AST node to evaluate.

            Returns:
                The literal value, or a list of literal values for list/tuple
                nodes.

            Raises:
                ValueError: If the node is not a literal.
            """
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
            """Compile an AST node recursively into a Polars expression.

            Args:
                n: The AST node to compile.

            Returns:
                A compiled Polars expression or a collection of expressions.

            Raises:
                ValueError: If the node type, function, method, or operator
                    is unsupported.
            """
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
        """Create a copy of this metric with optional new uid and name.

        Compiled state is carried over without revalidation. When uid is
        omitted the copy derives its content hash from the resulting fields,
        which equals this metric's ID unless content changed.

        Args:
            uid: Explicit unique identifier for the copy.
            name: New display name, or None to reuse the current name.

        Returns:
            A new Metric instance with copied configuration and compiled state.
        """
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
        """Convert Metric to MetricJSON Pydantic model."""
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
        """Reconstruct Metric from MetricJSON Pydantic model or dict."""

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


class DefaultUnitBadRate(Metric):
    """Default unit bad rate metric (placeholder for user-provided data)."""

    def __init__(self, data_source_ids: list[DataSourceID], uid: MetricID, name: str):
        """Initialize the default unit bad rate metric.

        Args:
            data_source_ids: Data sources used to evaluate the metric.
            uid: Unique identifier for the metric.
            name: Human-readable metric name.
        """
        super().__init__(
            uid=uid,
            name=name,
            query="__MISSING__",
            is_cumulative=False,
            use_thousand_sep=False,
            is_percentage=True,
            decimal_places=2,
            data_source_ids=data_source_ids,
        )

        self.validate_query()


class UnitBadRate(Metric):
    """Unit bad rate metric computed from a unit bad column and current MOB."""

    def __init__(
        self,
        var_unt_bad: str,
        current_rate_mob: int,
        data_source_ids: list[DataSourceID],
        uid: MetricID,
        name: str,
    ):
        """Initialize the unit bad rate metric.

        Args:
            var_unt_bad: Column name containing the unit bad indicator.
            current_rate_mob: Current month-on-book value for annualization.
            data_source_ids: Data sources used to evaluate the metric.
            uid: Unique identifier for the metric.
            name: Human-readable metric name.
        """
        super().__init__(
            uid=uid,
            name=name,
            query=f"(`{var_unt_bad}`.sum() / `{var_unt_bad}`.size) * (12 / {current_rate_mob})",
            is_cumulative=False,
            use_thousand_sep=False,
            is_percentage=True,
            decimal_places=2,
            data_source_ids=data_source_ids,
        )


class DefaultDollarBadRate(Metric):
    """Default dollar bad rate metric (placeholder for user-provided data)."""

    def __init__(self, data_source_ids: list[DataSourceID], uid: MetricID, name: str):
        """Initialize the default dollar bad rate metric.

        Args:
            data_source_ids: Data sources used to evaluate the metric.
            uid: Unique identifier for the metric.
            name: Human-readable metric name.
        """
        super().__init__(
            uid=uid,
            name=name,
            query="__MISSING__",
            is_cumulative=False,
            use_thousand_sep=False,
            is_percentage=True,
            decimal_places=2,
            data_source_ids=data_source_ids,
        )

        self.validate_query()


class DollarBadRate(Metric):
    """Dollar bad rate metric computed from dollar bad and average balance columns."""

    def __init__(
        self,
        var_dlr_bad: str,
        var_avg_bal: str,
        current_rate_mob: int,
        data_source_ids: list[DataSourceID],
        uid: MetricID,
        name: str,
    ):
        """Initialize the dollar bad rate metric.

        Args:
            var_dlr_bad: Column name containing the dollar bad indicator.
            var_avg_bal: Column name containing the average balance columns.
            current_rate_mob: Current month-on-book value for annualization.
            data_source_ids: Data sources used to evaluate the metric.
            uid: Unique identifier for the metric.
            name: Human-readable metric name.
        """
        super().__init__(
            uid=uid,
            name=name,
            query=f"(`{var_dlr_bad}`.sum() / `{var_avg_bal}`.sum()) * (12 / {current_rate_mob})",
            is_cumulative=False,
            use_thousand_sep=False,
            is_percentage=True,
            decimal_places=2,
            data_source_ids=data_source_ids,
        )


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
    "DefaultDollarBadRate",
    "DefaultUnitBadRate",
    "DollarBadRate",
    "Metric",
    "MetricQueryValidator",
    "UnitBadRate",
    "Volume",
]
