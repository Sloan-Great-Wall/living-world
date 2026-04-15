"""Agent memory — remember, recall, reflect."""

from __future__ import annotations

import hashlib

from living_world.memory import AgentMemoryStore, EmbeddingClient


class DeterministicEmbedder(EmbeddingClient):
    """Tests-only hash-based embedder. Not semantically meaningful —
    just deterministic and cheap. Does NOT call any external service."""

    dim = 128

    def embed(self, text: str) -> list[float]:
        h = hashlib.sha256(text.encode("utf-8")).digest()
        out: list[float] = []
        i = 0
        while len(out) < self.dim:
            out.append((h[i % 32] / 127.5) - 1.0)
            i += 1
        return out


def test_remember_and_recall():
    store = AgentMemoryStore(embedder=DeterministicEmbedder())
    store.remember(agent_id="alice", tick=1, doc="Alice met Bob at the tea house.")
    store.remember(agent_id="alice", tick=2, doc="Alice argued with Clara about pottery.")
    store.remember(agent_id="alice", tick=3, doc="Alice studied calligraphy alone.")
    store.remember(agent_id="bob", tick=1, doc="Bob sold tea leaves at the market.")

    results = store.recall("alice", "tea house memory", k=3)
    assert len(results) == 3
    assert all(r.agent_id == "alice" for r in results)


def test_reflection_folds_raw_entries():
    store = AgentMemoryStore(embedder=DeterministicEmbedder())
    for i in range(6):
        store.remember(agent_id="bob", tick=i, doc=f"event {i}")
    reflection = store.reflect(agent_id="bob", tick=10)
    assert reflection is not None
    assert reflection.kind == "reflection"
    assert reflection.metadata["folded_count"] == 6


def test_reflection_needs_minimum_raw():
    store = AgentMemoryStore(embedder=DeterministicEmbedder())
    store.remember(agent_id="carol", tick=1, doc="one")
    reflection = store.reflect(agent_id="carol", tick=2)
    assert reflection is None  # too few raw to fold
