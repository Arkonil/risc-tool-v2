"""Helper functions for SeleniumBase E2E tests interacting with Streamlit."""

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
    sb.set_window_size(1920, 1080)
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
    elif page_title in ("Filters", "Metrics"):
        try:
            sb.wait_for_element_visible("h1", timeout=15)
            sb.assert_text(page_title, "h1")
        except Exception:  # noqa: BLE001 - page may show "Load Data" instead
            sb.wait_for_text_visible("Load Data", timeout=10)
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

    # Give Streamlit time to flush the committed widget values to the server
    # before clicking the submit button, so the button's on_click reads the
    # filled values rather than stale/empty ones.
    sb.sleep(1)

    button_selector = f'//button[contains(., "{click_label}")]'
    sb.wait_for_element_clickable(button_selector, timeout=15)
    sb.sleep(2)  # Give the button time to become clickable
    sb.click(button_selector)

    # A successful import closes the empty "Add" form and shows the
    # "Add Data Source" button. A failed import leaves the form up and
    # renders an error alert. Poll for either outcome, since a plain
    # stDataFrame/stAlert check is unreliable when other sources (and their
    # persistent success messages / data frames) are already on the page.
    # Import / schema regeneration can be slow when combining multiple
    # large sources, so allow generous headroom.
    deadline = time.time() + 240
    iter_n = 0
    while time.time() < deadline:
        if sb.is_element_visible('//button[contains(., "Add Data Source")]'):
            break
        error_text = _error_alert_text(sb)
        if error_text:
            raise AssertionError(f"Import failed with error: {error_text}")
        iter_n += 1
        if iter_n % 15 == 1:
            _debug_page_state(sb, f"wait[{iter_n}]")
        sb.sleep(1)
    else:
        raise AssertionError("Data import did not complete within 240s")

    # Wait for the data preview to fully load
    sb.wait_for_element_visible('[data-testid="stDataFrame"]', timeout=240)
    sb.wait_for_text_visible("Preview Data", timeout=240)
    sb.sleep(2)  # Give extra time for data to fully render


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
    print(f"[DEBUG:{tag}] nav={info.get('type')} url={info.get('url')} "
          f"app={info.get('app')} inputs={info.get('inputs')} "
          f"tabs=[{info.get('tabs')}] alerts=[{info.get('alerts')}]")


def _commit_widget_input(sb: BaseCase, element, expected: str | None = None):
    """Force a Streamlit widget to commit its DOM value to the server.

    Selenium's ``send_keys`` sets the DOM ``value`` but does not always fire the
    React ``onChange`` that Streamlit listens to, so the server can end up
    reading a stale/empty value (observed as ``Filepath: .``). Dispatch an
    ``input`` event and blur the field so Streamlit's React widget flushes the
    value to the server.
    """
    sb.execute_script(
        """
        const el = arguments[0];
        const setter = Object.getOwnPropertyDescriptor(
            window.HTMLInputElement.prototype, 'value'
        ).set;
        setter.call(el, el.value);
        el.dispatchEvent(new Event('input', { bubbles: true }));
        el.blur();
        """,
        element,
    )
    if expected is not None:
        deadline = time.time() + 5
        while time.time() < deadline:
            if sb.execute_script("return arguments[0].value;", element) == expected:
                break
            sb.sleep(0.2)


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


def delete_source_by_label(sb: BaseCase, label: str):
    """Click the delete button for the data source whose label matches ``label``.

    Streamlit widgets do not expose a ``@key`` HTML attribute and the delete
    button's key never contains the source label, so we locate the source's
    UID from its Data Label input container and target the matching delete
    button.
    """
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

    delete_selector = (
        f'[class*="st-key-delete_button-file_selector-{uid}"] '
        'button[data-testid="stBaseButton-primary"]'
    )
    sb.wait_for_element_clickable(delete_selector, timeout=15)
    sb.click(delete_selector)


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
    import_data_source(sb, server_url, filepath=train_path, label="Train Data")

    # Verify the data is now loaded by checking for the preview
    sb.wait_for_element_visible('[data-testid="stDataFrame"]', timeout=30)
    sb.wait_for_text_visible("Preview Data", timeout=30)

    # Give the server time to propagate session state to all view models
    sb.sleep(3)


def set_code_editor_value(sb: BaseCase, value: str):
    """Set query text in Streamlit code editor (Ace/CodeMirror fallback)."""
    sb.wait_for_element_visible('[data-testid="stAppViewContainer"]', timeout=20)
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


def click_primary_action(sb: BaseCase, label: str):
    """Click a button by visible label with a stable wait."""
    selector = f'//button[contains(., "{label}")]'
    sb.wait_for_element_clickable(selector, timeout=15)
    sb.click(selector)
