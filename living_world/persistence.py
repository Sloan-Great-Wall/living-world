"""Persistence layer — Repository protocol + in-memory and Postgres impls.

Default: MemoryRepository (no external deps, lives within process).
Postgres: pgvector-backed, requires `pip install -e '.[db]'`.
"""

from __future__ import annotations

import json
import uuid
from typing import Any, Protocol

from living_world.core.agent import Agent, Item, LifeStage, Relationship
from living_world.core.event import LegendEvent
from living_world.core.tile import Tile
from living_world.core.world import World


class Repository(Protocol):
    """Uniform interface for in-memory and database-backed persistence."""

    def save_world(self, world: World) -> None: ...
    def load_world(self) -> World | None: ...
    def append_event(self, event: LegendEvent) -> None: ...
    def upsert_agent(self, agent: Agent) -> None: ...
    def upsert_tile(self, tile: Tile) -> None: ...
    def update_current_tick(self, tick: int) -> None: ...
    def list_events(
        self, *, since_tick: int = 0, pack_id: str | None = None, limit: int = 1000
    ) -> list[LegendEvent]: ...
    def close(self) -> None: ...


# ────────────────────────────────────────────────────────────────
# In-memory (default)
# ────────────────────────────────────────────────────────────────

class MemoryRepository:
    """Trivial in-memory repository — default backend for tests & single-session runs."""

    def __init__(self) -> None:
        self._world: World | None = None

    def save_world(self, world: World) -> None:
        self._world = world

    def load_world(self) -> World | None:
        return self._world

    def append_event(self, event: LegendEvent) -> None:
        if self._world is not None:
            self._world.record_event(event)

    def upsert_agent(self, agent: Agent) -> None:
        if self._world is not None:
            self._world.add_agent(agent)

    def upsert_tile(self, tile: Tile) -> None:
        if self._world is not None:
            self._world.add_tile(tile)

    def update_current_tick(self, tick: int) -> None:
        if self._world is not None:
            self._world.current_tick = tick

    def list_events(
        self, *, since_tick: int = 0, pack_id: str | None = None, limit: int = 1000
    ) -> list[LegendEvent]:
        if self._world is None:
            return []
        return self._world.events_since(since_tick, pack_id)[:limit]

    def close(self) -> None:
        pass

