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
- In `DataRepository`, check data availability using `data_repository.has_valid_sources` (or `view_model.data_loaded`).
- `DataRepository.common_columns()` returns `set[tuple[str, VariableType]]`. To extract raw column names, use `{c[0] for c in data_repository.common_columns()}`.

## AST Expression Compiler Guidelines
- Evaluate literal AST nodes (constants, keyword strings, lists of literals) as native Python primitives (`eval_lit_value`) when passing arguments to Polars methods expecting strings or raw collections (e.g., `interpolation='nearest'`, `is_in([1, 2])`).

## Architecture & Routing Invariants
- Package entrypoints under `risc_tool/ui/<feature>/__init__.py` must remain empty. Define page routes and `st.Page` instances inside `risc_tool/ui/<feature>/<feature>.py` to avoid circular imports during session/view model initialization.
- Test files under `tests/` must be organized into structured subpackages (`tests/data/models/`, `tests/data/services/`, `tests/ui/<feature>/`) mirroring the `risc_tool` codebase structure.

## Streamlit & View Model Design Standards
- View Models (`risc_tool/ui/<feature>/<feature>_vm.py`) must encapsulate all table formatting, pandas `Styler` construction (CSS colors, cell styles), unit scaling (e.g. % vs decimal), validation, and edit processing logic.
- UI elements (`risc_tool/ui/<feature>/<feature>.py`) must remain presentation-only: they fetch preconfigured `Styler` objects from the View Model to display in `st.data_editor` and pass edited DataFrames directly to View Model handler methods without performing manual data loops or data juggling.
- When type-annotating pandas Styler objects in Python code, import `from pandas.io.formats.style import Styler` directly to prevent `AttributeError: module 'pandas.io.formats' has no attribute 'style'` at runtime.
- When type-annotating lists or variables holding Streamlit containers or column elements (e.g. from `st.container()`, `st.columns()`), import `from streamlit.delta_generator import DeltaGenerator` and annotate as `list[DeltaGenerator]`.

## Session & Serialization Standards
- Every repository and full-page View Model MUST implement `to_dict()` returning a dedicated JSON-serializable Pydantic v2 model from `risc_tool/data/models/json_models.py`.
- Deserialization `from_dict()` methods MUST accept `errors: Literal["ignore", "raise"] = "raise"` and return a tuple `(instance, invalid_items)` (or `SessionRestoreResult` for `Session`) so valid data is restored while invalid items are safely flagged and pruned.
- When generating Python code strings containing file paths, always sanitize Windows path strings using `.replace("\\", "/")` to prevent invalid escape sequences in generated code.

## Tooling & Environment Execution
- Any Python command must be executed through `uv`.
- Use `uv run ...` for Python entrypoints (e.g., `uv run pytest`, `uv run ruff check`, `uv run streamlit run main.py`, `uv run python script.py`).
- Direct invocations of system Python or tools outside `uv` are explicitly disallowed.
