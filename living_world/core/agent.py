"""Unified Agent schema — works across SCP / Cthulhu / Liaozhai packs."""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class LifeStage(str, Enum):
    CHILD = "child"
    YOUNG = "young"
    PRIME = "prime"
    ELDER = "elder"
    DECEASED = "deceased"


class Relationship(BaseModel):
    """Per-pair directed relationship. Good feelings can be asymmetric."""

    target_id: str
    affinity: int = 0  # -100..100
    kind: str = "acquaintance"  # kin/master/disciple/lover/rival/enemy/...
    last_interaction_tick: int = 0


class Item(BaseModel):
    """Structured inventory entry with tag-based modifiers."""

    name: str
    tags: list[str] = Field(default_factory=list)  # ["weapon", "cursed", "heirloom"]
    power: int = 0
    origin_event_id: str | None = None


class Agent(BaseModel):
    """
    Canonical agent record. The stat-machine tick reads/writes this struct;
    LLM tiers consume it as context. All worldview-specific fields go into
    `tags` / `attributes` / `state_extra` rather than being hardcoded here.
    """

    # identity
    agent_id: str
    pack_id: str  # "scp" | "cthulhu" | "liaozhai"
    display_name: str
    persona_card: str  # < 500 chars, written in target-language tone

    # bucketed rank
    is_historical_figure: bool = False

    # attributes — open dict, each pack defines its own keys
    # e.g. scp: {"containment_class": "Euclid", "threat": 70}
    #      cthulhu: {"sanity": 60, "arcane_knowledge": 40}
    #      liaozhai: {"cultivation": 30, "charm": 80}
    attributes: dict[str, int | float | str] = Field(default_factory=dict)

    # generic dimensions used by every pack
    alignment: str = "neutral"  # lawful_good / neutral / chaotic_evil / ...
    tags: set[str] = Field(default_factory=set)

    # state
    life_stage: LifeStage = LifeStage.PRIME
    age: int = 20
    current_tile: str = ""
    current_goal: str | None = None
    inventory: list[Item] = Field(default_factory=list)
    relationships: dict[str, Relationship] = Field(default_factory=dict)

    # any pack-specific dynamic blob that doesn't fit above
    state_extra: dict[str, Any] = Field(default_factory=dict)

    # bookkeeping (not for LLM, for engine)
    last_tick: int = 0
    created_at_tick: int = 0

    def is_alive(self) -> bool:
        return self.life_stage != LifeStage.DECEASED

    def get_affinity(self, other_id: str) -> int:
        rel = self.relationships.get(other_id)
        return rel.affinity if rel else 0

    def adjust_affinity(self, other_id: str, delta: int, tick: int) -> None:
        rel = self.relationships.get(other_id)
        if rel is None:
            rel = Relationship(target_id=other_id, last_interaction_tick=tick)
            self.relationships[other_id] = rel
        rel.affinity = max(-100, min(100, rel.affinity + delta))
        rel.last_interaction_tick = tick
