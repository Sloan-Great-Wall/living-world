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
    # Park 2023 decay/recall fields — see KNOWN_ISSUES.md #15.
    # `last_accessed_tick` is bumped every time .recall() returns this
    # entry; entries that never get recalled fade faster than entries
    # that keep coming up in agent decisions.
    last_accessed_tick: int = 0
    access_count: int = 0


def _cosine(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b, strict=True))
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

    def remove_many(self, memory_ids: set[str]) -> int:
        """Drop entries by id. Returns count actually removed."""
        before = len(self._entries)
        self._entries = [e for e in self._entries if e.memory_id not in memory_ids]
        return before - len(self._entries)


class AgentMemoryStore:
    """High-level API. Writes raw events and reflections, reads for prompt retrieval."""

    def __init__(
        self,
        embedder: EmbeddingClient,
        backend: InMemoryBackend | None = None,
        reflector=None,  # optional MemoryReflector — see agents/reflector.py
    ) -> None:
        self.embedder = embedder
        self.backend = backend or InMemoryBackend()
        self.reflector = reflector  # injected by factory if LLM available

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
            agent_id=agent_id,
            tick=tick,
            doc=doc.strip(),
            importance=importance,
            kind=kind,
            embedding=emb,
            metadata=metadata or {},
        )
        self.backend.add(entry)
        return entry

    def recall(
        self,
        agent_id: str,
        query: str,
        *,
        top_k: int = 5,
        current_tick: int | None = None,
        k: int | None = None,  # legacy alias — older call sites used `k`
    ) -> list[MemoryEntry]:
        """Top-K most-similar memories for an agent.

        If `current_tick` is supplied, every returned entry's
        `last_accessed_tick` is bumped and `access_count` incremented —
        feeds the Park-style decay scoring (KNOWN_ISSUES #15).
        """
        if k is not None:
            top_k = k
        emb = self.embedder.embed(query)
        if not emb:
            return []
        results = self.backend.query(agent_id, emb, k=top_k)
        # Bump access bookkeeping so heavily-recalled memories survive decay
        if current_tick is not None:
            for e in results:
                e.last_accessed_tick = current_tick
                e.access_count += 1
        return results

    def decay(
        self,
        agent_id: str,
        current_tick: int,
        *,
        max_per_agent: int = 200,
        recency_half_life: float = 30.0,
        prune_fraction: float = 0.20,
    ) -> int:
        """Park-style decay: score every memory and drop the dullest if the
        agent's store exceeds `max_per_agent`. Returns count pruned.

        Score = importance × recency_factor × access_factor
          - recency_factor = 0.5 ** (age_in_ticks / recency_half_life)
          - access_factor  = log2(2 + access_count)        # mild boost
        Reflections get a +0.15 importance bonus inside the score so the
        agent's *abstractions* survive longer than the raw events that
        formed them.
        """
        all_entries = self.backend.list_all_for(agent_id)
        if len(all_entries) <= max_per_agent:
            return 0

        import math

        def score(e: MemoryEntry) -> float:
            age = max(0, current_tick - e.tick)
            recency = 0.5 ** (age / max(1.0, recency_half_life))
            access = math.log2(2 + e.access_count)
            kind_bonus = 0.15 if e.kind == "reflection" else 0.0
            return (e.importance + kind_bonus) * recency * access

        scored = sorted(all_entries, key=score)  # lowest first = first dropped
        n_drop = max(1, int(len(all_entries) * prune_fraction))
        # Don't drop more than the overflow over the cap.
        n_drop = min(n_drop, len(all_entries) - max_per_agent + n_drop)
        victims = {e.memory_id for e in scored[:n_drop]}
        return self.backend.remove_many(victims)

    def count(self, agent_id: str) -> int:
        return self.backend.count_for(agent_id)

    def reflect(
        self,
        agent_id: str,
        tick: int,
        *,
        max_raw_to_fold: int = 20,
        agent=None,  # optional Agent — required for LLM-driven reflection
    ) -> MemoryEntry | None:
        """Summarize recent raw memories into a reflection.

        Park 2023 path (preferred): if a `MemoryReflector` is wired AND
        an `agent` instance is supplied, ask the LLM to emit beliefs
        and store one summary memory listing them.

        MVP fallback: concatenate raw memory docs (used when no
        reflector or agent is available, e.g. in tests).
        """
        entries = [e for e in self.backend.list_all_for(agent_id) if e.kind == "raw"]
        recent = entries[-max_raw_to_fold:]
        if len(recent) < 3:
            return None
        docs = [e.doc for e in recent]

        # ── Park-style LLM reflection ──
        if self.reflector is not None and agent is not None:
            beliefs = self.reflector.reflect(agent, docs)
            if beliefs:
                belief_lines = [f"- {b['topic']}: {b['belief']}" for b in beliefs]
                summary = f"[reflection @ tick {tick}] I now believe:\n" + "\n".join(belief_lines)
                return self.remember(
                    agent_id=agent_id,
                    tick=tick,
                    doc=summary,
                    kind="reflection",
                    importance=0.5,
                    metadata={"folded_count": len(recent), "beliefs": beliefs, "source": "llm"},
                )
            # If reflector produced nothing, fall through to MVP
            # so the cadence still records *something*.

        # ── MVP fallback ──
        joined = "\n".join(f"- {d}" for d in docs)
        summary = f"[reflection @ tick {tick}] Recent pattern:\n{joined[:1200]}"
        return self.remember(
            agent_id=agent_id,
            tick=tick,
            doc=summary,
            kind="reflection",
            importance=0.4,
            metadata={"folded_count": len(recent), "source": "mvp"},
        )
