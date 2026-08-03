"""Central repository for documentation file paths and metadata."""

import pathlib

from pydantic import BaseModel

MODULE_NAME = "risc_tool"


class DocPage(BaseModel):
    """Metadata and content for a single documentation page.

    Attributes:
        title: Display title of the documentation page.
        slug: Unique URL-friendly identifier used for lookup.
        path: Filesystem path to the page's HTML source.
        content: Optional preloaded page content as a string.
    """

    title: str
    slug: str
    path: pathlib.Path
    content: str = ""


class DocsPath:
    """Central repository for documentation file paths and metadata."""

    DOCS_DIR: pathlib.Path = pathlib.Path(f"{MODULE_NAME}/assets/docs")

    # Static file paths
    INTRODUCTION: pathlib.Path = DOCS_DIR / "00_introduction.html"
    HOME: pathlib.Path = DOCS_DIR / "01_home_page.html"
    DATA_IMPORTER: pathlib.Path = DOCS_DIR / "02_data_importer.html"
    DATA_EXPLORER: pathlib.Path = DOCS_DIR / "03_data_explorer.html"
    METRICS: pathlib.Path = DOCS_DIR / "04_metric_editor.html"
    FILTERS: pathlib.Path = DOCS_DIR / "05_filter_editor.html"
    CONFIG: pathlib.Path = DOCS_DIR / "06_configurations.html"
    ITERATIONS: pathlib.Path = DOCS_DIR / "07_iterations.html"
    SUMMARY: pathlib.Path = DOCS_DIR / "08_summary.html"
    EXPORT: pathlib.Path = DOCS_DIR / "09_export.html"

    # stylesheet overwrites
    DOC_VIEWER_JS: pathlib.Path = DOCS_DIR / "doc_viewer.js"
    DOC_VIEWER_CSS: pathlib.Path = DOCS_DIR / "doc_viewer.css"
    GFM_STYLESHEET: pathlib.Path = DOCS_DIR / "gfm_styles.css"

    @classmethod
    def get_all_pages(cls) -> list[DocPage]:
        """Returns a structured list of all documentation pages with metadata."""
        return [
            DocPage(title="Introduction", slug="introduction", path=cls.INTRODUCTION),
            DocPage(title="Home Page", slug="home", path=cls.HOME),
            DocPage(title="Data Importer", slug="importer", path=cls.DATA_IMPORTER),
            DocPage(title="Data Explorer", slug="explorer", path=cls.DATA_EXPLORER),
            DocPage(title="Metric Editor", slug="metrics", path=cls.METRICS),
            DocPage(title="Filter Editor", slug="filters", path=cls.FILTERS),
            DocPage(title="Configurations", slug="config", path=cls.CONFIG),
            DocPage(title="Iterations", slug="iterations", path=cls.ITERATIONS),
            DocPage(title="Summary", slug="summary", path=cls.SUMMARY),
            DocPage(title="Export", slug="export", path=cls.EXPORT),
        ]

    @classmethod
    def get_all_files(cls) -> list[pathlib.Path]:
        """Returns a sorted list of all documentation file paths."""
        return [page.path for page in cls.get_all_pages()]

    @classmethod
    def get_page_by_slug(cls, slug: str) -> DocPage | None:
        """Retrieves a doc page by its slug."""
        for page in cls.get_all_pages():
            if page.slug == slug:
                return page
        return None


__all__ = ["DocPage", "DocsPath"]
