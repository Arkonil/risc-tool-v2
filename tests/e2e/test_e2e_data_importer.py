"""End-to-end tests for Data Importer feature using SeleniumBase.

These tests are opt-in: they require SeleniumBase (installed via the
``e2e`` extra: ``uv sync -E e2e``) and a real browser/webdriver. Set the
environment variable ``RUN_E2E=1`` (or pass ``--run-e2e``) to run them.
Without that, this module is skipped at collection time so that the
SeleniumBase import below does not fail on machines where it is absent.
"""

import pytest
from selenium.webdriver.common.keys import Keys

from tests.e2e.helpers import (
    _commit_widget_input,
    _error_alert_text,
    cancel_empty_data_source,
    delete_source_by_label,
    import_data_source,
    navigate_to,
    refresh_source_by_label,
    setup_browser,
    switch_preview_tab,
    update_source_label,
)


@pytest.mark.e2e
@pytest.mark.smoke
def test_data_importer_flow(sb, streamlit_server, test_data_paths):
    """Test importing a primary dataset and verifying data preview."""
    setup_browser(sb, streamlit_server)
    sb.assert_text("Data Importer", "h1")

    import_data_source(
        sb,
        streamlit_server,
        filepath=test_data_paths["e2e_train"],
        label="Train Data",
        click_label="Add",
    )

    sb.wait_for_text_visible("File imported successfully", timeout=20)
    sb.assert_text("Preview Data")
    sb.assert_element('[data-testid="stDataFrame"]')


@pytest.mark.e2e
@pytest.mark.regression
def test_data_importer_invalid_path_shows_error(sb, streamlit_server):
    """Test invalid file path handling in Data Importer."""
    navigate_to(sb, streamlit_server, "Data Importer")

    inputs = sb.find_elements('[data-testid="stTextInput"] input')
    if len(inputs) < 2:
        raise AssertionError("Expected label and path inputs in Data Importer")

    inputs[0].click()
    inputs[0].clear()
    inputs[0].send_keys("Broken Source")

    inputs[1].click()
    inputs[1].clear()
    inputs[1].send_keys("P:/python/risc-tool/tests/test_data/does_not_exist.csv")

    sb.click('//button[contains(., "Add")]')
    sb.wait_for_element_visible('[data-testid="stAlert"]', timeout=20)


@pytest.mark.e2e
@pytest.mark.regression
def test_data_importer_multiple_sources(sb, streamlit_server, test_data_paths):
    """Test adding multiple data sources."""
    navigate_to(sb, streamlit_server, "Data Importer")

    # Import first source
    import_data_source(
        sb, streamlit_server, filepath=test_data_paths["e2e_train"], label="Train Data"
    )

    # Import second source (reuse the same session/Streamlit page so the
    # first source is retained; a hard reload would start a fresh session)
    import_data_source(
        sb,
        streamlit_server,
        filepath=test_data_paths["e2e_val"],
        label="Val Data",
        navigate=False,
    )

    # Verify both appear in tabs
    sb.wait_for_element_visible('[data-testid="stTabs"]', timeout=60)
    sb.assert_text("Train Data")
    sb.assert_text("Val Data")


@pytest.mark.e2e
@pytest.mark.regression
def test_data_importer_delete_source(sb, streamlit_server, test_data_paths):
    """Test deleting a data source."""
    navigate_to(sb, streamlit_server, "Data Importer")
    import_data_source(
        sb, streamlit_server, filepath=test_data_paths["e2e_train"], label="To Delete"
    )

    # Find and click delete button for the source
    delete_source_by_label(sb, "To Delete")

    # Confirm it's removed: the empty data source form is shown again
    sb.wait_for_element_visible('[data-testid="stAppViewContainer"]', timeout=10)
    sb.wait_for_text_visible("New Data Source", timeout=10)
    sb.assert_text_not_visible("To Delete")


@pytest.mark.e2e
@pytest.mark.regression
def test_data_importer_full_lifecycle(sb, streamlit_server, test_data_paths):
    """Test full Data Importer user lifecycle in a single consolidated session:

    1. Initial empty state & disabled delete button verification
    2. Empty filepath validation error handling
    3. Invalid filepath error handling
    4. First data source import (happy path) & data preview verification
    5. 'Add Data Source' form toggle and cancellation via delete button
    6. Second data source import with custom delimiter (semicolon)
    7. Preview tabs switching between sources
    8. Updating/refreshing an existing data source label
    9. Cascading deletion: deleting one source preserves the other;
       deleting the last returns to empty state.
    """
    # 1. Initial empty state
    setup_browser(sb, streamlit_server)
    sb.assert_text("Data Importer", "h1")
    sb.assert_text("Select Data Sources")
    sb.assert_text("New Data Source")
    sb.assert_element_not_visible('[data-testid="stDataFrame"]')
    sb.assert_text_not_visible("Preview Data")
    # Delete button in initial empty form must be disabled
    sb.assert_element_visible(
        '//div[contains(., "New Data Source")]//div[contains(@class, "st-key-delete_button")]//button[@disabled]'
    )

    # 2. Empty filepath validation
    sb.click('//button[contains(., "Add")]')
    sb.wait_for_element_visible('[data-testid="stAlert"]', timeout=10)
    sb.assert_text("does not exist or is not a file")

    # 3. Invalid filepath error handling
    inputs = sb.find_elements('[data-testid="stTextInput"] input')
    label_inp = inputs[-2]
    path_inp = inputs[-1]
    label_inp.click()
    label_inp.send_keys(Keys.CONTROL + "a")
    label_inp.send_keys(Keys.BACKSPACE)
    label_inp.send_keys("Invalid Source")
    _commit_widget_input(sb, label_inp, expected="Invalid Source")

    path_inp.click()
    path_inp.send_keys(Keys.CONTROL + "a")
    path_inp.send_keys(Keys.BACKSPACE)
    path_inp.send_keys("P:/does/not/exist.csv")
    _commit_widget_input(sb, path_inp, expected="P:/does/not/exist.csv")

    sb.click('//button[contains(., "Add")]')
    sb.wait_for_element_visible('[data-testid="stAlert"]', timeout=10)
    error_text = _error_alert_text(sb)
    assert error_text, "Expected error alert for non-existent file path"

    # 4. Primary data source import (happy path)
    import_data_source(
        sb,
        streamlit_server,
        filepath=test_data_paths["e2e_train"],
        label="Train Data",
        navigate=False,
    )
    sb.wait_for_text_visible("File imported successfully", timeout=30)
    sb.wait_for_text_visible("Preview Data", timeout=30)
    sb.wait_for_element_visible('[data-testid="stDataFrame"]', timeout=30)

    # 5. Empty form toggle and cancellation
    sb.wait_for_element_visible('//button[contains(., "Add Data Source")]', timeout=15)
    sb.click('//button[contains(., "Add Data Source")]')
    sb.wait_for_text_visible("New Data Source", timeout=10)

    cancel_empty_data_source(sb)
    sb.wait_for_text_not_visible("New Data Source", timeout=10)
    sb.wait_for_element_visible('//button[contains(., "Add Data Source")]', timeout=10)

    # 6. Second data source import with custom delimiter (semicolon)
    import_data_source(
        sb,
        streamlit_server,
        filepath=test_data_paths["semicolon"],
        label="Semicolon Data",
        navigate=False,
        delimiter_name="Semicolon",
    )
    sb.wait_for_element_visible('[data-testid="stTabs"]', timeout=30)
    sb.assert_text("Train Data")
    sb.assert_text("Semicolon Data")

    # 7. Preview tab switching
    switch_preview_tab(sb, "Semicolon Data")
    sb.wait_for_element_visible('[data-testid="stDataFrame"]', timeout=15)
    switch_preview_tab(sb, "Train Data")
    sb.wait_for_element_visible('[data-testid="stDataFrame"]', timeout=15)

    # 8. Updating/refreshing an existing data source label
    update_source_label(sb, "Train Data", "Updated Train Data")
    refresh_source_by_label(sb, "Updated Train Data")
    sb.wait_for_text_visible("File imported successfully", timeout=30)
    sb.wait_for_text_visible("Updated Train Data", timeout=20)

    # 9. Cascading deletion
    # Delete first source ("Updated Train Data")
    delete_source_by_label(sb, "Updated Train Data")
    sb.sleep(2)
    sb.assert_text_not_visible("Updated Train Data")
    sb.assert_text("Semicolon Data")
    sb.assert_text("Preview Data")

    # Delete remaining source ("Semicolon Data")
    delete_source_by_label(sb, "Semicolon Data")
    sb.sleep(2)
    # All sources gone: empty form appears, Preview Data disappears
    sb.wait_for_text_visible("New Data Source", timeout=15)
    sb.assert_text_not_visible("Preview Data")
    sb.assert_element_not_visible('[data-testid="stDataFrame"]')
