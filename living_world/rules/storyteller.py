"""Per-tile Storyteller. Decides which event candidates should be proposed this tick,
based on: tension curve, cooldowns, tile/pack bias, and storyteller personality.

Core ideas borrowed from RimWorld's Cassandra/Phoebe/Randy storytellers:
- Alternate tension and rest
- Respect cooldowns so same event doesn't flood
- Personality-tuned curves
"""

from __future__ import annotations

import random
import uuid
from dataclasses import dataclass, field

from living_world.core.event import EventProposal
from living_world.core.tile import Tile
from living_world.world_pack import EventTemplate, StorytellerConfig


@dataclass
class TensionState:
    """Sliding window of recent event density per tile."""

    recent_days: list[int] = field(default_factory=list)  # days with events, length N
    window_size: int = 7

    def push(self, events_today: int) -> None:
        self.recent_days.append(events_today)
        if len(self.recent_days) > self.window_size:
            self.recent_days.pop(0)

    def current(self) -> float:
        if not self.recent_days:
            return 0.0
        return sum(self.recent_days) / max(1, len(self.recent_days) * 3.0)


class TileStoryteller:
    """
    One storyteller per tile. Asks: 'what should happen here today?'

    Outputs 0..N EventProposals for the stat machine to realize or drop.
    """

    def __init__(
        self,
        tile: Tile,
        config: StorytellerConfig,
        event_pool: dict[str, EventTemplate],
        rng: random.Random | None = None,
    ) -> None:
        self.tile = tile
        self.config = config
        self.event_pool = event_pool
        self.rng = rng or random.Random()
        self.tension = TensionState()
        # Phase E: optional goal-alignment hooks. Factory sets these when
        # wiring up the engine; plain TickEngine usage leaves them None and
        # the behavior is identical to before.
        # `World` typed as Any to avoid circular import; the read sites
        # all guard `if self.world is None` first.
        from typing import Any as _Any

        self.world: _Any = None
        self.goal_bonus: float = 1.0

    # Words carrying no signal. Keep in sync with movement._GOAL_STOPWORDS
    # (duplicated so this module stays standalone).
    _GOAL_STOPWORDS: frozenset[str] = frozenset(
        {
            "the",
            "a",
            "an",
            "to",
            "of",
            "in",
            "on",
            "at",
            "for",
            "with",
            "from",
            "by",
            "and",
            "or",
            "but",
            "is",
            "are",
            "was",
            "were",
            "be",
            "been",
            "do",
            "does",
            "did",
            "have",
            "has",
            "had",
            "will",
            "would",
            "should",
            "i",
            "me",
            "my",
            "you",
            "your",
            "he",
            "she",
            "it",
            "we",
            "they",
            "find",
            "get",
            "go",
            "come",
            "see",
            "make",
            "take",
            "some",
            "any",
        }
    )

    def _resident_goal_tokens(self) -> set[str]:
        """Collect goal + weekly-plan tokens from every agent currently in the tile."""
        if self.world is None or self.goal_bonus <= 1.0:
            return set()
        tokens: set[str] = set()
        for aid in self.tile.resident_agents:
            agent = self.world.get_agent(aid)
            if agent is None or not agent.is_alive():
                continue
            bag: list[str] = []
            if agent.current_goal:
                bag.append(agent.current_goal)
            plan = agent.get_weekly_plan() if hasattr(agent, "get_weekly_plan") else {}
            for key in ("goals_this_week", "seek"):
                items = plan.get(key) if isinstance(plan, dict) else None
                if isinstance(items, list):
                    bag.extend(str(x) for x in items)
            for blob in bag:
                for raw in str(blob).lower().split():
                    w = "".join(c for c in raw if c.isalnum() or c == "-")
                    if len(w) > 2 and w not in self._GOAL_STOPWORDS:
                        tokens.add(w)
        return tokens

    def _alignment_multiplier(self, tpl: EventTemplate, tokens: set[str]) -> float:
        """Multiplier ≥1.0 when template kind/description hits any resident goal token."""
        if not tokens:
            return 1.0
        hay = (tpl.event_kind + " " + (tpl.description or "")).lower()
        for w in tokens:
            if w in hay:
                return self.goal_bonus
        return 1.0

    def _personality_factor(self) -> float:
        """Personality shifts how often we trigger events."""
        return {
            "peaceful": 0.35,
            "balanced": 0.7,
            "chaotic": 1.1,
        }.get(self.config.personality, 0.7)

    def _pick_candidates(self, n: int, tick: int) -> list[EventTemplate]:
        """Weighted random pick respecting cooldowns."""
        available: list[EventTemplate] = []
        for kind, tpl in self.event_pool.items():
            cd_until = self.tile.event_cooldowns.get(kind, 0)
            if cd_until > tick:
                continue
            available.append(tpl)
        if not available:
            return []
        # weight by priority, with optional goal-alignment boost (Phase E).
        # When world is wired in, events whose kind/description mention a
        # token from any resident agent's goal or weekly_plan get bumped.
        tokens = self._resident_goal_tokens()
        weights = [
            max(0.05, tpl.base_importance + 0.05) * self._alignment_multiplier(tpl, tokens)
            for tpl in available
        ]
        picked: list[EventTemplate] = []
        remaining = list(zip(available, weights, strict=True))
        for _ in range(min(n, len(available))):
            total = sum(w for _, w in remaining)
            r = self.rng.uniform(0, total)
            acc = 0.0
            for i, (tpl, w) in enumerate(remaining):
                acc += w
                if r <= acc:
                    picked.append(tpl)
                    remaining.pop(i)
                    break
        return picked

    def tick_daily(self, tick: int) -> list[EventProposal]:
        """Called once per virtual day per tile."""
        current_t = self.tension.current()
        pressure = self.config.tension_target - current_t
        # if above target, give breathing room
        if pressure < -0.2:
            self.tension.push(0)
            return []

        raw = self._personality_factor() * (1.0 + max(0.0, pressure))
        # probabilistic rounding so a peaceful 0.49 still fires ~half the time
        base_count = int(raw) + (1 if self.rng.random() < (raw - int(raw)) else 0)
        num = max(0, min(self.config.max_events_per_day, base_count))
        if num == 0:
            self.tension.push(0)
            return []

        picked = self._pick_candidates(num, tick)
        proposals: list[EventProposal] = []
        for tpl in picked:
            proposals.append(
                EventProposal(
                    proposal_id=str(uuid.uuid4()),
                    pack_id=self.tile.primary_pack,
                    tile_id=self.tile.tile_id,
                    event_kind=tpl.event_kind,
                    priority=tpl.base_importance,
                    required_tags=list(tpl.trigger_conditions.get("required_tags", []) or []),
                    context={"template": tpl.model_dump()},
                )
            )
            if tpl.cooldown_days > 0:
                self.tile.event_cooldowns[tpl.event_kind] = tick + tpl.cooldown_days
        self.tension.push(len(proposals))
        return proposals
