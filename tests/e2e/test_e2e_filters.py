"""End-to-end tests for Filter feature using SeleniumBase."""

import pytest

from tests.e2e.helpers import (
    click_filter_action,
    click_primary_action,
    confirm_deletion_dialog,
    ensure_data_loaded,
    import_data_source,
    navigate_to,
    navigate_to_sidebar,
    set_code_editor_value,
    set_text_input_value,
    setup_browser,
)


@pytest.mark.e2e
@pytest.mark.smoke
def test_filter_empty_state_redirect(sb, streamlit_server):
    """Test empty state prompt and redirection to Data Importer page."""
    setup_browser(sb, streamlit_server)
    navigate_to(sb, streamlit_server, "Filters")

    sb.wait_for_text_visible("No Data Loaded", timeout=15)
    load_btn = '//button[contains(., "Load Data")]'
    sb.wait_for_element_clickable(load_btn, timeout=15)
    sb.click(load_btn)

    sb.wait_for_text_visible("Data Importer", timeout=15)
    sb.assert_text("Select Data Sources")


@pytest.mark.e2e
@pytest.mark.smoke
def test_filter_creation_flow(sb, streamlit_server, test_data_paths):
    """Test creating, verifying, and saving a filter with distribution pie chart."""
    setup_browser(sb, streamlit_server)
    ensure_data_loaded(sb, streamlit_server, test_data_paths["e2e_train"])

    navigate_to_sidebar(sb, streamlit_server, "Filters")
    click_primary_action(sb, "Create Filter")

    set_text_input_value(sb, 'input[placeholder="Filter Name"]', "High Score Filter")
    set_code_editor_value(sb, "credit_score > 700")

    click_primary_action(sb, "Verify")

    # Distribution pie chart renders on successful verification
    chart_selector = (
        '[data-testid="stVegaLiteChart"], [data-testid="stArrowVegaLiteChart"]'
    )
    sb.wait_for_element_visible(chart_selector, timeout=20)

    click_primary_action(sb, "Save")

    sb.wait_for_text_visible("Filters", timeout=20)
    sb.assert_text("High Score Filter")


@pytest.mark.e2e
@pytest.mark.regression
def test_filter_invalid_expression_shows_error(sb, streamlit_server, test_data_paths):
    """Test that an invalid filter expression displays an error and disables saving."""
    setup_browser(sb, streamlit_server)
    ensure_data_loaded(sb, streamlit_server, test_data_paths["e2e_train"])

    navigate_to_sidebar(sb, streamlit_server, "Filters")
    click_primary_action(sb, "Create Filter")

    set_text_input_value(sb, 'input[placeholder="Filter Name"]', "Invalid Filter")
    set_code_editor_value(sb, "credit_score >")

    click_primary_action(sb, "Verify")
    sb.wait_for_element_visible('[data-testid="stAlert"]', timeout=15)
    sb.assert_element_visible('//button[contains(., "Save") and @disabled]')


@pytest.mark.e2e
@pytest.mark.regression
def test_filter_edit_and_delete(sb, streamlit_server, test_data_paths):
    """Test editing an existing filter and deleting it via confirmation dialog."""
    setup_browser(sb, streamlit_server)
    ensure_data_loaded(sb, streamlit_server, test_data_paths["e2e_train"])

    navigate_to_sidebar(sb, streamlit_server, "Filters")
    click_primary_action(sb, "Create Filter")

    set_text_input_value(sb, 'input[placeholder="Filter Name"]', "To Edit Filter")
    set_code_editor_value(sb, "credit_score > 650")

    click_primary_action(sb, "Verify")
    click_primary_action(sb, "Save")
    sb.wait_for_text_visible("Filters", timeout=20)
    sb.assert_text("To Edit Filter")

    # Edit the filter
    click_filter_action(sb, "To Edit Filter", "edit")
    set_text_input_value(sb, 'input[placeholder="Filter Name"]', "Edited Filter")
    set_code_editor_value(sb, "credit_score > 680")

    click_primary_action(sb, "Verify")
    click_primary_action(sb, "Save")

    sb.wait_for_text_visible("Filters", timeout=20)
    sb.assert_text("Edited Filter")

    # Delete the filter
    click_filter_action(sb, "Edited Filter", "delete")
    confirm_deletion_dialog(sb)
    sb.wait_for_text_visible("Filters", timeout=15)
    sb.wait_for_text_not_visible("Edited Filter", timeout=10)


@pytest.mark.e2e
@pytest.mark.smoke
def test_filter_full_lifecycle(sb, streamlit_server, test_data_paths):
    """Test full Filter user lifecycle in a single consolidated session:

    1. Empty state verification & 'Load Data' prompt redirection to Data Importer
    2. Data source import in Data Importer
    3. Return to Filters page via sidebar
    4. Empty filter placeholder ('No Filters Created Yet') verification
    5. Filter creation: name, query expression, verification with Altair pie chart, and save
    6. Verify created filter appears in Filter List
    7. Filter duplication via copy button
    8. Filter editing via edit button
    9. Filter deletion via confirmation dialog
    """
    # 1. Empty state & redirect
    setup_browser(sb, streamlit_server)
    navigate_to(sb, streamlit_server, "Filters")
    sb.wait_for_text_visible("No Data Loaded", timeout=15)

    load_btn = '//button[contains(., "Load Data")]'
    sb.wait_for_element_clickable(load_btn, timeout=15)
    sb.click(load_btn)

    # 2. Data import in Data Importer
    sb.wait_for_text_visible("Data Importer", timeout=15)
    import_data_source(
        sb,
        streamlit_server,
        filepath=test_data_paths["e2e_train"],
        label="Train Data",
        navigate=False,
    )

    # 3. Return to Filters
    navigate_to_sidebar(sb, streamlit_server, "Filters")
    sb.wait_for_text_visible("No Filters Created Yet", timeout=20)

    # 4. Create first filter
    click_primary_action(sb, "Create Filter")
    set_text_input_value(sb, 'input[placeholder="Filter Name"]', "Lifecycle Filter")
    set_code_editor_value(sb, "income > 40000 and credit_score > 600")

    click_primary_action(sb, "Verify")
    chart_selector = (
        '[data-testid="stVegaLiteChart"], [data-testid="stArrowVegaLiteChart"]'
    )
    sb.wait_for_element_visible(chart_selector, timeout=20)

    click_primary_action(sb, "Save")
    sb.wait_for_text_visible("Filters", timeout=20)
    sb.assert_text("Lifecycle Filter")

    # 5. Duplicate filter
    click_filter_action(sb, "Lifecycle Filter", "content_copy")
    sb.wait_for_text_visible("Lifecycle Filter - copy(1)", timeout=15)

    # 6. Delete duplicate
    click_filter_action(sb, "Lifecycle Filter - copy(1)", "delete")
    confirm_deletion_dialog(sb)
    sb.wait_for_text_not_visible("Lifecycle Filter - copy(1)", timeout=10)

    # 7. Edit original filter
    click_filter_action(sb, "Lifecycle Filter", "edit")
    set_text_input_value(sb, 'input[placeholder="Filter Name"]', "Updated Filter")
    set_code_editor_value(sb, "income > 50000")

    click_primary_action(sb, "Verify")
    click_primary_action(sb, "Save")
    sb.wait_for_text_visible("Filters", timeout=20)
    sb.assert_text("Updated Filter")

    # 8. Delete filter to clean state
    click_filter_action(sb, "Updated Filter", "delete")
    confirm_deletion_dialog(sb)
    sb.wait_for_text_visible("No Filters Created Yet", timeout=15)
