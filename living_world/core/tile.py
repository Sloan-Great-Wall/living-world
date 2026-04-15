"""Tile — the spatial unit of the world. In Stage A it's purely virtual (no GPS binding)."""

from __future__ import annotations

from pydantic import BaseModel, Field


class Tile(BaseModel):
    """
    A location anchor. Stage A: virtual grid; Stage C: binds to H3 cell.

    A tile belongs to one primary pack (by tile_type origin) but can host
    agents from multiple packs when running in mixed mode.
    """

    tile_id: str
    display_name: str
    primary_pack: str  # scp / cthulhu / liaozhai — the "native" flavor of this tile
    tile_type: str  # "containment-chamber" / "dockside" / "market-street" / ...
    description: str = ""

    # which packs are allowed to spawn agents here (for mixed-mode control)
    allowed_packs: list[str] = Field(default_factory=list)

    # storyteller tuning per-tile
    tension_bias: float = 0.5  # 0 = peaceful, 1 = chaotic
    event_cooldowns: dict[str, int] = Field(default_factory=dict)
    # event_cooldowns[event_kind] = tick until allowed again

    # populated at runtime
    resident_agents: list[str] = Field(default_factory=list)
