# Goal
Make `test_data_importer_multiple_sources` genuinely pass (remove the xfail marker),
matching the manual flow the user confirms works.

# Current state (verified by reading current files)
- `tests/e2e/helpers.py` — `import_data_source(..., navigate=True)`; second import uses
  `navigate=False`. After clicking "Add Data Source" it fills the empty form's inputs
  via `inputs[-2]`/`inputs[-1]`, then sends `Keys.ENTER` on BOTH the label (line ~154)
  and the path (line ~162) inputs, then clicks "Add", then polls up to 240s for the
  "Add Data Source" button to reappear (success) or an error alert.
- `tests/e2e/test_e2e_data_importer.py` — `multiple_sources` is marked
  `@pytest.mark.xfail(run=True)` with an (likely wrong) "session instability" reason.
- `tests/e2e/conftest.py` — fresh function-scoped server per test.

# Diagnosis
Earlier "Streamlit session instability" conclusion is likely wrong: its only evidence was
repeated `set_session_state:51 | Session state initialized` log lines, which are
consistent with normal `st.navigation` page re-renders, not necessarily fresh data
sessions. The manual flow (identical sequence) works, so the gap is in how automation
drives the form.

## Primary hypothesis
The `Keys.ENTER` added to the LABEL input (line ~154). Manual users don't press Enter in
the label field. `st.text_input` triggers a rerun on Enter, which re-renders/invalidates
the widget before the path is filled and "Add" is clicked, so the button `on_click`
reads stale/empty value -> empty form retained with typed text, no source created, wait
times out. This matches the observed failure exactly.

## Secondary suspects (only if #1 does not resolve)
- Value-commit race: `sb.click("Add")` fires before Streamlit flushes the React widget
  onChange from `send_keys`. Fix: blur the field + short settle before clicking Add.
- Wrong empty-form targeting: verify exactly 4 text inputs exist and `inputs[-2]`/
  `inputs[-1]` are the empty form's when a prior source is present.

# Execution steps
1. Remove the xfail marker from `test_data_importer_multiple_sources` (let it run).
2. Remove the `label_input.send_keys(Keys.ENTER)` line in `import_data_source` (keep
   Enter only on the path input). Run the test alone.
3. If still failing, add lightweight live instrumentation to `import_data_source`
   (dump right after clicking Add: number of text inputs, the values of the last two,
   whether the empty-form container is present, and any error-alert text) to
   distinguish "wrong form targeted" vs "value not committed" vs "session reset".
4. Apply the targeted fix (blur + settle before clicking Add, and/or scope the fill to
   the empty form's container via its `st-key-...file_selector-ffffffff-...` class).
5. Remove all debug/instrumentation, ensure no xfail marker remains, then:
   - `uv run pytest tests/e2e/test_e2e_data_importer.py --no-header -v --run-e2e` -> 4 passed
   - `uv run pytest tests --no-header -q` -> no regressions
   - `uv run ruff check tests/e2e/helpers.py tests/e2e/test_e2e_data_importer.py ...`

# Constraints / notes
- Keep `PAGE_PATHS["Data Importer"] = "/"` (never `/data-importer`).
- Keep `navigate=False` for the second import (a hard `sb.open` between imports is the
  real way to lose the in-memory session; that part of the earlier reasoning is sound).
- Do not add comments to code unless asked.
