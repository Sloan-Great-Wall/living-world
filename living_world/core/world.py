"""World — in-memory snapshot of every agent, tile, and event log.

Stage A starts with this in-memory implementation. S1.5 task swaps the backend
to PostgreSQL + Redis without changing the public API.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Iterable

from living_world.core.agent import Agent
from living_world.core.event import LegendEvent
from living_world.core.tile import Tile


class World:
    """In-memory world state. Single source of truth for tick loop + dashboard."""

    def __init__(self, current_tick: int = 0) -> None:
        self.current_tick: int = current_tick
        self._agents: dict[str, Agent] = {}
        self._tiles: dict[str, Tile] = {}
        self._events: list[LegendEvent] = []
        self._loaded_packs: list[str] = []

    # ---- agents ----
    def add_agent(self, agent: Agent) -> None:
        self._agents[agent.agent_id] = agent
        if agent.current_tile and agent.current_tile in self._tiles:
            tile = self._tiles[agent.current_tile]
            if agent.agent_id not in tile.resident_agents:
                tile.resident_agents.append(agent.agent_id)

    def get_agent(self, agent_id: str) -> Agent | None:
        return self._agents.get(agent_id)

    def all_agents(self) -> Iterable[Agent]:
        return self._agents.values()

    def living_agents(self) -> Iterable[Agent]:
        return (a for a in self._agents.values() if a.is_alive())

    def historical_figures(self) -> Iterable[Agent]:
        return (a for a in self._agents.values() if a.is_historical_figure and a.is_alive())

    def agents_in_tile(self, tile_id: str) -> list[Agent]:
        return [self._agents[aid] for aid in self._tiles[tile_id].resident_agents
                if aid in self._agents and self._agents[aid].is_alive()]

    def agents_by_pack(self) -> dict[str, list[Agent]]:
        out: dict[str, list[Agent]] = defaultdict(list)
        for a in self._agents.values():
            out[a.pack_id].append(a)
        return dict(out)

    # ---- tiles ----
    def add_tile(self, tile: Tile) -> None:
        self._tiles[tile.tile_id] = tile

    def get_tile(self, tile_id: str) -> Tile | None:
        return self._tiles.get(tile_id)

    def all_tiles(self) -> Iterable[Tile]:
        return self._tiles.values()

    # ---- events ----
    def record_event(self, event: LegendEvent) -> None:
        self._events.append(event)

    def events_since(self, tick: int, pack_id: str | None = None) -> list[LegendEvent]:
        out = [e for e in self._events if e.tick >= tick]
        if pack_id:
            out = [e for e in out if e.pack_id == pack_id]
        return out

    def event_count(self) -> int:
        return len(self._events)

    # ---- packs ----
    def mark_pack_loaded(self, pack_id: str) -> None:
        if pack_id not in self._loaded_packs:
            self._loaded_packs.append(pack_id)

    @property
    def loaded_packs(self) -> list[str]:
        return list(self._loaded_packs)

    # ---- stats ----
    def summary(self) -> dict[str, int]:
        return {
            "tick": self.current_tick,
            "packs": len(self._loaded_packs),
            "tiles": len(self._tiles),
            "agents_total": len(self._agents),
            "agents_alive": sum(1 for a in self._agents.values() if a.is_alive()),
            "historical_figures": sum(
                1 for a in self._agents.values() if a.is_historical_figure and a.is_alive()
            ),
            "events_logged": len(self._events),
        }
