"""Custom Streamlit component wrapper for the documentation viewer."""

import streamlit.components.v2 as components

from risc_tool.data.models.docs_path import DocPage, DocsPath
from risc_tool.ui.components.theme_detector import get_theme

DOCS_JS = (
    DocsPath.DOC_VIEWER_JS.read_text(encoding="utf-8")
    if DocsPath.DOC_VIEWER_JS.exists()
    else ""
)
DOCS_CSS = (
    DocsPath.DOC_VIEWER_CSS.read_text(encoding="utf-8")
    if DocsPath.DOC_VIEWER_CSS.exists()
    else ""
)

_doc_viewer_component = components.component(
    "documentation_viewer",
    js=DOCS_JS,
    css=DOCS_CSS,
)


def documentation_viewer(pages: list[DocPage], active_index: int) -> int:
    """Renders custom documentation viewer component returning active page index."""
    result = _doc_viewer_component(
        data={
            "pages": [
                {
                    "title": page.title,
                    "slug": page.slug,
                    "path": str(page.path),
                    "content": page.content,
                }
                for page in pages
            ],
            "activeIndex": active_index,
            "theme": get_theme(),
        },
        key="doc_viewer",
    )

    if (
        result is not None
        and hasattr(result, "activeIndex")
        and result.activeIndex is not None
    ):
        return int(result.activeIndex)

    return active_index


__all__ = ["documentation_viewer"]
