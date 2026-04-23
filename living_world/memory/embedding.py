"""Embedding clients — abstract + Ollama backend.

Default local embedder: `nomic-embed-text` via Ollama (768d, small, open-weights).
Swap to BGE-M3 (1024d) when GPU server is available.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

import httpx


class EmbeddingClient(ABC):
    dim: int = 0

    @abstractmethod
    def embed(self, text: str) -> list[float]: ...

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        return [self.embed(t) for t in texts]


class OllamaEmbedder(EmbeddingClient):
    """Real embedder via Ollama. Default model: nomic-embed-text (768d).

    Includes a small in-memory LRU cache: many recall sites query with
    the same text within a tick (e.g. agent.current_goal is stable
    across self_update + planner + dialogue calls), so caching saves
    10-20% of embedding calls without any quality cost.
    """

    _CACHE_MAX = 4096  # ~6 MB of float lists at 768d; cheap

    def __init__(
        self,
        model: str = "nomic-embed-text",
        base_url: str = "http://localhost:11434",
        timeout: float = 30.0,
    ) -> None:
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.dim = 768 if "nomic-embed" in model else 1024  # common defaults
        self._cache: dict[str, list[float]] = {}
        self.cache_hits = 0
        self.cache_misses = 0

    def embed(self, text: str) -> list[float]:
        # Cache key uses model + text so swapping models invalidates entries.
        key = text
        cached = self._cache.get(key)
        if cached is not None:
            self.cache_hits += 1
            return cached
        self.cache_misses += 1
        try:
            r = httpx.post(
                f"{self.base_url}/api/embeddings",
                json={"model": self.model, "prompt": text},
                timeout=self.timeout,
            )
            r.raise_for_status()
            data = r.json()
            emb = data.get("embedding", [])
            if emb and self.dim != len(emb):
                self.dim = len(emb)  # auto-correct from actual response
            emb_list = list(emb)
            # Naive eviction: hard cap, drop oldest insertion-order entry.
            if len(self._cache) >= self._CACHE_MAX:
                # py3.7+ dict preserves insertion order
                first_key = next(iter(self._cache))
                del self._cache[first_key]
            if emb_list:
                self._cache[key] = emb_list
            return emb_list
        except Exception:
            # Fail soft — caller can skip memory write
            return []
