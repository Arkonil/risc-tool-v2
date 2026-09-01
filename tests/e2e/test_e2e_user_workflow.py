"""End-to-end tests for complete user workflow using SeleniumBase.
Tests mimic real user behavior: sequential sidebar navigation, mouse clicks, and send keys only.
"""

import os

import pytest

if os.environ.get("RUN_E2E", "").strip() != "1":
    pytest.skip(
        "E2E tests skipped: set RUN_E2E=1 or use --run-e2e to run",
        allow_module_level=True,
    )

from selenium.webdriver.common.keys import Keys

from tests.e2e.helpers import (
    click_primary_action,
    import_data_source,
    navigate_to,
    set_code_editor_value,
    setup_browser,
)

pytestmark = pytest.mark.skip(
    reason="User workflow E2E test disabled temporarily; need fixing"
)


@pytest.mark.e2e
@pytest.mark.smoke
def test_complete_user_workflow(sb, streamlit_server, test_data_paths):
    """Test complete user workflow: Data Importer -> Data Explorer -> Filters -> Metrics."""

    # ============================================================
    # STEP 1: DATA IMPORTER - Start at home page
    # ============================================================
    setup_browser(sb, streamlit_server)
    sb.assert_text("Data Importer", "h1")

    # Import first dataset (train)
    import_data_source(
        sb,
        streamlit_server,
        filepath=test_data_paths["train"],
        label="Train Data",
        click_label="Add",
    )

    # Verify data source appears in tabs
    sb.wait_for_element_visible('[data-testid="stTabs"]', timeout=15)
    sb.sleep(2)
    sb.assert_text("Train Data")

    # Try to import invalid path - should show error
    sb.wait_for_element_clickable(
        '//button[contains(., "Add Data Source")]', timeout=10
    )
    sb.click('//button[contains(., "Add Data Source")]')

    inputs = sb.find_elements('[data-testid="stTextInput"] input')
    inputs[0].click()
    inputs[0].send_keys(Keys.CONTROL + "a")
    inputs[0].send_keys(Keys.BACKSPACE)
    inputs[0].send_keys("Bad Data")

    inputs[1].click()
    inputs[1].send_keys(Keys.CONTROL + "a")
    inputs[1].send_keys(Keys.BACKSPACE)
    inputs[1].send_keys("P:/python/risc-tool/tests/test_data/does_not_exist.csv")

    sb.click('//button[contains(., "Add")]')
    sb.wait_for_element_visible('[data-testid="stAlert"]', timeout=20)

    # ============================================================
    # STEP 2: DATA EXPLORER - Use sidebar navigation
    # ============================================================
    navigate_to(sb, streamlit_server, "Data Explorer")
    sb.wait_for_element_visible('[data-testid="stTabs"]', timeout=15)
    sb.assert_text("IV Analysis")

    # Test IV Analysis tab
    sb.wait_for_text_visible("Target Variable", timeout=10)

    # Switch to Outlier Rules tab
    outlier_tab = '//button[@role="tab" and contains(., "Outlier Rules")]'
    sb.wait_for_element_clickable(outlier_tab, timeout=10)
    sb.click(outlier_tab)
    sb.wait_for_element_visible(
        '//button[contains(., "Save Rule") or contains(., "Rule Saved")]', timeout=15
    )
    sb.assert_text("Comparison Operation")

    # Create an outlier rule
    var_selector = '//div[contains(@data-testid, "stSelectbox")][1]'
    sb.wait_for_element_visible(var_selector, timeout=10)
    sb.click(var_selector)
    sb.wait_for_element_visible(
        '//div[contains(@class, "stSelectboxVirtualDropdown")]', timeout=5
    )
    first_option = '//div[contains(@class, "stSelectboxVirtualDropdown")]//li[1]'
    sb.click(first_option)

    sb.wait_for_element_clickable('//button[contains(., "Save Rule")]', timeout=10)
    sb.click('//button[contains(., "Save Rule")]')
    sb.wait_for_text_visible("Rule Saved", timeout=10)

    # ============================================================
    # STEP 3: FILTERS - Use sidebar navigation
    # ============================================================
    navigate_to(sb, streamlit_server, "Filters")
    sb.wait_for_element_visible("h1", timeout=15)
    sb.assert_text("Filters", "h1")

    # Click "Create Filter" button
    click_primary_action(sb, "Create Filter")
    sb.wait_for_element_visible('input[placeholder="Filter Name"]', timeout=10)

    # Enter filter name
    name_input = sb.find_element('input[placeholder="Filter Name"]')
    name_input.click()
    name_input.send_keys("High Credit Score")

    # Enter filter query in code editor
    set_code_editor_value(sb, "credit_score > 700")

    # Verify and save
    click_primary_action(sb, "Verify")
    click_primary_action(sb, "Save")
    sb.wait_for_text_visible("Filters", timeout=15)
    sb.assert_text("High Credit Score")

    # Create another filter with complex expression
    click_primary_action(sb, "Create Filter")
    sb.wait_for_element_visible('input[placeholder="Filter Name"]', timeout=10)
    name_input = sb.find_element('input[placeholder="Filter Name"]')
    name_input.send_keys("High Income and Good Score")
    set_code_editor_value(sb, "income > 50000 and credit_score > 650")
    click_primary_action(sb, "Verify")
    click_primary_action(sb, "Save")
    sb.wait_for_text_visible("Filters", timeout=15)
    sb.assert_text("High Income and Good Score")

    # Edit first filter - click edit button
    edit_btn = (
        '//button[contains(@key, "edit_btn") and contains(@key, "High Credit Score")]'
    )
    sb.wait_for_element_clickable(edit_btn, timeout=10)
    sb.click(edit_btn)
    sb.wait_for_element_visible('input[placeholder="Filter Name"]', timeout=10)
    name_input = sb.find_element('input[placeholder="Filter Name"]')
    name_input.click()
    name_input.send_keys(Keys.CONTROL + "a")
    name_input.send_keys(Keys.BACKSPACE)
    name_input.send_keys("High Credit Score Edited")
    set_code_editor_value(sb, "credit_score >= 750")
    click_primary_action(sb, "Verify")
    click_primary_action(sb, "Save")
    sb.wait_for_text_visible("Filters", timeout=15)
    sb.assert_text("High Credit Score Edited")

    # Delete the edited filter
    delete_btn = '//button[contains(@key, "delete_btn") and contains(@key, "High Credit Score Edited")]'
    sb.wait_for_element_clickable(delete_btn, timeout=10)
    sb.click(delete_btn)
    sb.wait_for_element_clickable('//button[contains(., "Delete")]', timeout=5)
    sb.click('//button[contains(., "Delete")]')
    sb.wait_for_text_visible("Filters", timeout=10)

    # ============================================================
    # STEP 4: METRICS - Use sidebar navigation
    # ============================================================
    navigate_to(sb, streamlit_server, "Metrics")
    sb.wait_for_element_visible("h1", timeout=15)
    sb.assert_text("Metrics", "h1")

    # Create metric via Code Editor
    click_primary_action(sb, "Create Metric")
    sb.wait_for_element_visible('input[placeholder="Metric Name"]', timeout=10)

    name_input = sb.find_element('input[placeholder="Metric Name"]')
    name_input.send_keys("Total Volume")

    # Use Code Editor (default)
    set_code_editor_value(sb, "credit_score.size")

    click_primary_action(sb, "Verify")
    click_primary_action(sb, "Save")
    sb.wait_for_text_visible("Metrics", timeout=15)
    sb.assert_text("Total Volume")

    # Create metric via Template Builder
    click_primary_action(sb, "Create Metric")
    sb.wait_for_element_visible('input[placeholder="Metric Name"]', timeout=10)
    name_input = sb.find_element('input[placeholder="Metric Name"]')
    name_input.send_keys("Approval Rate")

    # Switch to Template Builder
    sb.wait_for_element_visible('//label[contains(., "Template Builder")]', timeout=10)
    sb.click('//label[contains(., "Template Builder")]')
    sb.sleep(0.5)

    # Select Approval Rate template
    template_selector = '//div[contains(@data-testid, "stSelectbox")]'
    sb.wait_for_element_visible(template_selector, timeout=10)
    sb.click(template_selector)
    sb.wait_for_element_visible(
        '//div[contains(@class, "stSelectboxVirtualDropdown")]', timeout=5
    )
    approval_option = '//div[contains(@class, "stSelectboxVirtualDropdown")]//li[contains(., "Approval Rate")]'
    sb.click(approval_option)

    # Configure template - select status column
    status_selector = '(//div[contains(@data-testid, "stSelectbox")])[2]'
    sb.wait_for_element_visible(status_selector, timeout=10)
    sb.click(status_selector)
    sb.wait_for_element_visible(
        '//div[contains(@class, "stSelectboxVirtualDropdown")]', timeout=5
    )
    status_option = '//div[contains(@class, "stSelectboxVirtualDropdown")]//li[contains(., "status")]'
    sb.click(status_option)

    # Select approved values
    approved_selector = '(//div[contains(@data-testid, "stMultiSelect")])[1]'
    sb.click(approved_selector)
    sb.wait_for_element_visible(
        '//div[contains(@class, "stSelectboxVirtualDropdown")]', timeout=5
    )
    approved_option = '//div[contains(@class, "stSelectboxVirtualDropdown")]//li[contains(., "Approved")]'
    sb.click(approved_option)

    # Select declined values
    declined_selector = '(//div[contains(@data-testid, "stMultiSelect")])[2]'
    sb.click(declined_selector)
    sb.wait_for_element_visible(
        '//div[contains(@class, "stSelectboxVirtualDropdown")]', timeout=5
    )
    declined_option = '//div[contains(@class, "stSelectboxVirtualDropdown")]//li[contains(., "Declined")]'
    sb.click(declined_option)

    click_primary_action(sb, "Verify")
    click_primary_action(sb, "Save")
    sb.wait_for_text_visible("Metrics", timeout=15)
    sb.assert_text("Approval Rate")

    # Create metric with format options
    click_primary_action(sb, "Create Metric")
    sb.wait_for_element_visible('input[placeholder="Metric Name"]', timeout=10)
    name_input = sb.find_element('input[placeholder="Metric Name"]')
    name_input.send_keys("Percentage Metric")
    set_code_editor_value(sb, "credit_score.mean() / 1000")

    # Configure format options
    sb.click('//label[contains(., "Use Thousand Separator")]')
    sb.click('//label[contains(., "Is Percentage")]')
    decimal_input = sb.find_element('input[type="number"]')
    decimal_input.clear()
    decimal_input.send_keys("2")

    click_primary_action(sb, "Verify")
    click_primary_action(sb, "Save")
    sb.wait_for_text_visible("Metrics", timeout=15)
    sb.assert_text("Percentage Metric")

    # Edit a metric
    edit_btn = '//button[contains(@key, "edit_btn") and contains(@key, "Total Volume")]'
    sb.wait_for_element_clickable(edit_btn, timeout=10)
    sb.click(edit_btn)
    sb.wait_for_element_visible('input[placeholder="Metric Name"]', timeout=10)
    name_input = sb.find_element('input[placeholder="Metric Name"]')
    name_input.click()
    name_input.send_keys(Keys.CONTROL + "a")
    name_input.send_keys(Keys.BACKSPACE)
    name_input.send_keys("Total Volume Edited")
    click_primary_action(sb, "Verify")
    click_primary_action(sb, "Save")
    sb.wait_for_text_visible("Metrics", timeout=15)
    sb.assert_text("Total Volume Edited")

    # Delete the edited metric
    delete_btn = '//button[contains(@key, "delete_btn") and contains(@key, "Total Volume Edited")]'
    sb.wait_for_element_clickable(delete_btn, timeout=10)
    sb.click(delete_btn)
    sb.wait_for_element_clickable('//button[contains(., "Delete")]', timeout=5)
    sb.click('//button[contains(., "Delete")]')
    sb.wait_for_text_visible("Metrics", timeout=10)
    sb.assert_element_absent('//*[contains(text(), "Total Volume Edited")]')
