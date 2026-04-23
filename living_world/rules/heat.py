"""Tile heat scoring — pure-rule heuristic for "where is something likely
to happen right now?"

Used by the emergent-event LLM to pick which 1-2 tiles to spend its budget
on each tick. The scoring itself is deterministic and cheap (no LLM, no
embeddings) — just counts agents, historical figures, strong pairwise
affinity, and recent event density.

This file lives in `rules/` because the question "which tile is hot?" is
a pure function of world state. The downstream LLM call (in
`agents/emergent.py`) is what's intelligent.
"""

from __future__ import annotations

from living_world.core.tile import Tile
from living_world.core.world import World


def score_tile_heat(tile: Tile, world: World, *, recent_ticks: int = 3) -> float:
    """Higher = more likely something dramatic should happen here now.

    Signal weights (deliberately simple, tweak with care):
        +1.0 per resident
        +2.0 per historical figure
        +1.5 per pairwise affinity ≥ 40 (friend OR enemy — both = drama)
        +0.3 per event in this tile in the last `recent_ticks` ticks

    Returns 0.0 if fewer than 2 residents — emergent events need
    interaction, a single agent in an empty room is not interesting.
    """
    residents = world.agents_in_tile(tile.tile_id)
    if len(residents) < 2:
        return 0.0
    hf_count = sum(1 for a in residents if a.is_historical_figure)
    strong_pairs = 0
    for i, a in enumerate(residents):
        for b in residents[i + 1 :]:
            if abs(a.get_affinity(b.agent_id)) >= 40:
                strong_pairs += 1
    since = max(1, world.current_tick - recent_ticks)
    recent = sum(1 for e in world.events_since(since) if e.tile_id == tile.tile_id)
    return len(residents) + 2 * hf_count + 1.5 * strong_pairs + 0.3 * recent


def hot_tiles(world: World, *, limit: int = 2, min_heat: float = 3.5) -> list[Tile]:
    """Return the top-K tiles where something dramatic is likeliest right now."""
    scored: list[tuple[float, Tile]] = []
    for tile in world.all_tiles():
        h = score_tile_heat(tile, world)
        if h >= min_heat:
            scored.append((h, tile))
    scored.sort(key=lambda x: -x[0])
    return [t for _, t in scored[:limit]]
