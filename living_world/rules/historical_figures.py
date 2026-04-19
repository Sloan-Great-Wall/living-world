"""Historical Figure promotion/demotion — Dwarf Fortress style.

Keep only a small fraction of agents in 'fine-grained simulation' mode. The rest
are ambient NPCs that respond only when the storyteller names them.

Promotion triggers:
  - Participated in a spotlight-level event (importance >= 0.6)
  - Accumulated N notable events (importance >= 0.3)
  - Forged a strong relationship (|affinity| >= 70)

Demotion:
  - No activity for M virtual days
  - Is ordinary (i.e. not seeded as historical) and slipped below activity floor
"""

from __future__ import annotations

from dataclasses import dataclass

from living_world.core.agent import Agent
from living_world.core.event import LegendEvent
from living_world.core.world import World


@dataclass
class PromotionConfig:
    spotlight_threshold: float = 0.6
    notable_threshold: float = 0.3
    notable_count_for_promotion: int = 3
    strong_relationship_affinity: int = 70
    inactivity_days_for_demotion: int = 30


class HistoricalFigureRegistry:
    """Track activity-based promotion/demotion of historical figures."""

    def __init__(self, world: World, config: PromotionConfig | None = None) -> None:
        self.world = world
        self.config = config or PromotionConfig()
        self._notable_counts: dict[str, int] = {}
        self._last_seen: dict[str, int] = {}

    def observe_event(self, event: LegendEvent) -> list[str]:
        """Called by tick engine after each realized event.
        Returns agent_ids newly promoted this tick.
        """
        promoted: list[str] = []
        for aid in event.participants:
            self._last_seen[aid] = event.tick
            if event.importance >= self.config.notable_threshold:
                self._notable_counts[aid] = self._notable_counts.get(aid, 0) + 1

            agent = self.world.get_agent(aid)
            if agent is None or agent.is_historical_figure:
                continue

            # Spotlight event: instant promotion
            if event.importance >= self.config.spotlight_threshold:
                agent.is_historical_figure = True
                promoted.append(aid)
                continue

            # Notable event accumulation
            if self._notable_counts.get(aid, 0) >= self.config.notable_count_for_promotion:
                agent.is_historical_figure = True
                promoted.append(aid)

            # Strong relationship check
            for rel in agent.relationships.values():
                if abs(rel.affinity) >= self.config.strong_relationship_affinity:
                    agent.is_historical_figure = True
                    promoted.append(aid)
                    break

        return promoted

    def demote_inactive(self, current_tick: int) -> list[str]:
        """Called periodically (e.g. every 7 virtual days)."""
        demoted: list[str] = []
        cutoff = current_tick - self.config.inactivity_days_for_demotion
        for agent in self.world.all_agents():
            if not agent.is_historical_figure:
                continue
            # Don't demote seeded historical figures (always important)
            # Heuristic: if agent's age is high or tagged permanent, skip
            if "permanent_historical" in agent.tags:
                continue
            last = self._last_seen.get(agent.agent_id, agent.created_at_tick)
            if last < cutoff:
                agent.is_historical_figure = False
                demoted.append(agent.agent_id)
        return demoted

    def summary(self) -> dict[str, int]:
        total = sum(1 for a in self.world.all_agents() if a.is_alive())
        hf = sum(
            1 for a in self.world.all_agents() if a.is_alive() and a.is_historical_figure
        )
        return {"total_alive": total, "historical_figures": hf, "ordinary": total - hf}
