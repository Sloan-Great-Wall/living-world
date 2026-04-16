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

    # storyteller tuning
    tension_bias: float = 0.5
    event_cooldowns: dict[str, int] = Field(default_factory=dict)

    # populated at runtime
    resident_agents: list[str] = Field(default_factory=list)
