"""Pydantic model for autocomplete completion entries.

This module defines the Completion model used by the query editor to
provide column name and function name autocomplete suggestions in the UI.
"""

from pydantic import BaseModel, ConfigDict


class Completion(BaseModel):
    """A single autocomplete suggestion entry for the code editor.

    Attributes:
        caption: Display text shown in the autocomplete dropdown.
        value: The text inserted when the completion is selected.
        meta: Descriptive category label (e.g., "Column", "Numerical Column").
        name: Unique name for the completion entry.
        score: Numeric rank for ordering suggestions (higher = preferred).
    """

    model_config = ConfigDict(serialize_by_alias=True, validate_by_alias=True)

    caption: str
    value: str
    meta: str
    name: str
    score: int

    def to_dict(self) -> dict[str, str | int]:
        """Convert the completion to a dictionary for the code editor library.

        Returns:
            A dictionary with keys caption, value, meta, name, and score.
        """
        return {
            "caption": self.caption,
            "value": self.value,
            "meta": self.meta,
            "name": self.name,
            "score": self.score,
        }
