"""Asset path constants for the RISC Tool application.

This module defines paths to static assets (icons, logos, stylesheets) used
throughout the application. Paths are relative to the project root.
"""

import pathlib

MODULE_NAME = "risc_tool"


class AssetPath:
    """Container for application asset file paths.

    Attributes:
        APP_ICON: Path to the application icon (SVG).
        APP_LOGO_LIGHT: Path to the light theme logo (SVG).
        APP_LOGO_DARK: Path to the dark theme logo (SVG).
        STYLESHEET: Path to the custom CSS stylesheet.
    """

    APP_ICON = pathlib.Path(f"{MODULE_NAME}/assets/rt-icon.svg")
    APP_LOGO_LIGHT = pathlib.Path(f"{MODULE_NAME}/assets/rt-logo-light.svg")
    APP_LOGO_DARK = pathlib.Path(f"{MODULE_NAME}/assets/rt-logo-dark.svg")
    NO_DATA_ERROR_ICON = pathlib.Path(f"{MODULE_NAME}/assets/no-data-error.svg")
    NO_FILTER_ICON = pathlib.Path(f"{MODULE_NAME}/assets/no-filter.svg")
    NO_METRIC_ICON = pathlib.Path(f"{MODULE_NAME}/assets/no-metric.svg")
    ARROW_RIGHT = pathlib.Path(f"{MODULE_NAME}/assets/arrow-right.svg")
    FILTER_QUERY_REFERENCE = pathlib.Path(
        f"{MODULE_NAME}/assets/filter_query_reference.md"
    )
    STYLESHEET = pathlib.Path(f"{MODULE_NAME}/assets/style.css")


__all__ = ["AssetPath"]
