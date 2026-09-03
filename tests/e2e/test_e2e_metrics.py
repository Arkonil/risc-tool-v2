"""End-to-end tests for Metric feature using SeleniumBase."""

import pytest

from tests.e2e.helpers import (
    click_metric_action,
    click_primary_action,
    confirm_deletion_dialog,
    ensure_data_loaded,
    import_data_source,
    navigate_to,
    navigate_to_sidebar,
    select_multiselect_options,
    set_code_editor_value,
    set_text_input_value,
    setup_browser,
)


@pytest.mark.e2e
@pytest.mark.smoke
def test_metric_empty_state_redirect(sb, streamlit_server):
    """Test empty state prompt and redirection to Data Importer page."""
    setup_browser(sb, streamlit_server)
    navigate_to(sb, streamlit_server, "Metrics")

    sb.wait_for_text_visible("No Data Loaded", timeout=15)
    load_btn = '//button[contains(., "Load Data")]'
    sb.wait_for_element_clickable(load_btn, timeout=15)
    sb.click(load_btn)

    sb.wait_for_text_visible("Data Importer", timeout=15)
    sb.assert_text("Select Data Sources")


@pytest.mark.e2e
@pytest.mark.smoke
def test_metric_template_builder_flow(sb, streamlit_server, test_data_paths):
    """Test creating, configuring, and verifying a metric with Template Builder."""
    setup_browser(sb, streamlit_server)
    ensure_data_loaded(sb, streamlit_server, test_data_paths["e2e_train"])

    navigate_to_sidebar(sb, streamlit_server, "Metrics")
    click_primary_action(sb, "Create Metric")

    set_text_input_value(
        sb, 'input[placeholder="Metric Name"]', "Account Volume Metric"
    )

    # Select data source
    select_multiselect_options(
        sb, '[class*="st-key-select_data_source_ids"]', ["Train Data"]
    )

    # Switch to Template Builder mode
    template_radio = '//label[contains(., "Template Builder")]'
    sb.wait_for_element_clickable(template_radio, timeout=10)
    sb.click(template_radio)

    # Configure format options
    use_thousand_sep = '//label[contains(., "Use Thousand Separator")]'
    sb.wait_for_element_clickable(use_thousand_sep, timeout=10)
    sb.click(use_thousand_sep)

    click_primary_action(sb, "Verify")
    click_primary_action(sb, "Save")

    sb.wait_for_text_visible("Metrics", timeout=20)
    sb.assert_text("Account Volume Metric")


@pytest.mark.e2e
@pytest.mark.regression
def test_metric_code_editor_flow(sb, streamlit_server, test_data_paths):
    """Test creating a metric using Code Editor mode."""
    setup_browser(sb, streamlit_server)
    ensure_data_loaded(sb, streamlit_server, test_data_paths["e2e_train"])

    navigate_to_sidebar(sb, streamlit_server, "Metrics")
    click_primary_action(sb, "Create Metric")

    set_text_input_value(sb, 'input[placeholder="Metric Name"]', "Mean Credit Score")

    # Select data source
    select_multiselect_options(
        sb, '[class*="st-key-select_data_source_ids"]', ["Train Data"]
    )

    set_code_editor_value(sb, "credit_score.mean()")

    click_primary_action(sb, "Verify")
    click_primary_action(sb, "Save")

    sb.wait_for_text_visible("Metrics", timeout=20)
    sb.assert_text("Mean Credit Score")


@pytest.mark.e2e
@pytest.mark.regression
def test_metric_invalid_expression_shows_error(sb, streamlit_server, test_data_paths):
    """Test that an invalid metric expression displays an error and disables saving."""
    setup_browser(sb, streamlit_server)
    ensure_data_loaded(sb, streamlit_server, test_data_paths["e2e_train"])

    navigate_to_sidebar(sb, streamlit_server, "Metrics")
    click_primary_action(sb, "Create Metric")

    set_text_input_value(sb, 'input[placeholder="Metric Name"]', "Invalid Metric")

    # Select data source
    select_multiselect_options(
        sb, '[class*="st-key-select_data_source_ids"]', ["Train Data"]
    )

    set_code_editor_value(sb, "credit_score >")

    click_primary_action(sb, "Verify")
    sb.wait_for_element_visible('[data-testid="stAlert"]', timeout=15)
    sb.assert_element_visible('//button[contains(., "Save") and @disabled]')


@pytest.mark.e2e
@pytest.mark.regression
def test_metric_edit_and_delete(sb, streamlit_server, test_data_paths):
    """Test editing an existing metric and deleting it via confirmation dialog."""
    setup_browser(sb, streamlit_server)
    ensure_data_loaded(sb, streamlit_server, test_data_paths["e2e_train"])

    navigate_to_sidebar(sb, streamlit_server, "Metrics")
    click_primary_action(sb, "Create Metric")

    set_text_input_value(sb, 'input[placeholder="Metric Name"]', "To Edit Metric")
    select_multiselect_options(
        sb, '[class*="st-key-select_data_source_ids"]', ["Train Data"]
    )
    set_code_editor_value(sb, "credit_score.mean()")

    click_primary_action(sb, "Verify")
    click_primary_action(sb, "Save")
    sb.wait_for_text_visible("Metrics", timeout=20)
    sb.assert_text("To Edit Metric")

    # Edit the metric
    click_metric_action(sb, "To Edit Metric", "edit")
    set_text_input_value(sb, 'input[placeholder="Metric Name"]', "Edited Metric")
    set_code_editor_value(sb, "credit_score.count()")

    click_primary_action(sb, "Verify")
    click_primary_action(sb, "Save")

    sb.wait_for_text_visible("Metrics", timeout=20)
    sb.assert_text("Edited Metric")

    # Delete the metric
    click_metric_action(sb, "Edited Metric", "delete")
    confirm_deletion_dialog(sb)

    sb.wait_for_text_visible("Metrics", timeout=15)
    sb.wait_for_text_not_visible("Edited Metric", timeout=10)


@pytest.mark.e2e
@pytest.mark.smoke
def test_metric_full_lifecycle(sb, streamlit_server, test_data_paths):
    """Test full Metric user lifecycle in a single consolidated session:

    1. Empty state verification & 'Load Data' prompt redirection to Data Importer
    2. Data source import in Data Importer
    3. Return to Metrics page via sidebar
    4. Empty metric placeholder ('No Metrics Created Yet') verification
    5. Metric creation via Template Builder, format configuration, verification, and save
    6. Verify created metric appears in Metric List
    7. Metric duplication via copy button
    8. Metric editing via edit button
    9. Metric deletion via confirmation dialog
    """
    # 1. Empty state & redirect
    setup_browser(sb, streamlit_server)
    navigate_to(sb, streamlit_server, "Metrics")
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

    # 3. Return to Metrics
    navigate_to_sidebar(sb, streamlit_server, "Metrics")
    sb.wait_for_text_visible("No Metrics Created Yet", timeout=20)

    # 4. Create first metric via Template Builder
    click_primary_action(sb, "Create Metric")
    set_text_input_value(sb, 'input[placeholder="Metric Name"]', "Lifecycle Metric")
    select_multiselect_options(
        sb, '[class*="st-key-select_data_source_ids"]', ["Train Data"]
    )

    template_radio = '//label[contains(., "Template Builder")]'
    sb.wait_for_element_clickable(template_radio, timeout=10)
    sb.click(template_radio)

    click_primary_action(sb, "Verify")
    click_primary_action(sb, "Save")

    sb.wait_for_text_visible("Metrics", timeout=20)
    sb.assert_text("Lifecycle Metric")

    # 5. Duplicate metric
    click_metric_action(sb, "Lifecycle Metric", "content_copy")
    sb.wait_for_text_visible("Lifecycle Metric - copy(1)", timeout=15)

    # 6. Delete duplicate
    click_metric_action(sb, "Lifecycle Metric - copy(1)", "delete")
    confirm_deletion_dialog(sb)
    sb.wait_for_text_not_visible("Lifecycle Metric - copy(1)", timeout=10)

    # 7. Edit original metric
    click_metric_action(sb, "Lifecycle Metric", "edit")
    set_text_input_value(sb, 'input[placeholder="Metric Name"]', "Updated Metric")

    # Switch back to Code Editor
    code_radio = '//label[contains(., "Code Editor")]'
    sb.wait_for_element_clickable(code_radio, timeout=10)
    sb.click(code_radio)

    set_code_editor_value(sb, "credit_score.max()")

    click_primary_action(sb, "Verify")
    click_primary_action(sb, "Save")

    sb.wait_for_text_visible("Metrics", timeout=20)
    sb.assert_text("Updated Metric")

    # 8. Delete metric to clean state
    click_metric_action(sb, "Updated Metric", "delete")
    confirm_deletion_dialog(sb)
    sb.wait_for_text_visible("No Metrics Created Yet", timeout=15)
