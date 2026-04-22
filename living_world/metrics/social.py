"""Social network metrics over the world's affinity graph.

Inspired by AgentSociety (Tsinghua) — see KNOWN_ISSUES.md issue #16.

The affinity graph is built from `agent.relationships`. We treat an
edge as "real" when |affinity| ≥ a threshold (default 30, meaning the
two agents have a meaningfully positive or negative bond — neutral
acquaintances at affinity ≈ 0 don't count). The graph is undirected
for component analysis (we OR the two directions).

No external deps — pure stdlib so this runs anywhere the sim runs.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Iterable

from living_world.core.agent import Agent


# ── Public API ─────────────────────────────────────────────────────────────

def affinity_graph(
    agents: Iterable[Agent],
    *,
    min_abs_affinity: int = 30,
    pack_id: str | None = None,
) -> dict[str, set[str]]:
    """Build an undirected adjacency map over living agents.

    An edge a↔b exists if either side has |affinity| ≥ threshold for
    the other. Returns {agent_id: {neighbour_ids}}.
    """
    pool = [
        a for a in agents
        if a.is_alive() and (pack_id is None or a.pack_id == pack_id)
    ]
    pool_ids = {a.agent_id for a in pool}
    adj: dict[str, set[str]] = {a.agent_id: set() for a in pool}
    for a in pool:
        for target_id, rel in a.relationships.items():
            if target_id not in pool_ids:
                continue
            if abs(rel.affinity) >= min_abs_affinity:
                adj[a.agent_id].add(target_id)
                adj[target_id].add(a.agent_id)  # symmetrize
    return adj


@dataclass
class SocialMetrics:
    """Aggregate social readout for a world (or one pack within it)."""

    n_agents: int = 0
    n_edges: int = 0
    avg_degree: float = 0.0
    isolated: list[str] = field(default_factory=list)
    components: list[list[str]] = field(default_factory=list)
    top_central: list[tuple[str, int]] = field(default_factory=list)
    clustering_global: float = 0.0

    @property
    def n_components(self) -> int:
        return len(self.components)

    @property
    def biggest_component_size(self) -> int:
        return max((len(c) for c in self.components), default=0)

    def summary(self) -> str:
        """One-screen text summary, suitable for CLI / dashboard."""
        lines = [
            f"agents={self.n_agents}  edges={self.n_edges}  "
            f"avg_degree={self.avg_degree:.2f}",
            f"components={self.n_components}  "
            f"biggest={self.biggest_component_size}  "
            f"isolated={len(self.isolated)}",
            f"global_clustering={self.clustering_global:.3f}",
            "top central:",
        ]
        for aid, deg in self.top_central:
            lines.append(f"  {deg:3d}  {aid}")
        return "\n".join(lines)


def compute_social_metrics(
    agents: Iterable[Agent],
    *,
    min_abs_affinity: int = 30,
    pack_id: str | None = None,
    top_k: int = 5,
) -> SocialMetrics:
    """Compute the full SocialMetrics over the affinity graph."""
    adj = affinity_graph(agents, min_abs_affinity=min_abs_affinity, pack_id=pack_id)
    n = len(adj)
    if n == 0:
        return SocialMetrics()

    # edges (count once per pair)
    edges_seen: set[tuple[str, str]] = set()
    for a, neigh in adj.items():
        for b in neigh:
            edges_seen.add((min(a, b), max(a, b)))
    n_edges = len(edges_seen)

    degrees = {a: len(neigh) for a, neigh in adj.items()}
    avg_deg = (sum(degrees.values()) / n) if n else 0.0
    isolated = sorted(a for a, d in degrees.items() if d == 0)
    top_central = sorted(degrees.items(), key=lambda x: x[1], reverse=True)[:top_k]

    components = _connected_components(adj)
    clustering = _global_clustering(adj)

    return SocialMetrics(
        n_agents=n,
        n_edges=n_edges,
        avg_degree=avg_deg,
        isolated=isolated,
        components=components,
        top_central=top_central,
        clustering_global=clustering,
    )


# ── Internals ──────────────────────────────────────────────────────────────

def _connected_components(adj: dict[str, set[str]]) -> list[list[str]]:
    """Standard BFS over the undirected graph. Returns components sorted
    by size (largest first), ids within each component sorted."""
    seen: set[str] = set()
    out: list[list[str]] = []
    for start in adj:
        if start in seen:
            continue
        # BFS
        comp: list[str] = []
        stack = [start]
        while stack:
            node = stack.pop()
            if node in seen:
                continue
            seen.add(node)
            comp.append(node)
            stack.extend(adj[node] - seen)
        out.append(sorted(comp))
    out.sort(key=len, reverse=True)
    return out


def _global_clustering(adj: dict[str, set[str]]) -> float:
    """Global clustering coefficient = mean over nodes of
    (closed triangles through node) / (possible triangles through node).

    Returns 0.0 if no node has ≥2 neighbours (can't form a triangle).
    """
    coeffs: list[float] = []
    for node, neigh in adj.items():
        k = len(neigh)
        if k < 2:
            continue
        # count edges among neighbours
        nlist = list(neigh)
        triangles = 0
        for i in range(len(nlist)):
            for j in range(i + 1, len(nlist)):
                if nlist[j] in adj.get(nlist[i], ()):
                    triangles += 1
        possible = k * (k - 1) // 2
        coeffs.append(triangles / possible if possible else 0.0)
    return sum(coeffs) / len(coeffs) if coeffs else 0.0
