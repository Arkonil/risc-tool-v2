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
    STYLESHEET = pathlib.Path(f"{MODULE_NAME}/assets/style.css")


__all__ = ["AssetPath"]
