"""End-to-end tests for Data Explorer feature using SeleniumBase."""

import pytest

from tests.e2e.helpers import (
    click_primary_action,
    create_outlier_rule,
    delete_outlier_rule,
    import_data_source,
    navigate_to,
    navigate_to_sidebar,
    select_dropdown_option,
    select_multiselect_options,
    setup_browser,
    switch_preview_tab,
)


def _load_data_via_prompt(sb, streamlit_server, train_path: str):
    """Navigate to Data Explorer, use 'Load Data' prompt to import, and return to Explorer."""
    navigate_to(sb, streamlit_server, "Data Explorer")
    load_btn = '//button[contains(., "Load Data")]'
    sb.wait_for_element_clickable(load_btn, timeout=15)
    sb.click(load_btn)

    # Now on Data Importer page, import data source
    import_data_source(
        sb,
        streamlit_server,
        filepath=train_path,
        label="Train Data",
        navigate=False,
    )

    # Navigate back to Data Explorer using sidebar client-side routing
    navigate_to_sidebar(sb, streamlit_server, "Data Explorer")
    sb.wait_for_element_visible('[data-testid="stTabs"]', timeout=30)


@pytest.mark.e2e
@pytest.mark.smoke
def test_data_explorer_empty_state_redirect(sb, streamlit_server):
    """Test empty state prompt and redirection to Data Importer page."""
    setup_browser(sb, streamlit_server)
    navigate_to(sb, streamlit_server, "Data Explorer")

    sb.wait_for_text_visible("No Data Loaded", timeout=15)
    sb.assert_element_not_visible('[data-testid="stTabs"]')

    load_btn = '//button[contains(., "Load Data")]'
    sb.wait_for_element_clickable(load_btn, timeout=15)
    sb.click(load_btn)

    # Redirection via st.switch_page brings user to Data Importer
    sb.wait_for_text_visible("Data Importer", timeout=15)
    sb.assert_text("Select Data Sources")


@pytest.mark.e2e
@pytest.mark.regression
def test_data_explorer_iv_chart_renders(sb, streamlit_server, test_data_paths):
    """Test IV analysis configuration and Altair chart rendering."""
    setup_browser(sb, streamlit_server)
    _load_data_via_prompt(sb, streamlit_server, test_data_paths["e2e_train"])

    sb.wait_for_element_visible('[data-testid="stTabs"]', timeout=15)
    sb.assert_text("IV Analysis")

    # Initial warning is shown before target/inputs are configured
    sb.wait_for_text_visible(
        "Please select a target variable and at least one input variable",
        timeout=15,
    )

    # Select Data Source in the IV controls
    source_multiselect = '//label[contains(., "Select Data Sources")]/ancestor::div[@data-testid="stMultiSelect"]'
    select_multiselect_options(sb, source_multiselect, ["Train Data"])

    # Select Target Variable (e.g. credit_default_flag)
    target_selector = '//label[contains(., "Target Variable")]/ancestor::div[@data-testid="stSelectbox"]'
    select_dropdown_option(sb, target_selector, "credit_default_flag")

    # Select Input Variable (e.g. credit_score)
    var_multiselect = (
        '//label[contains(., "Variables")]/ancestor::div[@data-testid="stMultiSelect"]'
    )
    select_multiselect_options(sb, var_multiselect, ["credit_score"])

    # Save IV Config
    click_primary_action(sb, "Save Config")

    # Verify chart renders
    chart_selector = (
        '[data-testid="stVegaLiteChart"], [data-testid="stArrowVegaLiteChart"]'
    )
    sb.wait_for_element_visible(chart_selector, timeout=25)


@pytest.mark.e2e
@pytest.mark.regression
def test_data_explorer_outlier_rules(sb, streamlit_server, test_data_paths):
    """Test Outlier Rules distribution toggle, rule creation, and deletion."""
    setup_browser(sb, streamlit_server)
    _load_data_via_prompt(sb, streamlit_server, test_data_paths["e2e_train"])

    switch_preview_tab(sb, "Outlier Rules")
    sb.wait_for_text_visible("Comparison Operation", timeout=15)

    # By default, quantile distribution table is displayed
    sb.wait_for_element_visible('[data-testid="stDataFrame"]', timeout=15)

    # Toggle sidebar checkbox to show boxplot chart
    chart_checkbox = '//section[@data-testid="stSidebar"]//label[contains(., "Show Distribution as Chart")]'
    sb.wait_for_element_clickable(chart_checkbox, timeout=10)
    sb.click(chart_checkbox)

    # Boxplot Altair chart renders
    chart_selector = (
        '[data-testid="stVegaLiteChart"], [data-testid="stArrowVegaLiteChart"]'
    )
    sb.wait_for_element_visible(chart_selector, timeout=20)

    # Toggle back to table
    sb.click(chart_checkbox)
    sb.wait_for_element_visible('[data-testid="stDataFrame"]', timeout=15)

    # Create outlier rule on credit_score > 95th Percentile
    create_outlier_rule(
        sb, variable="credit_score", op=">", base_perc="95th Percentile"
    )

    # Verify rule is saved and metric is displayed
    sb.wait_for_element_visible('//button[contains(., "Rule Saved")]', timeout=15)
    sb.wait_for_element_visible('[data-testid="stMetric"]', timeout=15)
    sb.wait_for_text_visible("Total Outlier Count", timeout=15)

    # Delete outlier rule
    delete_outlier_rule(sb)
    sb.wait_for_text_not_visible("Total Outlier Count", timeout=15)


@pytest.mark.e2e
@pytest.mark.smoke
def test_data_explorer_full_lifecycle(sb, streamlit_server, test_data_paths):
    """Test complete Data Explorer user lifecycle in a single consolidated session:

    1. Empty state verification & 'Load Data' prompt redirection to Data Importer
    2. Data source import in Data Importer
    3. Return to Data Explorer and verify tabs
    4. IV Analysis warning banner verification
    5. IV Analysis configuration (source, target, inputs) and chart rendering
    6. Outlier Rules tab navigation
    7. Quantile table vs boxplot distribution toggle
    8. Outlier rule creation & metric verification
    9. Outlier rule deletion and clean state return
    """
    # 1. Empty state & redirect
    setup_browser(sb, streamlit_server)
    navigate_to(sb, streamlit_server, "Data Explorer")
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

    # 3. Return to Data Explorer
    navigate_to_sidebar(sb, streamlit_server, "Data Explorer")
    sb.wait_for_element_visible('[data-testid="stTabs"]', timeout=30)
    sb.assert_text("Data Explorer", "h1")
    sb.assert_text("IV Analysis")
    sb.assert_text("Outlier Rules")

    # 4. IV Analysis initial state
    sb.wait_for_text_visible(
        "Please select a target variable and at least one input variable",
        timeout=15,
    )

    # 5. IV Analysis configuration
    source_multiselect = '//label[contains(., "Select Data Sources")]/ancestor::div[@data-testid="stMultiSelect"]'
    select_multiselect_options(sb, source_multiselect, ["Train Data"])

    target_selector = '//label[contains(., "Target Variable")]/ancestor::div[@data-testid="stSelectbox"]'
    select_dropdown_option(sb, target_selector, "credit_default_flag")

    var_multiselect = (
        '//label[contains(., "Variables")]/ancestor::div[@data-testid="stMultiSelect"]'
    )
    select_multiselect_options(sb, var_multiselect, ["credit_score"])

    click_primary_action(sb, "Save Config")

    chart_selector = (
        '[data-testid="stVegaLiteChart"], [data-testid="stArrowVegaLiteChart"]'
    )
    sb.wait_for_element_visible(chart_selector, timeout=25)

    # 6. Outlier Rules tab navigation
    switch_preview_tab(sb, "Outlier Rules")
    sb.wait_for_text_visible("Comparison Operation", timeout=15)

    # 7. Distribution toggle (table -> chart -> table)
    sb.wait_for_element_visible('[data-testid="stDataFrame"]', timeout=15)
    chart_checkbox = '//section[@data-testid="stSidebar"]//label[contains(., "Show Distribution as Chart")]'
    sb.wait_for_element_clickable(chart_checkbox, timeout=10)
    sb.click(chart_checkbox)
    sb.wait_for_element_visible(chart_selector, timeout=20)
    sb.click(chart_checkbox)
    sb.wait_for_element_visible('[data-testid="stDataFrame"]', timeout=15)

    # 8. Create outlier rule
    create_outlier_rule(
        sb, variable="credit_score", op=">", base_perc="95th Percentile"
    )
    sb.wait_for_element_visible('//button[contains(., "Rule Saved")]', timeout=15)
    sb.wait_for_element_visible('[data-testid="stMetric"]', timeout=15)
    sb.wait_for_text_visible("Total Outlier Count", timeout=15)

    # 9. Delete outlier rule
    delete_outlier_rule(sb)
    sb.wait_for_text_not_visible("Total Outlier Count", timeout=15)
