"""Repository protocol — anything that can save/load world state."""

from __future__ import annotations

from typing import Protocol

from living_world.core.agent import Agent
from living_world.core.event import LegendEvent
from living_world.core.tile import Tile
from living_world.core.world import World


class Repository(Protocol):
    """Uniform interface for in-memory and database-backed persistence."""

    # ---- snapshot / restore ----
    def save_world(self, world: World) -> None:
        ...

    def load_world(self) -> World | None:
        """Return None if no world has been persisted yet."""
        ...

    # ---- incremental writes (event log) ----
    def append_event(self, event: LegendEvent) -> None:
        ...

    # ---- targeted writes ----
    def upsert_agent(self, agent: Agent) -> None:
        ...

    def upsert_tile(self, tile: Tile) -> None:
        ...

    def update_current_tick(self, tick: int) -> None:
        ...

    # ---- queries ----
    def list_events(self, *, since_tick: int = 0, pack_id: str | None = None, limit: int = 1000) -> list[LegendEvent]:
        ...

    def close(self) -> None:
        ...
