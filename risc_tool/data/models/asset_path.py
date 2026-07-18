import pathlib

MODULE_NAME = "risc_tool"


class AssetPath:
    APP_ICON = pathlib.Path(f"{MODULE_NAME}/assets/rt-icon.svg")
    APP_LOGO_LIGHT = pathlib.Path(f"{MODULE_NAME}/assets/rt-logo-light.svg")
    APP_LOGO_DARK = pathlib.Path(f"{MODULE_NAME}/assets/rt-logo-dark.svg")
    STYLESHEET = pathlib.Path(f"{MODULE_NAME}/assets/style.css")


__all__ = ["AssetPath"]
