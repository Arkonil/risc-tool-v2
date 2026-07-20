import ast
import re
import typing as t

import polars as pl

from risc_tool.data.models.exceptions import InvalidFilterError
from risc_tool.data.models.types import FilterID
from risc_tool.utils.logging import get_logger

ScalarValue = str | int | float | bool | None
CompiledValue = pl.Expr | list[ScalarValue]


class FilterQueryValidator(ast.NodeVisitor):
    """AST visitor to extract variable/column identifiers from a query.

    Attributes:
        found_columns: Set of discovered column names from the AST.
        placeholder_map: Mapping from placeholder names to original
            backticked column names.
    """

    def __init__(self, placeholder_map: dict[str, str]):
        """Initialize the validator with a placeholder map for backticked names.

        Args:
            placeholder_map: A dictionary mapping placeholder identifiers
                (e.g., __BACKTICKED_0__) to their original column names.
        """
        self.found_columns: set[str] = set()
        self.placeholder_map = placeholder_map

    def _resolve_and_add_name(self, identifier: str):
        """Resolve a name node to its original column name and add to found_columns.

        Skips identifiers starting with '@' (variables) and unmapped
        backtick placeholders.

        Args:
            identifier: The AST identifier string to resolve.
        """
        if identifier.startswith("@"):
            return  # Exclude @-variables

        original_name = self.placeholder_map.get(identifier, identifier)
        if (
            identifier.startswith("__BACKTICKED_")
            and identifier not in self.placeholder_map
        ):
            return  # Ignore unmapped placeholders

        self.found_columns.add(original_name)

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
        """Visit a Call AST node and visit its function arguments.

        Skips the function itself if it is a simple Name (treated elsewhere).
        Visits all positional arguments and keyword argument values.

        Args:
            node: The AST Call node being visited.
        """
        if not isinstance(node.func, ast.Name):
            self.visit(node.func)

        for arg in node.args:
            self.visit(arg)
        for kwarg in node.keywords:
            self.visit(kwarg.value)


class Filter:
    """Represents a filter condition in the application, calculated using Polars.

    Stores the raw query string, validates and compiles it into a Polars
    expression, and tracks which columns the filter depends on.

    Attributes:
        uid: Unique identifier for this filter.
        name: Human-readable name for display.
        query: The raw filter expression string.
        used_columns: List of column names that appear in the query.
        filter_expr: Compiled Polars expression, or None if not yet validated.
    """

    def __init__(self, uid: FilterID, name: str, query: str) -> None:
        """Initialize a new Filter.

        Args:
            uid: Unique identifier for the filter.
            name: Human-readable name.
            query: The filter expression string in Python-like syntax.
        """
        self.logger = get_logger(self.__class__.__name__)
        self.uid: FilterID = uid
        self.name: str = name
        self.query: str = query
        self.used_columns: list[str] = []
        self.filter_expr: pl.Expr | None = None

    @property
    def pretty_name(self) -> str:
        """Return the display name of the filter.

        Returns:
            The filter name string.
        """
        return self.name

    def validate_query(self, available_columns: list[str] | None = None) -> None:
        """Parse, validate structure, and extract used columns from the query."""
        self.logger.info("Validating filter query: '%s'", self.query)
        if not self.query.strip():
            self.logger.warning("Filter query is empty")
            raise InvalidFilterError(self.query, "Query cannot be empty.")

        # --- 1. Preprocess Backticked Identifiers ---
        backticked_map: dict[str, str] = {}

        def replace_backtick(match: re.Match[str]) -> str:
            name_inside_ticks = match.group(1)
            placeholder = f"__BACKTICKED_{len(backticked_map)}__"
            backticked_map[placeholder] = name_inside_ticks
            return placeholder

        processed_expression = re.sub(r"`([^`]+)`", replace_backtick, self.query)

        # --- 2. Parse and Validate Structure ---
        try:
            tree = ast.parse(processed_expression, mode="exec")
        except SyntaxError as e:
            self.logger.warning("Syntax error in query '%s': %s", self.query, e)
            raise InvalidFilterError(self.query, f"Syntax error in expression: {e}")

        if not tree.body or len(tree.body) > 1:
            self.logger.warning(
                "Query expression has %d body elements, expected 1",
                len(tree.body) if tree.body else 0,
            )
            raise InvalidFilterError(
                self.query,
                "Query expression must contain exactly one single expression.",
            )

        statement = tree.body[0]

        if isinstance(statement, (ast.Assign, ast.AugAssign, ast.AnnAssign)):
            self.logger.warning(
                "Assignment statement detected in query '%s'", self.query
            )
            raise InvalidFilterError(
                self.query,
                "Assignments ('=') are not allowed. Use '==' for comparison.",
            )

        if not isinstance(statement, ast.Expr):
            self.logger.warning(
                "Non-expression statement in query '%s': %s",
                self.query,
                type(statement).__name__,
            )
            raise InvalidFilterError(
                self.query,
                f"Query expression cannot contain statements of type '{type(statement).__name__}'. Only expressions are allowed.",
            )

        expr_node = statement.value

        # --- 3. Check for Boolean Nature ---
        allowed_top_level_nodes = (
            ast.Compare,  # a > b, a == b
            ast.BoolOp,  # a and b, a or b
            ast.Constant,  # True / False
            ast.Name,  # bool_col
            ast.Attribute,  # df.bool_col
            ast.Call,  # col.str.contains('x')
            ast.Subscript,  # col[index]
            ast.UnaryOp,  # ~a, not a
        )

        is_likely_boolean = False
        if isinstance(expr_node, allowed_top_level_nodes):
            is_likely_boolean = True
        elif isinstance(expr_node, ast.BinOp) and isinstance(
            expr_node.op, (ast.BitAnd, ast.BitOr, ast.BitXor)
        ):
            is_likely_boolean = True

        if not is_likely_boolean:
            node_type_name = type(expr_node).__name__
            reason = f"the top-level operation is '{node_type_name}', which typically does not produce a boolean result."
            if isinstance(expr_node, ast.BinOp):
                op_type_name = type(expr_node.op).__name__
                reason = f"the top-level arithmetic operator is '{op_type_name}'."
            self.logger.warning(
                "Non-boolean expression in query '%s': %s", self.query, reason
            )
            raise InvalidFilterError(
                self.query, f"Expression does not appear to be boolean; {reason}"
            )

        # --- 4. Extract Columns ---
        finder = FilterQueryValidator(backticked_map)
        finder.visit(expr_node)
        self.used_columns = sorted(list(finder.found_columns))

        # --- 5. Validate Columns Exist ---
        if available_columns is not None:
            available_set = set(available_columns)
            used_set = set(self.used_columns)
            missing_columns = sorted(list(used_set - available_set))
            if missing_columns:
                self.logger.warning("Missing columns in query: %s", missing_columns)
                raise InvalidFilterError(
                    self.query,
                    f"Following columns are not found in the data: {', '.join(missing_columns)}",
                )

        # --- 6. Compile Expression ---
        try:
            self.filter_expr = self._compile_expression(expr_node, backticked_map)
        except Exception as e:
            self.logger.exception("Failed to compile filter query '%s'", self.query)
            raise InvalidFilterError(
                self.query, f"Failed to compile to Polars expression: {e}"
            )

        self.logger.debug(
            "Query validated and compiled successfully. Columns used: %s",
            self.used_columns,
        )

    def _compile_expression(
        self, node: ast.AST, backticked_map: dict[str, str]
    ) -> pl.Expr:
        """Recursively compile an AST node into a Polars expression.

        Supports binary/unary operators, comparisons (including chained),
        boolean logic, function calls, method calls, attribute access,
        list/tuple literals, and backticked column identifiers.

        Args:
            node: The AST node to compile.
            backticked_map: Mapping from placeholder names to original
                backticked column names.

        Returns:
            A compiled Polars expression.

        Raises:
            ValueError: If the AST node type or operator is unsupported.
        """

        def require_expr(value: CompiledValue, context: str) -> pl.Expr:
            if isinstance(value, pl.Expr):
                return value
            self.logger.warning(
                "%s expects an expression operand, got %s",
                context,
                type(value).__name__,
            )
            raise ValueError(f"{context} expects an expression operand")

        def require_is_in_rhs(
            value: CompiledValue,
        ) -> pl.Expr | t.Collection[t.Any]:
            if isinstance(value, pl.Expr):
                return value
            return value

        def compile_sub(
            n: ast.AST,
        ) -> CompiledValue:
            if isinstance(n, ast.Name):
                name = backticked_map.get(n.id, n.id)
                if name == "True":
                    return pl.lit(True)
                elif name == "False":
                    return pl.lit(False)
                elif name == "None":
                    return pl.lit(None)
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
                self.logger.warning(
                    "Unsupported unary operator: %s", type(n.op).__name__
                )
                raise ValueError(f"Unsupported unary operator: {type(n.op).__name__}")

            elif isinstance(n, ast.BinOp):
                left = require_expr(
                    compile_sub(n.left), "Binary operator left-hand side"
                )
                right = require_expr(
                    compile_sub(n.right), "Binary operator right-hand side"
                )
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
                self.logger.warning(
                    "Unsupported binary operator: %s", type(op).__name__
                )
                raise ValueError(f"Unsupported binary operator: {type(op).__name__}")

            elif isinstance(n, ast.BoolOp):
                values = [
                    require_expr(compile_sub(v), "Boolean operator") for v in n.values
                ]
                if isinstance(n.op, ast.And):
                    res = values[0]
                    for v in values[1:]:
                        res = res & v
                    return res
                elif isinstance(n.op, ast.Or):
                    res = values[0]
                    for v in values[1:]:
                        res = res | v
                    return res
                self.logger.warning(
                    "Unsupported boolean operator: %s", type(n.op).__name__
                )
                raise ValueError(f"Unsupported boolean operator: {type(n.op).__name__}")

            elif isinstance(n, ast.Compare):
                left_compiled = require_expr(
                    compile_sub(n.left), "Comparison left-hand side"
                )
                exprs: list[pl.Expr] = []
                curr_left_compiled = left_compiled

                for idx, (op, comparator) in enumerate(zip(n.ops, n.comparators)):
                    right_compiled = compile_sub(comparator)
                    is_list_or_tuple = isinstance(comparator, (ast.List, ast.Tuple))

                    if isinstance(op, ast.Eq):
                        if is_list_or_tuple:
                            term = curr_left_compiled.is_in(
                                require_is_in_rhs(right_compiled)
                            )
                        else:
                            term = curr_left_compiled == require_expr(
                                right_compiled, "Equality comparison right-hand side"
                            )
                    elif isinstance(op, ast.NotEq):
                        if is_list_or_tuple:
                            term = ~curr_left_compiled.is_in(
                                require_is_in_rhs(right_compiled)
                            )
                        else:
                            term = curr_left_compiled != require_expr(
                                right_compiled,
                                "Inequality comparison right-hand side",
                            )
                    elif isinstance(op, ast.Lt):
                        term = curr_left_compiled < require_expr(
                            right_compiled, "Less-than comparison right-hand side"
                        )
                    elif isinstance(op, ast.LtE):
                        term = curr_left_compiled <= require_expr(
                            right_compiled,
                            "Less-than-or-equal comparison right-hand side",
                        )
                    elif isinstance(op, ast.Gt):
                        term = curr_left_compiled > require_expr(
                            right_compiled, "Greater-than comparison right-hand side"
                        )
                    elif isinstance(op, ast.GtE):
                        term = curr_left_compiled >= require_expr(
                            right_compiled,
                            "Greater-than-or-equal comparison right-hand side",
                        )
                    elif isinstance(op, ast.In):
                        term = curr_left_compiled.is_in(
                            require_is_in_rhs(right_compiled)
                        )
                    elif isinstance(op, ast.NotIn):
                        term = ~curr_left_compiled.is_in(
                            require_is_in_rhs(right_compiled)
                        )
                    else:
                        self.logger.warning(
                            "Unsupported comparison operator: %s", type(op).__name__
                        )
                        raise ValueError(
                            f"Unsupported comparison operator: {type(op).__name__}"
                        )

                    exprs.append(term)
                    if idx < len(n.ops) - 1:
                        curr_left_compiled = require_expr(
                            right_compiled,
                            "Chained comparison operand",
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
                    if fn_name == "arctan2":
                        if len(n.args) != 2:
                            self.logger.warning(
                                "arctan2 requires exactly 2 arguments, got %d",
                                len(n.args),
                            )
                            raise ValueError("arctan2 requires exactly 2 arguments")
                        y_arg = require_expr(
                            compile_sub(n.args[0]), "arctan2 y-argument"
                        )
                        x_arg = require_expr(
                            compile_sub(n.args[1]), "arctan2 x-argument"
                        )
                        return pl.arctan2(y_arg, x_arg)
                    elif fn_name == "expm1":
                        if len(n.args) != 1:
                            self.logger.warning(
                                "expm1 requires exactly 1 argument, got %d", len(n.args)
                            )
                            raise ValueError("expm1 requires exactly 1 argument")
                        arg = require_expr(compile_sub(n.args[0]), "expm1 argument")
                        return arg.exp() - 1
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
                        if len(n.args) != 1:
                            self.logger.warning(
                                "%s requires exactly 1 argument, got %d",
                                fn_name,
                                len(n.args),
                            )
                            raise ValueError(f"{fn_name} requires exactly 1 argument")
                        arg = require_expr(
                            compile_sub(n.args[0]), f"{fn_name} argument"
                        )
                        return getattr(arg, fn_name)()
                    self.logger.warning("Unsupported function call: %s", fn_name)
                    raise ValueError(f"Unsupported function call: {fn_name}")

                elif isinstance(n.func, ast.Attribute):
                    target = compile_sub(n.func.value)
                    method_name = n.func.attr
                    compiled_args = [compile_sub(arg) for arg in n.args]

                    if method_name == "isna":
                        return require_expr(target, "isna target").is_null()
                    elif method_name == "notna":
                        return require_expr(target, "notna target").is_not_null()
                    elif method_name == "contains":
                        if len(compiled_args) != 1:
                            self.logger.warning(
                                "contains requires exactly 1 argument, got %d",
                                len(compiled_args),
                            )
                            raise ValueError("contains requires exactly 1 argument")
                        pattern = require_expr(compiled_args[0], "contains pattern")
                        return require_expr(target, "contains target").str.contains(
                            pattern
                        )
                    elif method_name in ("startswith", "starts_with"):
                        if len(compiled_args) != 1:
                            self.logger.warning(
                                "startswith requires exactly 1 argument, got %d",
                                len(compiled_args),
                            )
                            raise ValueError("startswith requires exactly 1 argument")
                        prefix = require_expr(compiled_args[0], "startswith prefix")
                        return require_expr(
                            target, "startswith target"
                        ).str.starts_with(prefix)
                    elif method_name in ("endswith", "ends_with"):
                        if len(compiled_args) != 1:
                            self.logger.warning(
                                "endswith requires exactly 1 argument, got %d",
                                len(compiled_args),
                            )
                            raise ValueError("endswith requires exactly 1 argument")
                        suffix = require_expr(compiled_args[0], "endswith suffix")
                        return require_expr(target, "endswith target").str.ends_with(
                            suffix
                        )
                    elif hasattr(target, method_name):
                        return getattr(target, method_name)(*compiled_args)
                    self.logger.warning("Unsupported method call: %s", method_name)
                    raise ValueError(f"Unsupported method call: {method_name}")
                self.logger.warning("Unsupported function call structure")
                raise ValueError("Unsupported function call structure")

            elif isinstance(n, ast.Attribute):
                if n.attr == "isna":
                    obj = require_expr(compile_sub(n.value), "Attribute target")
                    return obj.is_null()
                elif n.attr == "notna":
                    obj = require_expr(compile_sub(n.value), "Attribute target")
                    return obj.is_not_null()
                self.logger.warning("Unsupported attribute access: %s", n.attr)
                raise ValueError(f"Unsupported attribute access: {n.attr}")

            elif isinstance(n, (ast.List, ast.Tuple)):
                vals: list[ScalarValue] = []
                for el in n.elts:
                    if isinstance(el, ast.Constant):
                        vals.append(t.cast(ScalarValue, el.value))
                    elif isinstance(el, ast.Name):
                        name = backticked_map.get(el.id, el.id)
                        if name == "True":
                            vals.append(True)
                        elif name == "False":
                            vals.append(False)
                        elif name == "None":
                            vals.append(None)
                        else:
                            vals.append(name)
                    else:
                        value = compile_sub(el)
                        self.logger.warning(
                            "List/Tuple literal contains non-scalar value: %s",
                            type(value).__name__,
                        )
                        raise ValueError(
                            f"List/Tuple literals only support scalar values, got {type(value).__name__}"
                        )
                return vals

            self.logger.warning("Unsupported syntax node type: %s", type(n).__name__)
            raise ValueError(f"Unsupported syntax node: {type(n).__name__}")

        compiled = compile_sub(node)

        if not isinstance(compiled, pl.Expr):
            self.logger.warning(
                "Expression compiled to %s, not a Polars Expression",
                type(compiled).__name__,
            )
            raise ValueError("Expression must compile to a Polars Expression object.")

        return compiled

    def duplicate(
        self, uid: FilterID | None = None, name: str | None = None
    ) -> "Filter":
        """Create a duplicate of this filter."""
        if uid is None:
            uid = self.uid
        if name is None:
            name = self.name

        self.logger.debug("Duplicating filter '%s' as '%s'", self.name, name)
        new_instance = Filter(uid=uid, name=name, query=self.query)
        new_instance.used_columns = list(self.used_columns)
        new_instance.filter_expr = self.filter_expr
        return new_instance

    def to_dict(self) -> dict[str, t.Any]:
        """Convert the filter instance to a dictionary for compatibility."""
        return {
            "uid": int(self.uid),
            "name": self.name,
            "query": self.query,
            "used_columns": self.used_columns,
            "is_outlier": False,
        }


__all__ = ["Filter"]
