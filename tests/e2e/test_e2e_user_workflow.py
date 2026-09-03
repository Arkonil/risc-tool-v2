"""End-to-end tests for complete cross-page user workflow using SeleniumBase.

Tests mimic real user behavior: sequential sidebar navigation, form inputs,
component verification, and data persistence across all 4 feature pages:
Data Importer -> Data Explorer -> Filters -> Metrics.
"""

import pytest

from tests.e2e.helpers import (
    click_filter_action,
    click_metric_action,
    click_primary_action,
    confirm_deletion_dialog,
    create_outlier_rule,
    delete_outlier_rule,
    import_data_source,
    navigate_to_sidebar,
    select_multiselect_options,
    set_code_editor_value,
    set_text_input_value,
    setup_browser,
    switch_preview_tab,
)


@pytest.mark.e2e
@pytest.mark.smoke
def test_complete_user_workflow(sb, streamlit_server, test_data_paths):
    """Test complete continuous user workflow across all 4 core pages in one session."""

    # ============================================================
    # STEP 1: DATA IMPORTER - Start at home page & import data
    # ============================================================
    setup_browser(sb, streamlit_server)
    sb.wait_for_element_visible("h1", timeout=20)
    sb.assert_text("Data Importer", "h1")

    # Import primary dataset
    import_data_source(
        sb,
        streamlit_server,
        filepath=test_data_paths["e2e_train"],
        label="Train Data",
        navigate=False,
    )

    # Verify preview renders
    sb.wait_for_element_visible('[data-testid="stDataFrame"]', timeout=20)
    sb.assert_text("Train Data")

    # ============================================================
    # STEP 2: DATA EXPLORER - Navigate via sidebar & Outlier rules
    # ============================================================
    navigate_to_sidebar(sb, streamlit_server, "Data Explorer")
    sb.wait_for_element_visible('[data-testid="stTabs"]', timeout=20)
    sb.assert_text("IV Analysis")
    sb.assert_text("Outlier Rules")

    # Switch to Outlier Rules tab
    switch_preview_tab(sb, "Outlier Rules")
    sb.wait_for_text_visible("Comparison Operation", timeout=15)

    # Create an outlier rule
    create_outlier_rule(
        sb, variable="credit_score", op=">", base_perc="95th Percentile"
    )
    sb.wait_for_element_visible('//button[contains(., "Rule Saved")]', timeout=15)
    sb.wait_for_text_visible("Total Outlier Count", timeout=15)

    # Delete the outlier rule
    delete_outlier_rule(sb)
    sb.wait_for_text_not_visible("Total Outlier Count", timeout=15)

    # ============================================================
    # STEP 3: FILTERS - Navigate via sidebar & CRUD
    # ============================================================
    navigate_to_sidebar(sb, streamlit_server, "Filters")
    sb.wait_for_text_visible("No Filters Created Yet", timeout=20)

    # Create Filter
    click_primary_action(sb, "Create Filter")
    set_text_input_value(sb, 'input[placeholder="Filter Name"]', "High Credit Score")
    set_code_editor_value(sb, "credit_score > 700")

    click_primary_action(sb, "Verify")
    chart_selector = (
        '[data-testid="stVegaLiteChart"], [data-testid="stArrowVegaLiteChart"]'
    )
    sb.wait_for_element_visible(chart_selector, timeout=20)

    click_primary_action(sb, "Save")
    sb.wait_for_text_visible("Filters", timeout=20)
    sb.assert_text("High Credit Score")

    # Edit Filter
    click_filter_action(sb, "High Credit Score", "edit")
    set_text_input_value(
        sb, 'input[placeholder="Filter Name"]', "High Credit Score Edited"
    )
    set_code_editor_value(sb, "credit_score >= 750")

    click_primary_action(sb, "Verify")
    click_primary_action(sb, "Save")
    sb.wait_for_text_visible("Filters", timeout=20)
    sb.assert_text("High Credit Score Edited")

    # Delete Filter
    click_filter_action(sb, "High Credit Score Edited", "delete")
    confirm_deletion_dialog(sb)
    sb.wait_for_text_visible("No Filters Created Yet", timeout=15)

    # ============================================================
    # STEP 4: METRICS - Navigate via sidebar & CRUD
    # ============================================================
    navigate_to_sidebar(sb, streamlit_server, "Metrics")
    sb.wait_for_text_visible("No Metrics Created Yet", timeout=20)

    # Create Metric via Template Builder
    click_primary_action(sb, "Create Metric")
    set_text_input_value(sb, 'input[placeholder="Metric Name"]', "Total Volume")
    select_multiselect_options(
        sb, '[class*="st-key-select_data_source_ids"]', ["Train Data"]
    )

    template_radio = '//label[contains(., "Template Builder")]'
    sb.wait_for_element_clickable(template_radio, timeout=10)
    sb.click(template_radio)

    click_primary_action(sb, "Verify")
    click_primary_action(sb, "Save")
    sb.wait_for_text_visible("Metrics", timeout=20)
    sb.assert_text("Total Volume")

    # Edit Metric
    click_metric_action(sb, "Total Volume", "edit")
    set_text_input_value(sb, 'input[placeholder="Metric Name"]', "Total Volume Edited")

    code_radio = '//label[contains(., "Code Editor")]'
    sb.wait_for_element_clickable(code_radio, timeout=10)
    sb.click(code_radio)
    set_code_editor_value(sb, "credit_score.size")

    click_primary_action(sb, "Verify")
    click_primary_action(sb, "Save")
    sb.wait_for_text_visible("Metrics", timeout=20)
    sb.assert_text("Total Volume Edited")

    # Delete Metric
    click_metric_action(sb, "Total Volume Edited", "delete")
    confirm_deletion_dialog(sb)
    sb.wait_for_text_visible("No Metrics Created Yet", timeout=15)
