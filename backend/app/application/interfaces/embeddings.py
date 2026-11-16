"""Extension point for future visual-embedding deduplication (not used in MVP)."""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class EmbeddingSimilarityProvider(Protocol):
    async def similarity(self, embedding_a: list[float], embedding_b: list[float]) -> float: ...
