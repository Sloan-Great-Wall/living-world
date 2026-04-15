"""Agent movement — lightweight, probabilistic. Runs once per tick per agent.

Design goals:
- Historical figures mostly stay put (story anchor), but occasionally travel.
- Ordinary agents move more often (they explore / wander).
- Pack-aware: agent stays within tiles their pack has access to.
- Relationship-aware: small bias toward tiles containing friends.
"""

from __future__ import annotations

import random

from living_world.core.world import World


# Tag → tile_type preference weights. Multiplied into the tile score when an
# agent considers where to go. Higher = more likely to choose that tile type.
#
# These encode the physical-logic constraint: a monk wants a temple,
# a D-class does NOT want the containment chamber, an SCP anomaly cannot
# just stroll into the lounge.
TAG_TILE_AFFINITY: dict[str, dict[str, float]] = {
    # SCP roster
    "researcher":       {"research-floor": 3.0, "social-area": 1.5, "operations": 1.2, "hallway": 1.0, "containment-chamber": 0.6},
    "field-agent":      {"operations": 3.0, "hallway": 1.2, "social-area": 0.8, "research-floor": 0.5},
    "d-class":          {"d-holding": 2.5, "hallway": 0.4, "containment-chamber": 0.2,
                         "research-floor": 0.3, "social-area": 0.3, "operations": 0.2, "restricted": 0.05},
    "o5":               {"restricted": 4.0, "operations": 1.0, "research-floor": 0.8, "hallway": 0.3},
    "staff":            {"hallway": 2.5, "social-area": 1.8, "d-holding": 0.6, "research-floor": 0.6},
    "psychologist":     {"research-floor": 2.8, "social-area": 1.3, "d-holding": 1.0},
    "anomaly":          {"containment-chamber": 5.0, "hallway": 0.05, "social-area": 0.05, "research-floor": 0.1},
    # Cthulhu
    "academic":         {"restricted-archive": 3.0, "scholar-study": 2.0, "law-office": 0.6, "cult-hall": 0.1},
    "investigator":     {"law-office": 2.5, "restricted-archive": 1.5, "scholar-study": 1.2, "decaying-port": 1.0, "wilderness-haunt": 0.8},
    "reporter":         {"law-office": 2.0, "decaying-port": 1.5, "wilderness-haunt": 1.2, "cult-hall": 0.4},
    "law-enforcement":  {"law-office": 3.0, "decaying-port": 1.0, "cult-hall": 0.3},
    "cultist":          {"cult-hall": 3.5, "decaying-port": 1.5, "wilderness-haunt": 1.2, "law-office": 0.1},
    "hybrid":           {"decaying-port": 3.5, "cult-hall": 1.2, "law-office": 0.05},
    "mi-go":            {"wilderness-haunt": 4.0, "cosmic-void": 2.0, "scholar-study": 0.2},
    "great-old-one":    {"cosmic-ruin": 5.0, "cosmic-void": 4.0, "wilderness-haunt": 0.3},
    "outer-god":        {"cosmic-void": 5.0, "cosmic-ruin": 3.0},
    "dreamer":          {"scholar-study": 2.5, "restricted-archive": 1.5, "cosmic-void": 1.2},
    "artist":           {"scholar-study": 3.0},
    # Liaozhai
    "scholar":          {"scholar-study": 3.0, "market-street": 1.2, "official-yard": 0.8, "underworld-yard": 0.3},
    "monk":             {"haunted-temple": 4.0, "market-street": 0.4, "wilderness": 0.8},
    "fox-spirit":       {"fox-den": 2.5, "market-street": 1.5, "wilderness": 1.5, "haunted-temple": 0.5,
                         "scholar-study": 1.2, "courtyard-residence": 1.0},
    "ghost":            {"haunted-temple": 3.5, "scholar-study": 1.5, "courtyard-residence": 1.0,
                         "underworld-yard": 1.0, "market-street": 0.3},
    "demon":            {"haunted-temple": 4.0, "wilderness": 1.0, "market-street": 0.05},
    "deity":            {"underworld-yard": 4.0, "haunted-temple": 1.0, "official-yard": 0.8},
    "official":         {"official-yard": 4.0, "underworld-yard": 1.5, "market-street": 0.4},
    "mortal":           {"market-street": 2.5, "courtyard-residence": 1.8, "haunted-temple": 0.3},
}


# Frailty tags reduce movement probability (elderly / sickly / sleeping dreamers).
FRAILTY_TAG_BOOST: dict[str, float] = {
    "permanent_historical": 0.4,  # world-level fixtures stay put more
    "dreaming": 0.3,
    "hybrid": 0.7,                # aging hybrids less mobile
}

# Tags for agents who SHOULDN'T move at all (anchored to their site).
ANCHORED_TAGS: set[str] = {"anomaly", "great-old-one", "outer-god"}


def _tile_affinity_score(agent_tags: set[str], tile_type: str) -> float:
    """Combine affinity weights from all matching tags; default 1.0 if none match."""
    scores = []
    for tag in agent_tags:
        weights = TAG_TILE_AFFINITY.get(tag)
        if weights and tile_type in weights:
            scores.append(weights[tile_type])
    if not scores:
        return 1.0
    # Use min — physical logic: ONE strong "must not go" overrules ten weak yeses
    return min(scores) * (sum(scores) / len(scores)) ** 0.5


class MovementPolicy:
    """Decide per-tick whether each agent moves, and where to."""

    def __init__(
        self,
        world: World,
        rng: random.Random | None = None,
        *,
        base_move_prob: float = 0.08,
        hf_move_prob: float = 0.03,
        friend_pull: float = 0.35,
        llm_advisor=None,       # optional LLMMoveAdvisor
        llm_hf_only: bool = True,
        llm_chance: float = 0.3,  # when LLM applies, how often to use it
    ) -> None:
        self.world = world
        self.rng = rng or random.Random()
        self.base_move_prob = base_move_prob
        self.hf_move_prob = hf_move_prob
        self.friend_pull = friend_pull
        self.llm_advisor = llm_advisor
        self.llm_hf_only = llm_hf_only
        self.llm_chance = llm_chance

    def _candidate_tiles_weighted(self, agent) -> list[tuple[str, float]]:
        """(tile_id, weight) pairs respecting pack rules + tag affinities."""
        out: list[tuple[str, float]] = []
        for t in self.world.all_tiles():
            if t.tile_id == agent.current_tile:
                continue
            if t.allowed_packs and agent.pack_id not in t.allowed_packs:
                continue
            w = _tile_affinity_score(agent.tags, t.tile_type)
            if w <= 0.01:
                continue  # hard-excluded by physical logic
            out.append((t.tile_id, w))
        return out

    def _friend_tiles(self, agent) -> list[str]:
        """Tiles currently containing agents the subject likes (affinity >= 40)."""
        friend_ids = [
            r.target_id for r in agent.relationships.values()
            if r.affinity >= 40
        ]
        tiles: list[str] = []
        for fid in friend_ids:
            other = self.world.get_agent(fid)
            if other and other.is_alive() and other.current_tile:
                tiles.append(other.current_tile)
        return tiles

    def _move_agent(self, agent, to_tile_id: str) -> None:
        """Update world state: remove from old tile, add to new."""
        old_tile = self.world.get_tile(agent.current_tile) if agent.current_tile else None
        if old_tile and agent.agent_id in old_tile.resident_agents:
            old_tile.resident_agents.remove(agent.agent_id)
        agent.current_tile = to_tile_id
        new_tile = self.world.get_tile(to_tile_id)
        if new_tile and agent.agent_id not in new_tile.resident_agents:
            new_tile.resident_agents.append(agent.agent_id)

    def _weighted_choice(self, candidates: list[tuple[str, float]]) -> str:
        total = sum(w for _, w in candidates)
        r = self.rng.uniform(0, total)
        acc = 0.0
        for tile_id, w in candidates:
            acc += w
            if r <= acc:
                return tile_id
        return candidates[-1][0]

    def tick(self) -> list[tuple[str, str, str]]:
        """Run one movement tick. Returns list of (agent_id, from_tile, to_tile)."""
        moves: list[tuple[str, str, str]] = []
        for agent in list(self.world.living_agents()):
            # Anchored entities do not move (SCP-173, Cthulhu, etc.)
            if ANCHORED_TAGS & agent.tags:
                continue

            base = self.hf_move_prob if agent.is_historical_figure else self.base_move_prob
            # Frailty damping
            for tag in FRAILTY_TAG_BOOST:
                if tag in agent.tags:
                    base *= FRAILTY_TAG_BOOST[tag]

            if self.rng.random() > base:
                continue

            candidates = self._candidate_tiles_weighted(agent)
            if not candidates:
                continue

            dest: str | None = None

            # LLM advisor override — only for historical figures (if opt-in)
            use_llm = (
                self.llm_advisor is not None
                and (not self.llm_hf_only or agent.is_historical_figure)
                and self.rng.random() < self.llm_chance
            )
            if use_llm:
                try:
                    dest = self.llm_advisor.suggest(agent, self.world, candidates)
                except Exception:
                    dest = None

            if dest is None:
                # Friend pull — overrides tile affinity with some probability
                friend_tiles = set(self._friend_tiles(agent))
                friend_cands = [(t, w) for t, w in candidates if t in friend_tiles]
                if friend_cands and self.rng.random() < self.friend_pull:
                    dest = self._weighted_choice(friend_cands)
                else:
                    dest = self._weighted_choice(candidates)

            from_tile = agent.current_tile
            self._move_agent(agent, dest)
            moves.append((agent.agent_id, from_tile, dest))
        return moves
