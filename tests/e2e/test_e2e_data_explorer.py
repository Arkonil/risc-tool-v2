"""End-to-end tests for Data Explorer feature using SeleniumBase."""

import os

import pytest

if os.environ.get("RUN_E2E", "").strip() != "1":
    pytest.skip(
        "E2E tests skipped: set RUN_E2E=1 or use --run-e2e to run",
        allow_module_level=True,
    )

from tests.e2e.helpers import import_data_source, navigate_to

pytestmark = pytest.mark.skip(
    reason="Data Explorer E2E tests disabled temporarily; need fixing"
)


def _load_data_on_explorer(sb, streamlit_server, train_path):
    """Load data via the Data Explorer's 'Load Data' button."""
    navigate_to(sb, streamlit_server, "Data Explorer")

    # Click "Load Data" button which uses st.switch_page
    load_btn = '//button[contains(., "Load Data")]'
    sb.wait_for_element_clickable(load_btn, timeout=15)
    sb.click(load_btn)

    # Now on Data Importer page, import data
    import_data_source(sb, streamlit_server, filepath=train_path, label="Train Data")

    # Navigate back to Data Explorer using sidebar navigation (client-side routing)
    # Find and click the Data Explorer link in sidebar
    de_link_xpath = (
        '//section[@data-testid="stSidebar"]//a[contains(., "Data Explorer")]'
    )
    sb.wait_for_element_visible(de_link_xpath, timeout=10)
    sb.click(de_link_xpath)

    sb.wait_for_element_visible('[data-testid="stTabs"]', timeout=30)


@pytest.mark.e2e
@pytest.mark.smoke
def test_data_explorer_iv_and_outliers(sb, streamlit_server, test_data_paths):
    """Test Data Explorer IV Analysis and Outlier Rules workflows."""
    _load_data_on_explorer(sb, streamlit_server, test_data_paths["train"])

    sb.wait_for_element_visible('[data-testid="stTabs"]', timeout=15)
    sb.assert_text("IV Analysis")

    outlier_tab_xpath = (
        '//button[@role="tab" and contains(., "Outlier Rules")]'
        ' | //p[contains(text(), "Outlier Rules")]'
    )
    sb.wait_for_element_visible(outlier_tab_xpath, timeout=15)
    sb.click(outlier_tab_xpath)

    sb.wait_for_element_visible(
        '//button[contains(., "Save Rule") or contains(., "Rule Saved")]', timeout=20
    )
    sb.assert_text("Comparison Operation")


@pytest.mark.e2e
@pytest.mark.regression
def test_data_explorer_iv_chart_renders(sb, streamlit_server, test_data_paths):
    """Test IV analysis section renders with loaded data."""
    _load_data_on_explorer(sb, streamlit_server, test_data_paths["train"])

    sb.wait_for_text_visible("Target Variable", timeout=20)
    sb.assert_element('div[data-testid="stVegaLiteChart"]')


@pytest.mark.e2e
@pytest.mark.regression
def test_data_explorer_create_outlier_rule(sb, streamlit_server, test_data_paths):
    """Test creating an outlier rule in Data Explorer."""
    _load_data_on_explorer(sb, streamlit_server, test_data_paths["train"])

    # Switch to Outlier Rules tab
    outlier_tab_xpath = (
        '//button[@role="tab" and contains(., "Outlier Rules")]'
        ' | //p[contains(text(), "Outlier Rules")]'
    )
    sb.wait_for_element_visible(outlier_tab_xpath, timeout=15)
    sb.click(outlier_tab_xpath)
    sb.wait_for_element_visible(
        '//button[contains(., "Save Rule") or contains(., "Rule Saved")]', timeout=20
    )

    # Select a variable
    sb.wait_for_element_visible('[data-testid="stSelectbox"]', timeout=15)
    # Click the selectbox to open options
    variable_selector = '//div[contains(@data-testid, "stSelectbox")][1]'
    sb.click(variable_selector)
    sb.wait_for_element_visible(
        '//div[contains(@class, "stSelectboxVirtualDropdown")]', timeout=10
    )

    # Select first available option
    first_option = '//div[contains(@class, "stSelectboxVirtualDropdown")]//li[1]'
    sb.click(first_option)

    # Click Save Rule
    sb.wait_for_element_clickable('//button[contains(., "Save Rule")]', timeout=10)
    sb.click('//button[contains(., "Save Rule")]')

    # Verify rule was saved
    sb.wait_for_text_visible("Rule Saved", timeout=15)
    sb.assert_text("Comparison Operation")
