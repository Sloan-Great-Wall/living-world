"""AgentMemoryStore — write episodic memory entries, retrieve top-k similar.

Two backends:
  - InMemoryBackend (default): simple Python list + cosine sim, for tests + Stage A
  - PostgresBackend: writes to agent_memory table with pgvector
"""

from __future__ import annotations

import math
import uuid
from dataclasses import dataclass, field
from typing import Any

from living_world.memory.embedding import EmbeddingClient


@dataclass
class MemoryEntry:
    memory_id: str
    agent_id: str
    tick: int
    doc: str
    importance: float = 0.0
    kind: str = "raw"  # raw | reflection | interview
    embedding: list[float] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


def _cosine(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


class InMemoryBackend:
    def __init__(self) -> None:
        self._entries: list[MemoryEntry] = []

    def add(self, entry: MemoryEntry) -> None:
        self._entries.append(entry)

    def query(self, agent_id: str, query_vec: list[float], k: int = 5) -> list[MemoryEntry]:
        candidates = [e for e in self._entries if e.agent_id == agent_id]
        scored = [(e, _cosine(query_vec, e.embedding)) for e in candidates]
        # reflections get a 1.3× retrieval boost; interview gets 1.2×
        weighted = []
        for e, s in scored:
            bonus = 1.3 if e.kind == "reflection" else (1.2 if e.kind == "interview" else 1.0)
            weighted.append((e, s * bonus))
        weighted.sort(key=lambda x: x[1], reverse=True)
        return [e for e, _ in weighted[:k]]

    def count_for(self, agent_id: str) -> int:
        return sum(1 for e in self._entries if e.agent_id == agent_id)

    def list_all_for(self, agent_id: str) -> list[MemoryEntry]:
        return [e for e in self._entries if e.agent_id == agent_id]


class AgentMemoryStore:
    """High-level API. Writes raw events and reflections, reads for prompt retrieval."""

    def __init__(self, embedder: EmbeddingClient, backend: InMemoryBackend | None = None) -> None:
        self.embedder = embedder
        self.backend = backend or InMemoryBackend()

    def remember(
        self,
        agent_id: str,
        tick: int,
        doc: str,
        *,
        kind: str = "raw",
        importance: float = 0.0,
        metadata: dict[str, Any] | None = None,
    ) -> MemoryEntry | None:
        if not doc.strip():
            return None
        emb = self.embedder.embed(doc)
        if not emb:
            return None
        entry = MemoryEntry(
            memory_id=str(uuid.uuid4()),
            agent_id=agent_id, tick=tick, doc=doc.strip(),
            importance=importance, kind=kind,
            embedding=emb, metadata=metadata or {},
        )
        self.backend.add(entry)
        return entry

    def recall(self, agent_id: str, query: str, *, k: int = 5) -> list[MemoryEntry]:
        emb = self.embedder.embed(query)
        if not emb:
            return []
        return self.backend.query(agent_id, emb, k=k)

    def count(self, agent_id: str) -> int:
        return self.backend.count_for(agent_id)

    def reflect(
        self,
        agent_id: str,
        tick: int,
        *,
        max_raw_to_fold: int = 20,
    ) -> MemoryEntry | None:
        """Summarize recent raw memories into a reflection.

        MVP: concatenate + truncate (real LLM summary comes when Tier 3 pipeline wired in).
        """
        entries = [e for e in self.backend.list_all_for(agent_id) if e.kind == "raw"]
        recent = entries[-max_raw_to_fold:]
        if len(recent) < 3:
            return None
        joined = "\n".join(f"- {e.doc}" for e in recent)
        summary = f"[reflection @ tick {tick}] Recent pattern:\n{joined[:1200]}"
        return self.remember(
            agent_id=agent_id, tick=tick, doc=summary,
            kind="reflection", importance=0.4,
            metadata={"folded_count": len(recent)},
        )
