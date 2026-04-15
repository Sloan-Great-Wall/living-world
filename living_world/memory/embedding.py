"""Embedding clients — abstract + Ollama backend + mock for tests.

Default local embedder: `nomic-embed-text` via Ollama (768d, small, open-weights).
Swap to BGE-M3 (1024d) when GPU server is available.
"""

from __future__ import annotations

import hashlib
from abc import ABC, abstractmethod

import httpx


class EmbeddingClient(ABC):
    dim: int = 0

    @abstractmethod
    def embed(self, text: str) -> list[float]:
        ...

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        return [self.embed(t) for t in texts]


class MockEmbedder(EmbeddingClient):
    """Deterministic hash-based pseudo-embedding — tests only, NOT semantically meaningful."""

    dim = 128

    def embed(self, text: str) -> list[float]:
        h = hashlib.sha256(text.encode("utf-8")).digest()
        # Stretch 32 bytes to `dim` floats in [-1, 1]
        out: list[float] = []
        i = 0
        while len(out) < self.dim:
            out.append((h[i % 32] / 127.5) - 1.0)
            i += 1
        return out


class OllamaEmbedder(EmbeddingClient):
    """Real embedder via Ollama. Default model: nomic-embed-text (768d)."""

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

    def embed(self, text: str) -> list[float]:
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
            return list(emb)
        except Exception:
            # Fail soft — caller can skip memory write
            return []
