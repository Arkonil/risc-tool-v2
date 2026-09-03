"""Helper functions for SeleniumBase E2E tests interacting with Streamlit."""

import contextlib
import time

from selenium.webdriver.common.keys import Keys
from seleniumbase import BaseCase

PAGE_PATHS = {
    "Data Importer": "/",
    "Data Explorer": "/data-explorer",
    "Filters": "/filters",
    "Metrics": "/metrics",
}


def setup_browser(sb: BaseCase, server_url: str):
    """Initialize desktop viewport and open application."""
    # sb.set_window_size(1920, 1080)
    sb.open(f"{server_url}{PAGE_PATHS['Data Importer']}")
    sb.wait_for_element_visible('[data-testid="stAppViewContainer"]', timeout=25)
    sb.wait_for_element_visible("h1", timeout=20)
    # Dismiss any initial dialog (e.g., "Add Data Source" modal)
    _dismiss_dialog_if_present(sb)


def navigate_to_sidebar(sb: BaseCase, server_url: str, page_title: str):
    """Navigate to another page via sidebar navigation link (client-side routing)."""
    nav_xpath = (
        f'//section[@data-testid="stSidebar"]//a[contains(., "{page_title}")]'
        f' | //nav//a[contains(., "{page_title}")]'
    )
    sb.wait_for_element_visible(nav_xpath, timeout=15)
    sb.click(nav_xpath)
    sb.wait_for_element_visible('[data-testid="stAppViewContainer"]', timeout=20)

    if page_title == "Data Explorer":
        # Data Explorer shows tabs when data is loaded, or "Load Data" prompt when empty
        sb.wait_for_element_visible(
            '[data-testid="stTabs"], [data-testid="stButton"]', timeout=30
        )
        if sb.is_element_visible('[data-testid="stTabs"]'):
            sb.wait_for_element_visible('[data-testid="stTabs"]', timeout=10)
        else:
            sb.wait_for_text_visible("Load Data", timeout=10)
    elif page_title == "Filters":
        sb.wait_for_element_visible(
            '//h1 | //h3[contains(., "No Filters")] | //button[contains(., "Create Filter")] | //button[contains(., "Load Data")]',
            timeout=20,
        )
    elif page_title == "Metrics":
        sb.wait_for_element_visible(
            '//h1 | //h3[contains(., "No Metrics")] | //button[contains(., "Create Metric")] | //button[contains(., "Load Data")]',
            timeout=20,
        )
    else:
        sb.wait_for_element_visible("h1", timeout=20)
        sb.assert_text(page_title, "h1")

    _dismiss_dialog_if_present(sb)


def navigate_to(sb: BaseCase, server_url: str, page_title: str):
    """Navigate to another page via direct URL (reliable)."""
    path = PAGE_PATHS.get(page_title)
    if not path:
        raise ValueError(
            f"Unknown page title: {page_title}. Known pages: {list(PAGE_PATHS.keys())}"
        )
    sb.open(f"{server_url}{path}")
    sb.wait_for_element_visible('[data-testid="stAppViewContainer"]', timeout=20)
    # Dismiss any dialog that might appear immediately on page load
    _dismiss_dialog_if_present(sb)
    if page_title == "Data Explorer":
        sb.wait_for_element_visible('[data-testid="stTabs"], button, h1', timeout=20)
    elif page_title == "Filters":
        sb.wait_for_element_visible(
            '//h1 | //h3[contains(., "No Filters")] | //button[contains(., "Create Filter")] | //button[contains(., "Load Data")]',
            timeout=20,
        )
    elif page_title == "Metrics":
        sb.wait_for_element_visible(
            '//h1 | //h3[contains(., "No Metrics")] | //button[contains(., "Create Metric")] | //button[contains(., "Load Data")]',
            timeout=20,
        )
    elif page_title == "Simulations":
        try:
            sb.wait_for_element_visible("h1", timeout=10)
        except Exception:  # noqa: BLE001
            sb.wait_for_text_visible("Load Data", timeout=10)
    else:
        sb.wait_for_element_visible("h1", timeout=20)
        sb.assert_text(page_title, "h1")


def _dismiss_dialog_if_present(sb: BaseCase):
    """Dismiss any Streamlit dialog that might be blocking the UI."""
    try:
        # Wait a bit for dialog to potentially appear
        sb.sleep(1)

        # Try multiple times to catch dialogs that appear after initial load
        for _ in range(3):
            if sb.is_element_visible('[data-testid="stDialog"]', timeout=3):
                # Try to click cancel/close button (secondary button)
                try:
                    sb.click('[data-testid="stDialog"] button[kind="secondary"]')
                except Exception:  # noqa: BLE001 - falls back to first button below
                    # If no secondary button, try the first button in dialog
                    try:
                        sb.click('[data-testid="stDialog"] button')
                    except Exception:  # noqa: BLE001, S110
                        pass  # best-effort: no dismissable button found
                sb.wait_for_element_not_visible('[data-testid="stDialog"]', timeout=3)
                sb.sleep(0.5)
            else:
                break

        # Force-remove any remaining dialog via JS
        sb.execute_script("""
            const dialog = document.querySelector('[data-testid="stDialog"]');
            if (dialog) dialog.remove();
            document.body.style.overflow = '';
            document.documentElement.style.overflow = '';
        """)
        sb.sleep(0.5)
    except Exception:  # noqa: BLE001, S110 - dialog dismissal is best-effort
        pass


def set_text_input(sb: BaseCase, selector: str, value: str):
    """Clear and set a text input value."""
    sb.wait_for_element_visible(selector, timeout=20)
    element = sb.find_element(selector)
    element.click()
    element.send_keys(Keys.CONTROL + "a")
    element.send_keys(Keys.BACKSPACE)
    element.send_keys(value)


def import_data_source(
    sb: BaseCase,
    server_url: str,
    filepath: str,
    label: str = "Train Data",
    click_label: str = "Add",
    navigate: bool = True,
    delimiter_name: str | None = None,
):
    """Import a data source from the Data Importer page.

    On the first call ``navigate`` should be left True so the page is loaded.
    For subsequent imports in the same test pass ``navigate=False`` so the
    current (in-memory) Streamlit session is reused instead of a hard reload
    (a hard reload starts a fresh session and loses previously added sources).
    """
    if navigate:
        navigate_to(sb, server_url, "Data Importer")
    elif sb.is_text_visible("Add Data Source"):
        # Existing source(s) are shown; reveal the empty "New Data Source" form.
        _debug_page_state(sb, "pre_add_ds_click")
        sb.click('//button[contains(., "Add Data Source")]')
        _debug_page_state(sb, "post_add_ds_click")
        _dismiss_dialog_if_present(sb)
        _debug_page_state(sb, "post_dismiss")

    # Wait for the form inputs to be visible
    sb.wait_for_element_visible('[data-testid="stTextInput"] input', timeout=20)
    inputs = sb.find_elements('[data-testid="stTextInput"] input')
    if len(inputs) < 2:
        raise AssertionError("Expected at least 2 text inputs for label and file path")

    # The empty "New Data Source" form is rendered after any existing source
    # forms, so its two text inputs (label, file path) are always the last two.
    label_input = inputs[-2]
    # Click, clear, and set label, then force a commit via blur.
    label_input.click()
    label_input.send_keys(Keys.CONTROL + "a")
    label_input.send_keys(Keys.BACKSPACE)
    label_input.send_keys(label)
    _commit_widget_input(sb, label_input)

    path_input = inputs[-1]
    # Click, clear, and set file path, then force a commit via blur.
    path_input.click()
    path_input.send_keys(Keys.CONTROL + "a")
    path_input.send_keys(Keys.BACKSPACE)
    path_input.send_keys(filepath)
    _commit_widget_input(sb, path_input, expected=filepath)

    # Verify the value was set
    actual_value = sb.execute_script("return arguments[0].value;", path_input)
    if actual_value != filepath:
        raise AssertionError(
            f"Path input value not set correctly. Expected: {filepath}, Got: {actual_value}"
        )

    if delimiter_name:
        delimiter_selector = '(//input[contains(@aria-label, "Delimiter")])[last()]/ancestor::div[@data-testid="stSelectbox"]'
        select_dropdown_option(sb, delimiter_selector, delimiter_name)

    # Give Streamlit time to flush the committed widget values to the server
    # before clicking the submit button, so the button's on_click reads the
    # filled values rather than stale/empty ones.
    sb.sleep(1)

    button_selector = f'//button[contains(., "{click_label}")]'
    initial_error = _error_alert_text(sb)
    sb.wait_for_element_clickable(button_selector, timeout=15)
    sb.click(button_selector)
    sb.sleep(2)

    # A successful import closes the empty "Add" form and shows the
    # "Add Data Source" button. A failed import leaves the form up and
    # renders an error alert. Poll for either outcome, ignoring any
    # stale error alert from before the submit button was clicked.
    deadline = time.time() + 180
    iter_n = 0
    while time.time() < deadline:
        if sb.is_element_visible('//button[contains(., "Add Data Source")]'):
            break
        error_text = _error_alert_text(sb)
        if error_text and error_text != initial_error:
            raise AssertionError(f"Import failed with error: {error_text}")
        iter_n += 1
        if iter_n % 15 == 1:
            _debug_page_state(sb, f"wait[{iter_n}]")
        sb.sleep(1)
    else:
        raise AssertionError("Data import did not complete within 180s")

    # Wait for the data preview to fully load
    sb.wait_for_element_visible('[data-testid="stDataFrame"]', timeout=60)
    sb.wait_for_text_visible("Preview Data", timeout=60)
    sb.sleep(1)


def _debug_page_state(sb: BaseCase, tag: str):
    """Live debug dump to detect page reloads / new sessions during the flow."""
    info = sb.execute_script(
        """
        const nav = performance.getEntriesByType('navigation')[0];
        const tabEls = document.querySelectorAll('[role="tab"]');
        return {
            type: nav ? nav.type : 'unknown',
            url: location.href,
            app: !!document.querySelector('[data-testid="stAppViewContainer"]'),
            inputs: document.querySelectorAll('[data-testid="stTextInput"] input').length,
            tabs: Array.from(tabEls).map(t => t.textContent.trim()).join('|'),
            alerts: Array.from(document.querySelectorAll('[data-testid="stAlert"]'))
                        .map(a => (a.textContent || '').trim()).join(' || '),
        };
        """
    )
    print(
        f"[DEBUG:{tag}] nav={info.get('type')} url={info.get('url')} "
        f"app={info.get('app')} inputs={info.get('inputs')} "
        f"tabs=[{info.get('tabs')}] alerts=[{info.get('alerts')}]"
    )


def _commit_widget_input(sb: BaseCase, element, expected: str | None = None):
    """Force a Streamlit widget to commit its DOM value to the server.

    Selenium's ``send_keys`` sets the DOM ``value`` but does not always fire the
    React ``onChange`` that Streamlit listens to, so the server can end up
    reading a stale/empty value (observed as ``Filepath: .``). Dispatch an
    ``input`` and ``change`` event, send an ENTER key, and blur the field so
    Streamlit's React widget flushes the value to the server.
    """
    sb.execute_script(
        """
        const el = arguments[0];
        const setter = Object.getOwnPropertyDescriptor(
            window.HTMLInputElement.prototype, 'value'
        ).set;
        setter.call(el, el.value);
        el.dispatchEvent(new Event('input', { bubbles: true }));
        el.dispatchEvent(new Event('change', { bubbles: true }));
        el.blur();
        """,
        element,
    )
    with contextlib.suppress(Exception):
        element.send_keys(Keys.ENTER)
    if expected is not None:
        deadline = time.time() + 5
        while time.time() < deadline:
            if sb.execute_script("return arguments[0].value;", element) == expected:
                break
            sb.sleep(0.2)
    sb.sleep(0.5)


def _safe_alert_text(el) -> str:
    """Return an alert element's text, tolerating elements that go stale."""
    try:
        return el.text or ""
    except Exception:  # noqa: BLE001 - element may go stale mid-poll
        return ""


def _error_alert_text(sb: BaseCase) -> str:
    """Return the text of an error alert, or empty string if none found.

    Success messages always contain "imported successfully"; any other
    non-empty alert text is treated as an import error.
    """
    for el in sb.find_elements('[data-testid="stAlert"]'):
        text = _safe_alert_text(el)
        if text and "imported successfully" not in text.lower():
            return text
    return ""


def select_dropdown_option(sb: BaseCase, container_selector: str, option_text: str):
    """Open a Streamlit selectbox dropdown and select an option by visible text."""
    sb.wait_for_element_clickable(container_selector, timeout=15)
    container = sb.find_element(container_selector)
    sb.execute_script("arguments[0].scrollIntoView({block: 'center'});", container)
    sb.sleep(0.3)

    open_btn_selector = (
        f"{container_selector}//button[@aria-label='Open']"
        if container_selector.startswith(("//", "("))
        else f"{container_selector} button[aria-label='Open']"
    )
    if sb.is_element_visible(open_btn_selector):
        btn = sb.find_element(open_btn_selector)
        sb.execute_script("arguments[0].focus(); arguments[0].click();", btn)
    else:
        sb.execute_script("arguments[0].focus(); arguments[0].click();", container)

    listbox_selector = (
        '[role="listbox"], [data-testid="stSelectboxVirtualDropdown"], '
        '[class*="stSelectboxVirtualDropdown"]'
    )
    sb.wait_for_element_visible(listbox_selector, timeout=10)
    option_xpath = (
        f'//*[@role="option" and contains(., "{option_text}")]'
        f' | //div[contains(@class, "stSelectboxVirtualDropdown")]//li[contains(., "{option_text}")]'
        f' | //li[contains(., "{option_text}")]'
    )
    sb.wait_for_element_visible(option_xpath, timeout=10)
    opt_el = sb.find_element(option_xpath)
    sb.execute_script("arguments[0].click();", opt_el)
    sb.sleep(0.5)


def set_number_input(sb: BaseCase, selector: str, value: int):
    """Set a Streamlit number input value."""
    sb.wait_for_element_visible(selector, timeout=10)
    element = sb.find_element(selector)
    element.click()
    element.send_keys(Keys.CONTROL + "a")
    element.send_keys(Keys.BACKSPACE)
    element.send_keys(str(value))
    _commit_widget_input(sb, element, expected=str(value))


def get_data_source_uid_by_label(sb: BaseCase, label: str) -> str:
    """Locate the data source UID from its Data Label input container."""
    uid = sb.execute_script(
        """
        const target = arguments[0];
        const inputs = document.querySelectorAll('input[aria-label*="Data Label"]');
        for (const inp of inputs) {
          if (inp.value === target) {
            const container = inp.closest('.stElementContainer');
            const m = container && container.className.match(/file_selector-([0-9a-f-]+)/);
            if (m) return m[1];
          }
        }
        return null;
        """,
        label,
    )
    if not uid:
        raise AssertionError(f"Could not locate data source with label '{label}'")
    return uid


def delete_source_by_label(sb: BaseCase, label: str):
    """Locate the data source card by label and click its primary delete
    button.
    """
    uid = get_data_source_uid_by_label(sb, label)

    delete_selector = (
        f'[class*="st-key-delete_button-file_selector-{uid}"] '
        'button[data-testid="stBaseButton-primary"]'
    )
    sb.wait_for_element_visible(delete_selector, timeout=15)
    del_btn = sb.find_element(delete_selector)
    sb.execute_script("arguments[0].scrollIntoView({block: 'center'});", del_btn)
    sb.sleep(0.5)
    sb.click(delete_selector)


def update_source_label(sb: BaseCase, old_label: str, new_label: str):
    """Update the label input of an existing data source."""
    uid = get_data_source_uid_by_label(sb, old_label)
    label_input_selector = (
        f'[class*="file_selector-{uid}"] input[aria-label*="Data Label"]'
    )
    sb.wait_for_element_visible(label_input_selector, timeout=10)
    label_input = sb.find_element(label_input_selector)
    sb.execute_script("arguments[0].scrollIntoView({block: 'center'});", label_input)
    sb.sleep(0.5)
    sb.execute_script("arguments[0].focus(); arguments[0].click();", label_input)
    label_input.send_keys(Keys.CONTROL + "a")
    label_input.send_keys(Keys.BACKSPACE)
    label_input.send_keys(new_label)
    _commit_widget_input(sb, label_input, expected=new_label)
    sb.sleep(0.5)


def refresh_source_by_label(sb: BaseCase, label: str):
    """Click the refresh button for the data source matching label."""
    uid = get_data_source_uid_by_label(sb, label)
    refresh_selector = (
        f'[class*="st-key-import_button-file_selector-{uid}"] '
        'button[data-testid="stBaseButton-primary"]'
    )
    sb.wait_for_element_visible(refresh_selector, timeout=15)
    ref_btn = sb.find_element(refresh_selector)
    sb.execute_script("arguments[0].scrollIntoView({block: 'center'});", ref_btn)
    sb.sleep(0.5)
    sb.click(refresh_selector)
    sb.sleep(1)


def cancel_empty_data_source(sb: BaseCase):
    """Click the delete button on the empty 'New Data Source' form to dismiss it."""
    empty_del_selector = '[class*="delete_button-file_selector-ffffffff-ffff-ffff-ffff-fffffffffffe"] button'
    sb.wait_for_element_clickable(empty_del_selector, timeout=10)
    sb.click(empty_del_selector)
    sb.sleep(1)


def switch_preview_tab(sb: BaseCase, tab_label: str):
    """Switch to a specific data preview tab by its label."""
    tab_xpath = f'//*[@role="tab" and contains(., "{tab_label}")]'
    sb.wait_for_element_clickable(tab_xpath, timeout=15)
    sb.click(tab_xpath)
    sb.sleep(1)


def ensure_data_loaded(sb: BaseCase, server_url: str, train_path: str):
    """Ensure at least one data source is loaded for cross-page workflows."""
    navigate_to(sb, server_url, "Data Importer")
    # Check if data is already loaded by looking for the preview dataframe
    # and the "Preview Data" text which indicates successful import
    if sb.is_element_visible('[data-testid="stDataFrame"]') and sb.is_text_visible(
        "Preview Data"
    ):
        # Data appears loaded
        return

    # No data loaded, import it
    import_data_source(
        sb, server_url, filepath=train_path, label="Train Data", navigate=False
    )

    # Verify the data is now loaded by checking for the preview
    sb.wait_for_element_visible('[data-testid="stDataFrame"]', timeout=30)
    sb.wait_for_text_visible("Preview Data", timeout=30)

    # Give the server time to propagate session state to all view models
    sb.sleep(3)


def set_code_editor_value(sb: BaseCase, value: str, timeout: int = 25):
    """Set query text in Streamlit code editor (Ace/CodeMirror fallback)."""
    sb.wait_for_element_visible('[data-testid="stAppViewContainer"]', timeout=20)
    iframe_selector = (
        'iframe[title="code_editor.code_editor"], iframe[src*="code_editor"]'
    )
    # Wait explicitly for the code editor iframe to mount in the DOM
    with contextlib.suppress(Exception):
        sb.wait_for_element_present(iframe_selector, timeout=timeout)
        sb.wait_for_element_visible(iframe_selector, timeout=timeout)

    if sb.is_element_visible(iframe_selector):
        sb.switch_to_frame(iframe_selector)
        try:
            # Wait for ace editor element to be visible inside the iframe
            sb.wait_for_element_visible(".ace_editor", timeout=timeout)

            # Poll until Ace or Streamlit component hook is initialized
            for _ in range(20):
                is_ready = sb.execute_script(
                    """
const el = document.querySelector('.ace_editor');
if (!el) return false;
return Boolean((el.env && el.env.editor) || window.ace || (window.Streamlit && window.Streamlit.setComponentValue));
"""
                )
                if is_ready:
                    break
                sb.sleep(0.5)

            sb.execute_script(
                """
const val = arguments[0];
const el = document.querySelector('.ace_editor');
if (el) {
  let editor = null;
  if (el.env && el.env.editor) {
    editor = el.env.editor;
  } else if (window.ace) {
    editor = window.ace.edit(el);
  }
  if (editor) {
    editor.setValue(val, 1);
    editor.clearSelection();
  }
}
if (window.Streamlit && window.Streamlit.setComponentValue) {
  window.Streamlit.setComponentValue({
    id: "e2e_editor_sync",
    type: "change",
    lang: "python",
    text: val,
    selected: "",
    cursor: {row: 0, column: 0}
  });
}
""",
                value,
            )
            if sb.is_element_visible(".ace_text-input"):
                inp = sb.find_element(".ace_text-input")
                inp.click()
                inp.send_keys(" ")
                inp.send_keys(Keys.BACKSPACE)
            sb.sleep(0.5)
        finally:
            sb.switch_to_default_content()
        sb.sleep(1)
        return

    # Fallback if not in iframe
    if sb.is_element_visible(".ace_text-input"):
        editor_input = sb.find_element(".ace_text-input")
        editor_input.click()
        editor_input.send_keys(Keys.CONTROL + "a")
        editor_input.send_keys(Keys.BACKSPACE)
        editor_input.send_keys(value)

    sb.execute_script(
        """
const value = arguments[0];
const aceHost = document.querySelector('.ace_editor');
if (aceHost && aceHost.env && aceHost.env.editor) {
  aceHost.env.editor.setValue(value, -1);
  aceHost.env.editor.clearSelection();
  aceHost.env.editor.session.selection.clearSelection();
  aceHost.env.editor.renderer.updateFull();
}
const cmHost = document.querySelector('.CodeMirror');
if (cmHost && cmHost.CodeMirror) {
  cmHost.CodeMirror.setValue(value);
  cmHost.CodeMirror.refresh();
}
const textareas = document.querySelectorAll('textarea');
for (const el of textareas) {
  if (el.value !== undefined) {
    el.value = value;
    el.dispatchEvent(new Event('input', { bubbles: true }));
    el.dispatchEvent(new Event('change', { bubbles: true }));
  }
}
""",
        value,
    )
    sb.sleep(1)


def set_text_input_value(sb: BaseCase, selector: str, value: str):
    """Clear, set value, and commit a Streamlit text input with Enter."""
    sb.wait_for_element_visible(selector, timeout=15)
    inp = sb.find_element(selector)
    sb.execute_script("arguments[0].scrollIntoView({block: 'center'});", inp)
    sb.sleep(0.2)
    inp.click()
    inp.send_keys(Keys.CONTROL + "a")
    inp.send_keys(Keys.BACKSPACE)
    inp.send_keys(value)
    sb.execute_script(
        "arguments[0].dispatchEvent(new Event('change', {bubbles: true}));", inp
    )
    inp.send_keys(Keys.ENTER)
    sb.sleep(0.5)


def click_primary_action(sb: BaseCase, label: str):
    """Click a button by visible label with a stable wait."""
    selector = f'//button[contains(., "{label}")]'
    sb.wait_for_element_clickable(selector, timeout=15)
    sb.click(selector)


def select_multiselect_options(
    sb: BaseCase, container_selector: str, options: list[str]
):
    """Select multiple options in an st.multiselect widget."""
    sb.wait_for_element_visible(container_selector, timeout=15)
    if "input" in container_selector:
        input_selector = container_selector
    elif container_selector.startswith(("//", "(")):
        input_selector = f"{container_selector}//input"
    else:
        input_selector = f"{container_selector} input"

    for opt in options:
        sb.wait_for_element_visible(input_selector, timeout=10)
        inp = sb.find_element(input_selector)
        sb.execute_script("arguments[0].scrollIntoView({block: 'center'});", inp)
        sb.sleep(0.3)
        sb.execute_script("arguments[0].focus(); arguments[0].click();", inp)
        inp.send_keys(opt)
        sb.sleep(0.5)
        listbox_opt = (
            f'//*[@role="option" and contains(., "{opt}")]'
            f' | //div[contains(@class, "stSelectboxVirtualDropdown")]//li[contains(., "{opt}")]'
            f' | //li[contains(., "{opt}")]'
        )
        if sb.is_element_visible(listbox_opt):
            opt_el = sb.find_element(listbox_opt)
            sb.execute_script("arguments[0].click();", opt_el)
        else:
            inp.send_keys(Keys.ENTER)
        sb.sleep(0.5)

    with contextlib.suppress(Exception):
        inp = sb.find_element(input_selector)
        inp.send_keys(Keys.ESCAPE)
    sb.sleep(0.5)


def create_outlier_rule(
    sb: BaseCase,
    variable: str,
    op: str = ">",
    base_perc: str = "95th Percentile",
    key: str = "new",
):
    """Configure and save an outlier rule via the Outlier Rules form."""
    var_selector = f'[class*="st-key-outlier-variable-name-selector-{key}"]'
    select_dropdown_option(sb, var_selector, variable)

    op_selector = f'[class*="st-key-outlier-comparison-op-selector-{key}"]'
    select_dropdown_option(sb, op_selector, op)

    base_selector = f'[class*="st-key-outlier-comparison-base-selector-{key}"]'
    select_dropdown_option(sb, base_selector, base_perc)

    save_btn_selector = f'[class*="st-key-outlier-save-button-{key}"] button'
    sb.wait_for_element_clickable(save_btn_selector, timeout=10)
    btn = sb.find_element(save_btn_selector)
    sb.execute_script("arguments[0].scrollIntoView({block: 'center'});", btn)
    sb.sleep(0.3)
    sb.click(save_btn_selector)
    sb.sleep(1)


def delete_outlier_rule(sb: BaseCase, rule_key: str | None = None):
    """Delete an outlier rule by rule key or first available delete button."""
    if rule_key:
        del_selector = f'[class*="st-key-outlier-delete-button-{rule_key}"] button'
    else:
        del_selector = '//button[contains(., "Delete Rule")]'
    sb.wait_for_element_clickable(del_selector, timeout=15)
    btn = sb.find_element(del_selector)
    sb.execute_script("arguments[0].scrollIntoView({block: 'center'});", btn)
    sb.sleep(0.3)
    sb.click(del_selector)
    sb.sleep(1)


def click_filter_action(sb: BaseCase, filter_name: str, action: str):
    """Click action button (edit, delete, content_copy) on a filter card."""
    card_xpath = (
        f'//div[contains(@class, "st-key-filter_") and contains(@class, "_container") and .//*[contains(text(), "{filter_name}")]]'
        f'//button[contains(., "{action}") or .//span[contains(text(), "{action}")]]'
    )
    sb.wait_for_element_visible(card_xpath, timeout=15)
    btn = sb.find_element(card_xpath)
    sb.execute_script("arguments[0].scrollIntoView({block: 'center'});", btn)
    sb.sleep(0.3)
    sb.execute_script("arguments[0].focus(); arguments[0].click();", btn)
    sb.sleep(0.5)


def click_metric_action(sb: BaseCase, metric_name: str, action: str):
    """Click action button (edit, delete, content_copy) on a metric card."""
    card_xpath = (
        f'//div[contains(@class, "st-key-metric_") and contains(@class, "_container") and .//*[contains(text(), "{metric_name}")]]'
        f'//button[contains(., "{action}") or .//span[contains(text(), "{action}")]]'
    )
    sb.wait_for_element_visible(card_xpath, timeout=15)
    btn = sb.find_element(card_xpath)
    sb.execute_script("arguments[0].scrollIntoView({block: 'center'});", btn)
    sb.sleep(0.3)
    sb.execute_script("arguments[0].focus(); arguments[0].click();", btn)
    sb.sleep(0.5)


def confirm_deletion_dialog(sb: BaseCase):
    """Confirm a deletion in Streamlit st.dialog."""
    del_btn_xpath = (
        '//*[@role="dialog"]//button[contains(., "Delete")]'
        ' | //*[@data-testid="stDialog"]//button[contains(., "Delete")]'
    )
    sb.wait_for_element_visible(del_btn_xpath, timeout=15)
    btn = sb.find_element(del_btn_xpath)
    sb.execute_script("arguments[0].scrollIntoView({block: 'center'});", btn)
    sb.sleep(0.3)
    sb.execute_script("arguments[0].focus(); arguments[0].click();", btn)
    sb.sleep(0.5)
