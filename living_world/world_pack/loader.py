"""Load a world_packs/<id>/ directory into runtime objects."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field

from living_world.core.agent import Agent, Item, LifeStage, Relationship
from living_world.core.tile import Tile


class StorytellerConfig(BaseModel):
    personality: str = "balanced"  # balanced | peaceful | chaotic
    tension_target: float = 0.5
    max_events_per_day: int = 3
    narration_tone: str = ""  # free-form hint passed to Tier 2/3 prompt


class PackManifest(BaseModel):
    """Parsed `pack.yaml`."""

    pack_id: str
    display_name: str
    description: str = ""
    narrative_style: str = ""  # "scp report format" / "gothic prose" / "文言白话"
    storyteller: StorytellerConfig = Field(default_factory=StorytellerConfig)


class EventTemplate(BaseModel):
    """One entry in events/*.yaml."""

    event_kind: str
    description: str = ""
    trigger_conditions: dict[str, Any] = Field(default_factory=dict)
    dice_roll: dict[str, Any] = Field(default_factory=dict)  # {"stat":"charm","dc":12,"mod":0}
    outcomes: dict[str, dict[str, Any]] = Field(default_factory=dict)
    # outcomes["success"] = {"stat_changes": {...}, "template": "..."}
    cooldown_days: int = 0
    base_importance: float = 0.1


class WorldPack:
    """A loaded world pack — personas + events + tiles + storyteller config."""

    def __init__(
        self,
        manifest: PackManifest,
        personas: list[Agent],
        events: dict[str, EventTemplate],
        tiles: list[Tile],
        root: Path,
    ) -> None:
        self.manifest = manifest
        self.personas = personas
        self.events = events
        self.tiles = tiles
        self.root = root

    @property
    def pack_id(self) -> str:
        return self.manifest.pack_id


def _load_yaml(p: Path) -> Any:
    if not p.exists():
        return None
    with p.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def _parse_persona(raw: dict[str, Any], pack_id: str) -> Agent:
    """Parse personas/*.yaml entry into an Agent record."""
    rels: dict[str, Relationship] = {}
    for rel_raw in raw.get("relationships", []) or []:
        r = Relationship(**rel_raw)
        rels[r.target_id] = r
    items = [Item(**i) for i in raw.get("inventory", []) or []]
    return Agent(
        agent_id=raw["agent_id"],
        pack_id=pack_id,
        display_name=raw.get("display_name", raw["agent_id"]),
        persona_card=raw.get("persona_card", ""),
        is_historical_figure=bool(raw.get("is_historical_figure", False)),
        attributes=raw.get("attributes", {}) or {},
        alignment=raw.get("alignment", "neutral"),
        tags=set(raw.get("tags", []) or []),
        life_stage=LifeStage(raw.get("life_stage", "prime")),
        age=int(raw.get("age", 20)),
        current_tile=raw.get("current_tile", ""),
        current_goal=raw.get("current_goal"),
        inventory=items,
        relationships=rels,
        state_extra=raw.get("state_extra", {}) or {},
    )


def load_pack(path: Path) -> WorldPack:
    """Load one pack directory. Missing optional files are OK; manifest is required."""
    path = Path(path).resolve()
    manifest_raw = _load_yaml(path / "pack.yaml")
    if manifest_raw is None:
        raise FileNotFoundError(f"pack.yaml missing in {path}")
    manifest = PackManifest(**manifest_raw)

    personas: list[Agent] = []
    persona_dir = path / "personas"
    if persona_dir.exists():
        for f in sorted(persona_dir.glob("*.yaml")):
            raw = _load_yaml(f)
            if raw:
                personas.append(_parse_persona(raw, manifest.pack_id))

    events: dict[str, EventTemplate] = {}
    events_dir = path / "events"
    if events_dir.exists():
        for f in sorted(events_dir.glob("*.yaml")):
            raw = _load_yaml(f) or {}
            for ev in raw.get("events", []) or []:
                t = EventTemplate(**ev)
                events[t.event_kind] = t

    tiles: list[Tile] = []
    tiles_dir = path / "tiles"
    if tiles_dir.exists():
        for f in sorted(tiles_dir.glob("*.yaml")):
            raw = _load_yaml(f) or {}
            for tl in raw.get("tiles", []) or []:
                tiles.append(Tile(**tl))

    return WorldPack(manifest, personas, events, tiles, path)


def load_all_packs(base: Path, pack_ids: list[str]) -> list[WorldPack]:
    """Load the requested packs from a base directory."""
    base = Path(base).resolve()
    out = []
    for pid in pack_ids:
        p = base / pid
        if not p.exists():
            raise FileNotFoundError(f"pack directory not found: {p}")
        out.append(load_pack(p))
    return out
