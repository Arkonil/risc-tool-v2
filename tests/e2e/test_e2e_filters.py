"""End-to-end tests for Filter feature using SeleniumBase."""

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
    reason="Filter E2E tests disabled temporarily; need fixing"
)


@pytest.mark.e2e
@pytest.mark.smoke
def test_filter_creation_flow(sb, streamlit_server, test_data_paths):
    """Test creating, verifying, and viewing a filter."""
    ensure_data_loaded(sb, streamlit_server, test_data_paths["train"])

    navigate_to(sb, streamlit_server, "Filters")
    click_primary_action(sb, "Create Filter")

    sb.wait_for_element_visible('input[placeholder="Filter Name"]', timeout=20)
    sb.type('input[placeholder="Filter Name"]', "High Score Filter")

    set_code_editor_value(sb, "credit_score > 700")

    click_primary_action(sb, "Verify")
    click_primary_action(sb, "Save")

    sb.wait_for_text_visible("Filters", timeout=20)
    sb.assert_text("High Score Filter")


@pytest.mark.e2e
@pytest.mark.regression
def test_filter_invalid_expression_shows_error(sb, streamlit_server, test_data_paths):
    """Test invalid filter expression displays an error."""
    ensure_data_loaded(sb, streamlit_server, test_data_paths["train"])
    navigate_to(sb, streamlit_server, "Filters")
    click_primary_action(sb, "Create Filter")

    sb.wait_for_element_visible('input[placeholder="Filter Name"]', timeout=20)
    sb.type('input[placeholder="Filter Name"]', "Invalid Filter")
    set_code_editor_value(sb, "credit_score >")

    click_primary_action(sb, "Verify")
    sb.wait_for_element_visible('[data-testid="stAlert"]', timeout=20)


@pytest.mark.e2e
@pytest.mark.regression
def test_filter_complex_expression(sb, streamlit_server, test_data_paths):
    """Test creating a filter with complex expression."""
    ensure_data_loaded(sb, streamlit_server, test_data_paths["train"])
    navigate_to(sb, streamlit_server, "Filters")
    click_primary_action(sb, "Create Filter")

    sb.wait_for_element_visible('input[placeholder="Filter Name"]', timeout=20)
    sb.type('input[placeholder="Filter Name"]', "Complex Filter")
    set_code_editor_value(sb, "credit_score > 700 and income > 50000")

    click_primary_action(sb, "Verify")
    click_primary_action(sb, "Save")

    sb.wait_for_text_visible("Filters", timeout=20)
    sb.assert_text("Complex Filter")


@pytest.mark.e2e
@pytest.mark.regression
def test_filter_edit_and_delete(sb, streamlit_server, test_data_paths):
    """Test editing and deleting a filter."""
    ensure_data_loaded(sb, streamlit_server, test_data_paths["train"])
    navigate_to(sb, streamlit_server, "Filters")
    click_primary_action(sb, "Create Filter")

    sb.wait_for_element_visible('input[placeholder="Filter Name"]', timeout=20)
    sb.type('input[placeholder="Filter Name"]', "To Edit Filter")
    set_code_editor_value(sb, "credit_score > 650")

    click_primary_action(sb, "Verify")
    click_primary_action(sb, "Save")
    sb.wait_for_text_visible("Filters", timeout=20)

    # Edit the filter - click edit button
    edit_btn = (
        '//button[contains(@key, "edit_btn") and contains(@key, "To Edit Filter")]'
    )
    sb.wait_for_element_clickable(edit_btn, timeout=15)
    sb.click(edit_btn)

    sb.wait_for_element_visible('input[placeholder="Filter Name"]', timeout=20)
    sb.type('input[placeholder="Filter Name"]', "Edited Filter")
    set_code_editor_value(sb, "credit_score > 700")

    click_primary_action(sb, "Verify")
    click_primary_action(sb, "Save")
    sb.wait_for_text_visible("Filters", timeout=20)
    sb.assert_text("Edited Filter")

    # Delete the filter
    delete_btn = (
        '//button[contains(@key, "delete_btn") and contains(@key, "Edited Filter")]'
    )
    sb.wait_for_element_clickable(delete_btn, timeout=15)
    sb.click(delete_btn)

    # Confirm deletion dialog
    sb.wait_for_element_clickable('//button[contains(., "Delete")]', timeout=10)
    sb.click('//button[contains(., "Delete")]')
    sb.wait_for_text_visible("Filters", timeout=15)
    sb.assert_element_absent('//*[contains(text(), "Edited Filter")]')
