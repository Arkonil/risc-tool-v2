"""End-to-end tests for Metric feature using SeleniumBase."""

import os

import pytest

if os.environ.get("RUN_E2E", "").strip() != "1":
    pytest.skip(
        "E2E tests skipped: set RUN_E2E=1 or use --run-e2e to run",
        allow_module_level=True,
    )

from tests.e2e.helpers import (
    click_primary_action,
    ensure_data_loaded,
    navigate_to,
    set_code_editor_value,
)

pytestmark = pytest.mark.skip(
    reason="Metric E2E tests disabled temporarily; need fixing"
)


@pytest.mark.e2e
@pytest.mark.smoke
def test_metric_creation_flow(sb, streamlit_server, test_data_paths):
    """Test creating, configuring, and verifying a metric with Template Builder."""
    ensure_data_loaded(sb, streamlit_server, test_data_paths["train"])

    navigate_to(sb, streamlit_server, "Metrics")
    click_primary_action(sb, "Create Metric")

    sb.wait_for_element_visible('input[placeholder="Metric Name"]', timeout=20)
    sb.type('input[placeholder="Metric Name"]', "Total Account Volume")

    set_code_editor_value(sb, "credit_score.size")

    click_primary_action(sb, "Verify")
    click_primary_action(sb, "Save")

    sb.wait_for_text_visible("Metrics", timeout=20)
    sb.assert_text("Total Account Volume")


@pytest.mark.e2e
@pytest.mark.regression
def test_metric_invalid_expression_shows_error(sb, streamlit_server, test_data_paths):
    """Test invalid metric expression displays an error."""
    ensure_data_loaded(sb, streamlit_server, test_data_paths["train"])
    navigate_to(sb, streamlit_server, "Metrics")
    click_primary_action(sb, "Create Metric")

    sb.wait_for_element_visible('input[placeholder="Metric Name"]', timeout=20)
    sb.type('input[placeholder="Metric Name"]', "Invalid Metric")

    set_code_editor_value(sb, "credit_score >")

    click_primary_action(sb, "Verify")
    sb.wait_for_element_visible('[data-testid="stAlert"]', timeout=20)


@pytest.mark.e2e
@pytest.mark.regression
def test_metric_format_options(sb, streamlit_server, test_data_paths):
    """Test configuring metric format options."""
    ensure_data_loaded(sb, streamlit_server, test_data_paths["train"])
    navigate_to(sb, streamlit_server, "Metrics")
    click_primary_action(sb, "Create Metric")

    sb.wait_for_element_visible('input[placeholder="Metric Name"]', timeout=20)
    sb.type('input[placeholder="Metric Name"]', "Formatted Metric")
    set_code_editor_value(sb, "credit_score.size")

    # Configure format options
    sb.click('//label[contains(., "Is Cumulative")]')
    sb.click('//label[contains(., "Use Thousand Separator")]')
    sb.click('//label[contains(., "Is Percentage")]')

    # Change decimal places
    decimal_input = sb.find_element('input[type="number"]')
    decimal_input.clear()
    decimal_input.send_keys("4")

    click_primary_action(sb, "Verify")
    click_primary_action(sb, "Save")

    sb.wait_for_text_visible("Metrics", timeout=20)
    sb.assert_text("Formatted Metric")


@pytest.mark.e2e
@pytest.mark.regression
def test_metric_code_editor_mode(sb, streamlit_server, test_data_paths):
    """Test creating metric using Code Editor mode."""
    ensure_data_loaded(sb, streamlit_server, test_data_paths["train"])
    navigate_to(sb, streamlit_server, "Metrics")
    click_primary_action(sb, "Create Metric")

    # Select Code Editor mode (default)
    sb.wait_for_element_visible('//label[contains(., "Code Editor")]', timeout=15)
    sb.click('//label[contains(., "Code Editor")]')

    sb.wait_for_element_visible('input[placeholder="Metric Name"]', timeout=20)
    sb.type('input[placeholder="Metric Name"]', "Code Editor Metric")
    set_code_editor_value(sb, "credit_score.mean()")

    click_primary_action(sb, "Verify")
    click_primary_action(sb, "Save")

    sb.wait_for_text_visible("Metrics", timeout=20)
    sb.assert_text("Code Editor Metric")


@pytest.mark.e2e
@pytest.mark.regression
def test_metric_edit_and_delete(sb, streamlit_server, test_data_paths):
    """Test editing and deleting a metric."""
    ensure_data_loaded(sb, streamlit_server, test_data_paths["train"])
    navigate_to(sb, streamlit_server, "Metrics")
    click_primary_action(sb, "Create Metric")

    sb.wait_for_element_visible('input[placeholder="Metric Name"]', timeout=20)
    sb.type('input[placeholder="Metric Name"]', "To Edit Metric")
    set_code_editor_value(sb, "credit_score.size")

    click_primary_action(sb, "Verify")
    click_primary_action(sb, "Save")
    sb.wait_for_text_visible("Metrics", timeout=20)

    # Edit the metric - click edit button
    edit_btn = (
        '//button[contains(@key, "edit_btn") and contains(@key, "To Edit Metric")]'
    )
    sb.wait_for_element_clickable(edit_btn, timeout=15)
    sb.click(edit_btn)

    sb.wait_for_element_visible('input[placeholder="Metric Name"]', timeout=20)
    sb.type('input[placeholder="Metric Name"]', "Edited Metric")
    set_code_editor_value(sb, "credit_score.count()")

    click_primary_action(sb, "Verify")
    click_primary_action(sb, "Save")
    sb.wait_for_text_visible("Metrics", timeout=20)
    sb.assert_text("Edited Metric")

    # Delete the metric
    delete_btn = (
        '//button[contains(@key, "delete_btn") and contains(@key, "Edited Metric")]'
    )
    sb.wait_for_element_clickable(delete_btn, timeout=15)
    sb.click(delete_btn)

    # Confirm deletion dialog
    sb.wait_for_element_clickable('//button[contains(., "Delete")]', timeout=10)
    sb.click('//button[contains(., "Delete")]')
    sb.wait_for_text_visible("Metrics", timeout=15)
    sb.assert_element_absent('//*[contains(text(), "Edited Metric")]')
