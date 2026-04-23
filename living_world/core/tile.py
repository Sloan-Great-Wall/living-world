"""Tile — the spatial unit of the world. In Stage A it's purely virtual (no GPS binding)."""

from __future__ import annotations

from pydantic import BaseModel, Field


class Tile(BaseModel):
    """
    A location in the world with a 2D center + radius.
    Agents whose current_tile matches are rendered within this region.
    Stage C will bind to real-world coordinates; Stage A uses virtual layout.
    """

    tile_id: str
    display_name: str
    primary_pack: str
    tile_type: str
    description: str = ""

    # 2D world position — center of this location
    x: float = 0.0
    y: float = 0.0
    radius: float = 50.0  # visual bounding circle

    # pack access control
    allowed_packs: list[str] = Field(default_factory=list)
    # Cross-pack bridge (KNOWN_ISSUES #7). A liminal tile is shared
    # across all loaded packs — agents from different worlds can meet
    # here. Migration events (e.g. scp:portal-anomaly,
    # liaozhai:dream-passage, cthulhu:dream-call) deposit agents into a
    # liminal tile; from there they can interact regardless of origin.
    is_liminal: bool = False

    # storyteller tuning
    tension_bias: float = 0.5
    event_cooldowns: dict[str, int] = Field(default_factory=dict)

    # populated at runtime
    resident_agents: list[str] = Field(default_factory=list)
