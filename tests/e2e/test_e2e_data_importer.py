"""End-to-end tests for Data Importer feature using SeleniumBase.

These tests are opt-in: they require SeleniumBase (installed via the
``e2e`` extra: ``uv sync -E e2e``) and a real browser/webdriver. Set the
environment variable ``RUN_E2E=1`` (or pass ``--run-e2e``) to run them.
Without that, this module is skipped at collection time so that the
SeleniumBase import below does not fail on machines where it is absent.
"""

import pytest

# if os.environ.get("RUN_E2E", "").strip() != "1":
#     pytest.skip(
#         "E2E tests skipped: set RUN_E2E=1 or use --run-e2e to run",
#         allow_module_level=True,
#     )
from tests.e2e.helpers import (
    delete_source_by_label,
    import_data_source,
    navigate_to,
    setup_browser,
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
        filepath=test_data_paths["train"],
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
        sb, streamlit_server, filepath=test_data_paths["train"], label="Train Data"
    )

    # Import second source (reuse the same session/Streamlit page so the
    # first source is retained; a hard reload would start a fresh session)
    import_data_source(
        sb,
        streamlit_server,
        filepath=test_data_paths["val"],
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
        sb, streamlit_server, filepath=test_data_paths["train"], label="To Delete"
    )

    # Find and click delete button for the source
    delete_source_by_label(sb, "To Delete")

    # Confirm it's removed: the empty data source form is shown again
    sb.wait_for_element_visible('[data-testid="stAppViewContainer"]', timeout=10)
    sb.wait_for_text_visible("New Data Source", timeout=10)
    sb.assert_text_not_visible("To Delete")
