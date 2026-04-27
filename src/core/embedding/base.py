"""Abstract interface for embedding providers."""

from __future__ import annotations

from abc import ABC, abstractmethod


class BaseEmbedder(ABC):
    """Produce float-vector embeddings for text strings."""

    @abstractmethod
    async def embed(self, texts: list[str]) -> list[list[float]]:
        """Return one embedding vector per input text."""

    async def embed_one(self, text: str) -> list[float]:
        return (await self.embed([text]))[0]
