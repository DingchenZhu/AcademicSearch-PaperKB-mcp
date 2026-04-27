"""OpenAI-compatible embedding client (also works with NVIDIA NIM)."""

from __future__ import annotations

import os

from openai import AsyncOpenAI

from .base import BaseEmbedder


class OpenAIEmbedder(BaseEmbedder):
    """Uses any OpenAI-compatible /v1/embeddings endpoint.

    Configured via environment variables (see .env.example):
      OPENAI_API_KEY, OPENAI_BASE_URL, EMBEDDING_MODEL
    """

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
    ) -> None:
        self._model = model or os.environ.get("EMBEDDING_MODEL", "text-embedding-3-small")
        self._client = AsyncOpenAI(
            api_key=api_key or os.environ.get("OPENAI_API_KEY"),
            base_url=base_url or os.environ.get("OPENAI_BASE_URL"),
        )

    async def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        response = await self._client.embeddings.create(model=self._model, input=texts)
        return [item.embedding for item in response.data]
