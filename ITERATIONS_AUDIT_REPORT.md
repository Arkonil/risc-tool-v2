# Iterations Audit Report

## Scope and Validation

This report tracks findings from the original static audit of the iterations feature path and their resolution status against the current implementation.

The full test suite now runs and passes via `uv run pytest tests/ -q` (**349 tests passing**). Tests exercise the UI (`streamlit.testing.v1.AppTest`), repositories, domain models, and services. Two production defects surfaced by the new tests were fixed during test hardening:

- [`iterations_vm.set_metadata`](risc_tool/ui/iterations/iterations_vm.py) crashed with `TypeError` when the sidebar passed `filter_ids=` (used by `single_var_iteration.py` and `common.py`); `IterationMetadata.update()` only accepted `current_filter_ids`. The VM now aliases `filter_ids` to `current_filter_ids`.
- `IterationsViewModel.scalar_selected` previously checked `portfolio_scalar` (which defaults to `1.0` and is never NaN) instead of `current_rate`/`lifetime_rate`, so scalar validation never failed when scalars were unset. It now checks the actual rates.

## Status Summary

| # | Finding | Status |
|---|---------|--------|
| 1 | Double-variable page renders as empty | **Resolved** |
| 2 | Child creation stores no usable segmentation state | **Resolved** |
| 3 | Double mapping compares incompatible segment ID types | **Resolved** |
| 4 | Double-iteration configuration inputs are discarded | **Resolved** |
| 5 | Root iteration can be created with no groups | **Resolved** |
| 6 | Contradictory variable-type choice crashes banding | **Resolved** |
| 7 | Child risk-segment editor edits do nothing | **Resolved** |
| 8 | Graph model does not enforce its DAG invariant | **Resolved** |
| 9 | Repository APIs bypass UI safety checks | **Partially resolved** |
| 10 | Iterations stay active after all data sources become invalid | **Open** |
| 11 | Numeric banding reversal uses a hard-coded `1.0` delta | **Open** |
| 12 | Automatic banding has unhandled degenerate-data cases | **Partially resolved** |
| 13 | Selected segment configuration can create invalid bands without validation | **Resolved** |
| 14 | Deletion accepts nonexistent IDs and still emits a change | **Resolved** |
| 15 | Graph node content is interpolated as raw HTML | **Resolved** |
| 16 | Graph page uses a deprecated Streamlit parameter | **Resolved** |

## Resolved Findings

### 1. Double-variable iterations are user-reachable but render as an empty page

**Resolved.** [`double_var_iteration`](risc_tool/ui/iterations/double_var_iteration.py) is fully implemented: it validates the current iteration type, renders the sidebar (`iteration_sidebar_components`), shows split (grid) or linear layouts for default and editable grids, renders metric views, surfaces errors/warnings, and walks the ancestry chain rendering each previous iteration's metric table. `test_double_var_iteration.py` (23 tests) covers both layouts, the sidebar, split-view toggling, chain display, and invalid-type error handling.

### 2. Child iteration creation stores no usable segmentation state

**Resolved.** [`add_double_var_iteration`](risc_tool/data/repositories/iterations.py) now initializes full state. With `auto_band=False` it creates default groups (quantile-based for numerical, even-split for categorical) plus an identity risk-segment grid. With `auto_band=True` it computes per-parent-segment cut points, merges equivalent rows, builds the risk-segment grid from summarized metrics, applies upgrade/downgrade limits, and (optionally) auto-rank ordering via monotone cum-max. Covered by `test_iterations_repository.py::test_add_double_var_iteration_*` and `test_double_var_iteration_type_matching`.

### 3. Double-variable mapping compares incompatible segment ID types

**Resolved.** [`DoubleVarIteration.get_risk_segment_expr`](risc_tool/data/models/iteration.py) now compares `pl.col(prev_seg_col) == parent_seg_id.value` (integer-to-integer), and the upstream mapping expressions cast to `pl.UInt16`. The prior `str(parent_seg_id)` mismatch is gone.

### 4. All double-iteration configuration inputs are discarded

**Resolved.** `auto_band`, `use_scalar`, `remove_outliers`, `upgrade_limit`, `downgrade_limit`, and `auto_rank_ordering` are all consumed in `add_double_var_iteration`. Scalar/MAF scaling is applied during grid selection, and `auto_rank_ordering` runs monotone cum-max post-processing. The repo also validates that upgrade/downgrade limits are supplied when auto-banding.

### 5. A root iteration can be created with no groups and no way to repair it

**Resolved.** [`add_single_var_iteration`](risc_tool/data/repositories/iterations.py) builds group sets directly from `selected_segment_config`, where `GroupID` maps 1:1 to `RiskSegmentID`. Since single-variable creation now mandatorily requires selecting valid risk segments with finite upper bounds (Finding 13), a root iteration can no longer be created group-less.

### 6. The creation form allows a data-type choice that crashes automatic banding

**Resolved.** [`validate_iter_create_params`](risc_tool/ui/iterations/iterations_vm.py) rejects a categorical-schema variable marked `NUMERICAL`, and the creator coerces any non-numeric schema variable to `CATEGORICAL` before calling `add_*_var_iteration` (`iteration_creator.py`). The auto-band services also defensively reject non-numeric variables for numeric bands and numeric variables for categorical bands. Covered by `test_iteration_creator_validation.py` (`test_numerical_type_on_string_variable_error` and friends).

### 7. The risk-segment editor for child creation is editable but its edits do nothing

**Resolved.** The `SELECTED` checkbox column in [`risk_segment_details_selector`](risc_tool/ui/iterations/iteration_creator.py) is now `disabled=not is_single`, so child creation displays the root node's segments read-only. The return value is only consumed for single-variable creation.

### 8. The graph model does not enforce its documented DAG invariant

**Resolved.** [`IterationGraph.add_child`](risc_tool/data/models/iteration_graph.py) now raises on self-links, on re-parenting a child that already has a different parent, and on edges that would create a cycle (via `get_descendants`). Covered by `test_iteration_models.py::test_iteration_graph_dag_invariants`.

### 14. Deletion accepts nonexistent IDs and still emits a change

**Resolved.** [`delete_iteration`](risc_tool/data/repositories/iterations.py) now checks for the ID, logs a warning, and returns without deleting or notifying subscribers when the iteration does not exist. Covered by `test_iterations_repo_edge_cases.py::test_delete_nonexistent_iteration_warns`.

### 13. Selected segment configuration can create invalid automatic bands without validation

**Resolved.** [`RiskSegmentConfig.has_finite_upper_bound_segment()`](risc_tool/data/models/config.py) now validates that at least one selected risk segment has a finite upper rate bound (`upper_rate < float("inf")`). Creation of a single-variable iteration is defensively rejected with a `ValueError` in [`add_single_var_iteration`](risc_tool/data/repositories/iterations.py) and surfaces a live UI validation error message disabling creation in [`validate_iter_create_params`](risc_tool/ui/iterations/iterations_vm.py) and [`iteration_creator`](risc_tool/ui/iterations/iteration_creator.py) whenever empty or infinite-only risk segments are selected. Covered by `test_has_finite_upper_bound_segment`, `test_add_single_var_iteration_finite_upper_bound_validation`, and `test_validate_iter_create_params_finite_risk_segment`.

### 15. Graph node content is interpolated as raw HTML

**Resolved.** [`streamlit_flow_graph`](risc_tool/ui/iterations/graph.py) now escapes iteration names and variable names via `html.escape()` before embedding them in node content.

### 16. The graph page uses a deprecated Streamlit parameter

**Resolved.** All buttons on the graph page now use `width="stretch"` instead of `use_container_width=True`.

## Partially Resolved Findings

### 9. Repository APIs bypass UI safety checks

**Partially resolved.** [`add_double_var_iteration`](risc_tool/data/repositories/iterations.py) now validates that the parent iteration exists and that the variable/dtype pair exists in the common columns before creating the node. Graph-level safety (self-links, cycles, multiple parents) is also enforced in `IterationGraph.add_child`. Maximum-depth enforcement remains UI-only via `IterationsViewModel.can_have_child` and the graph's Add Child button; the repository does not check depth, so a non-UI caller can still persist an over-depth child.

### 12. Automatic banding has unhandled degenerate-data cases

**Partially resolved.** `does_high_value_implies_high_risk` now guards NaN (`fill_nan(0)`), empty frames, and null heuristic output (returns `True`), and `create_auto_numeric_bands` emits a zero-width group when no rows satisfy a segment rather than crashing. Creation validation still does not verify that the selected data can actually produce valid groups (e.g., all-zero bad rates, zero balances, or empty filtered data producing invalid or empty bands).

## Open Findings

### 10. Iterations remain marked active after all data sources become invalid or are removed

[`IterationsRepository.on_dependency_update`](risc_tool/data/repositories/iterations.py) still returns early when there are no valid sources, leaving pre-existing iterations marked `active=True` even though their variables are no longer usable. `test_iterations_repo_edge_cases.py::test_iteration_active_flag_on_data_change` only covers the happy path and does not exercise source removal or invalidation.

### 11. Automatic numeric banding corrupts continuous-variable boundaries when high values imply lower risk

The reversal logic in [`create_auto_numeric_bands`](risc_tool/data/services/auto_band.py) still transforms generated bounds with `-bound - 1.0` (`delta = 1.0`). That one-unit adjustment only approximates discrete integers and introduces gaps or incorrect allocation for decimals, currency, ratios, and other continuous numerical variables. The group predicate is `(lower, upper]`, so this should be handled by interval semantics rather than a hard-coded `1.0`. There is still no test covering descending continuous numeric bands.

## Test Coverage

The original test-gap section is largely obsolete. Current coverage includes:

- **Double-variable creation, mapping, and grids**: `test_iterations_repository.py::test_add_double_var_iteration_*`, `test_double_var_iteration.py`, `test_iterations_vm_edge_cases.py` (`test_metric_grids_*`, `test_select_groups_*`, `test_add_new_group*`), `test_iterations_repo_edge_cases.py::test_set_grid_*` / `test_get_risk_segment_grid_*`, `test_iteration_models.py::test_double_var_iteration_type_matching`.
- **Graph invariants and depth enforcement**: `test_iteration_models.py::test_iteration_graph_dag_invariants`, `test_graph_navigation.py::test_depth_limit_prevents_add_child`, `test_iterations_vm_edge_cases.py::test_can_have_child`.
- **Contradictory variable types**: `test_iteration_creator_validation.py::test_numerical_type_on_string_variable_error`.
- **Repository creation and defaults**: `test_iterations_repository.py` (12 tests) covers quantile/categorical defaults, rename/delete semantics, and double-var initialization.
- **Full workflows**: `test_iterations_integration.py::test_full_single_var_flow_integration`; `test_iteration_creator_validation.py` includes `test_create_single_var_iteration_success` and `test_create_double_var_iteration_success`.

Remaining test gaps:

- Empty/zero-data automatic banding (all-zero bad rates, zero balances, null-heavy data, empty filtered data).
- Descending continuous numeric bands (the `-bound - 1.0` reversal).
- Repository-level maximum-depth enforcement.
- Source removal / invalidation leaving `active=True` on stale iterations.

## Remaining Repair Order

1. Clear or recompute `active` flags when data sources become invalid or are removed (finding 10).
2. Replace the hard-coded `1.0` delta in numeric band reversal with interval-semantics handling for continuous variables, and add descending-band tests (finding 11).
3. Validate, before persisting, that at least one risk segment is selected and that generated groups are nonempty and valid (finding 13).
4. Enforce maximum depth in the repository rather than only in the UI (finding 9).
5. Consider allowing `set_controls` to repair group sets and hardening banding against degenerate data (findings 5 and 12).
