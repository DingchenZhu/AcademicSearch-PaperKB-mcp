"""Abstract base class for academic search backends."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional

from src.core.models import Paper


class BaseSearchClient(ABC):
    """Each search backend implements this interface."""

    @abstractmethod
    async def search(
        self,
        query: str,
        year_from: Optional[int] = None,
        year_to: Optional[int] = None,
        max_results: int = 20,
    ) -> list[Paper]:
        """Return a list of papers matching the query."""

    @abstractmethod
    async def get_metadata(self, external_id: str) -> Optional[Paper]:
        """Fetch full metadata for a single paper by its source-specific ID."""
