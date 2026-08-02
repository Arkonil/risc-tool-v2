"""Utilities for loading and parsing documentation HTML pages."""

import re

import streamlit as st

from risc_tool.data.models.docs_path import DocPage, DocsPath


@st.cache_data
def load_documentation_pages() -> list[DocPage]:
    """Loads all documentation pages and extracts HTML body and inline CSS styles."""
    pages: list[DocPage] = []

    for doc_page in DocsPath.get_all_pages():
        path = doc_page.path

        if not path.exists():
            continue

        try:
            full_html = path.read_text(encoding="utf-8")

            styles = re.findall(r"<style>(.*?)</style>", full_html, re.DOTALL)
            body_match = re.search(
                r'<body class="markdown-body">(.*?)</body>', full_html, re.DOTALL
            )

            content_html = ""
            gfm_styles = ""

            if styles:
                gfm_styles = "".join(styles)

            if DocsPath.GFM_STYLESHEET.exists():
                gfm_styles += DocsPath.GFM_STYLESHEET.read_text(encoding="utf-8")

            content_html += f"<style>{gfm_styles}</style>"

            if body_match:
                content_html += (
                    f'<div class="markdown-body">{body_match.group(1)}</div>'
                )
            else:
                content_html += full_html

            pages.append(
                DocPage(
                    title=doc_page.title,
                    slug=doc_page.slug,
                    path=doc_page.path,
                    content=content_html,
                )
            )
        except Exception as e:  # noqa: BLE001
            print(f"Error loading {path}: {e}")

    return pages


__all__ = ["load_documentation_pages"]
