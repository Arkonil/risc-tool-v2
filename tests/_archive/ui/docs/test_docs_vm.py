"""Unit tests for DocsViewModel and DocsPath utilities."""

from risc_tool.data.models.docs_path import DocsPath
from risc_tool.ui.docs.docs_vm import DocsViewModel
from risc_tool.ui.docs.utils import load_documentation_pages


def test_docs_view_model_initialization():
    vm = DocsViewModel()
    assert vm.documentation_page_idx == 0


def test_docs_view_model_set_page_index():
    vm = DocsViewModel()
    vm.set_page_index(3)
    assert vm.documentation_page_idx == 3


def test_load_documentation_pages():
    pages = load_documentation_pages()
    assert len(pages) == 10
    assert pages[0].title == "Introduction"
    assert pages[0].slug == "introduction"
    assert "markdown-body" in pages[0].content


def test_docs_path_get_page_by_slug():
    page = DocsPath.get_page_by_slug("iterations")
    assert page is not None
    assert page.title == "Iterations"
    assert DocsPath.get_page_by_slug("nonexistent") is None
