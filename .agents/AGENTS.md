# Project Rules

## Filter Query DSL Design
- The filter query expression compiler lives in `risc_tool/data/models/filter.py`.
- String methods use flat single-dot syntax: `col.contains('x')`, `col.startswith('x')`, `col.endswith('x')`.
- The `.str` namespace accessor (e.g., `col.str.contains('x')`) is explicitly disallowed and must raise an error.
- Math functions use function-call syntax: `sin(col) > 0`, `log(col) > 1`, `abs(col) > 5`.
- The user-facing reference document is at `risc_tool/assets/filter_query_reference.md` and must be kept in sync with the compiler implementation.
- Tests for the filter compiler are in `tests/test_filters.py`.

## Polars Gotchas
- In Polars, `NaN > 0.0` evaluates to `True` (NaN is ordered higher than all finite values). When writing tests for math functions that produce NaN on invalid domain inputs (e.g., `log(-1)`, `sqrt(-1)`), use inputs within the valid domain to avoid false positives in filter results.
- Use `how="full"` instead of deprecated `how="outer"` in `LazyFrame.join(...)`.
- Use `how="horizontal_extend"` instead of deprecated `how="horizontal"` in `pl.concat(...)` when heights may differ.

## AST Expression Compiler Guidelines
- Evaluate literal AST nodes (constants, keyword strings, lists of literals) as native Python primitives (`eval_lit_value`) when passing arguments to Polars methods expecting strings or raw collections (e.g., `interpolation='nearest'`, `is_in([1, 2])`).

## Architecture & Routing Invariants
- Package entrypoints under `risc_tool/ui/<feature>/__init__.py` must remain empty. Define page routes and `st.Page` instances inside `risc_tool/ui/<feature>/<feature>.py` to avoid circular imports during session/view model initialization.
- Test files under `tests/` must be organized into structured subpackages (`tests/data/models/`, `tests/data/services/`, `tests/ui/<feature>/`) mirroring the `risc_tool` codebase structure.
