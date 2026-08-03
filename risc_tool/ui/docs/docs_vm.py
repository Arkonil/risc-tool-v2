"""View Model for the Documentation page."""

from risc_tool.data.models.changes import ChangeTracker
from risc_tool.data.models.enums import Signature
from risc_tool.data.models.types import ChangeIDs


class DocsViewModel(ChangeTracker):
    """View model managing Documentation page navigation state."""

    @property
    def signature(self) -> Signature:
        """Get the component signature for change tracking.

        Returns:
            Signature.DOCS_VIEW_MODEL
        """
        return Signature.DOCS_VIEW_MODEL

    def __init__(self) -> None:
        """Initialize the DocsViewModel with the first documentation page active."""
        super().__init__(dependencies=[])
        self.documentation_page_idx: int = 0

    def on_dependency_update(self, change_ids: ChangeIDs) -> None:
        """Handle changes in dependencies."""

    def set_page_index(self, index: int) -> None:
        """Set active documentation page index."""
        self.documentation_page_idx = index


__all__ = ["DocsViewModel"]
