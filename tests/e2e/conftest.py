"""Pytest configuration for E2E (SeleniumBase) tests.

E2E tests drive a real browser through SeleniumBase, which is not installed
by default (it lives in the optional ``e2e`` extra) and needs a real
browser/webdriver to run. They are **opt-in**: run them with the
``RUN_E2E=1`` environment variable or the ``--run-e2e`` flag. Without
opt-in they are skipped so a plain ``pytest`` run never fails on a machine
that has no SeleniumBase or browser available.

Each E2E test is fully isolated: a fresh Streamlit server is started before
the test and torn down after it, so no server, session, or data is shared
between tests.
"""

import os
import pathlib
import socket
import subprocess
import time
import urllib.error
import urllib.request

import pytest

E2E_PYTEST_FLAG = "run_e2e"

ROOT_DIR = pathlib.Path(__file__).resolve().parent.parent.parent


def get_free_port() -> int:
    """Find a free TCP port available on localhost."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def wait_for_server(url: str, timeout: float = 30.0) -> bool:
    """Poll Streamlit health check endpoint until it responds with HTTP 200."""
    health_url = f"{url}/_stcore/health"
    start_time = time.time()
    while time.time() - start_time < timeout:
        try:
            req = urllib.request.Request(health_url)
            with urllib.request.urlopen(req, timeout=1.0) as response:
                if response.status == 200:
                    return True
        except (urllib.error.URLError, TimeoutError, ConnectionRefusedError, OSError):
            pass
        time.sleep(0.5)
    return False


@pytest.fixture
def streamlit_server():
    """Start a local Streamlit server and yield the base URL.

    Function-scoped: a fresh server is started for every test and torn down
    afterwards, so no state is shared between tests.
    """
    port = get_free_port()
    base_url = f"http://127.0.0.1:{port}"

    cmd = [
        "uv",
        "run",
        "streamlit",
        "run",
        "main.py",
        f"--server.port={port}",
        "--server.headless=true",
        "--server.fileWatcherType=none",
        "--browser.gatherUsageStats=false",
        "--server.address=127.0.0.1",
    ]

    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"

    process = subprocess.Popen(
        cmd,
        cwd=str(ROOT_DIR),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    ready = wait_for_server(base_url, timeout=30.0)
    if not ready:
        process.terminate()
        try:
            stdout, stderr = process.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            stdout, stderr = process.communicate()
        pytest.fail(
            f"Streamlit server failed to start at {base_url} within 30s.\n"
            f"STDOUT:\n{stdout}\nSTDERR:\n{stderr}"
        )

    yield base_url

    # Teardown: reliably stop the server and free the port before the next test.
    process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait()


def pytest_addoption(parser):
    parser.addoption(
        "--run-e2e",
        action="store_true",
        default=False,
        help="Run SeleniumBase end-to-end UI tests (requires the 'e2e' extra).",
    )


def pytest_configure(config):
    config.addinivalue_line(
        "markers", "e2e: SeleniumBase end-to-end UI tests (opt-in via RUN_E2E=1)"
    )


def pytest_collection_modifyitems(config, items):
    """Skip E2E tests unless the user explicitly opted in."""
    enabled = (
        os.environ.get("RUN_E2E", "").strip() == "1"
        or config.getoption(E2E_PYTEST_FLAG)
    )
    if enabled:
        return

    skip = pytest.mark.skip(
        reason="E2E tests skipped: set RUN_E2E=1 or use --run-e2e to run"
    )
    for item in items:
        if "e2e" in item.keywords:
            item.add_marker(skip)
