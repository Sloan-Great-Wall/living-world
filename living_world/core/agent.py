"""Unified Agent schema — works across SCP / Cthulhu / Liaozhai packs."""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class LifeStage(StrEnum):
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
    # Cross-pack bridge: pack_id may CHANGE if the agent migrates into
    # another world (e.g. fox-spirit ends up in an SCP corridor), but
    # pack_origin records where they were originally authored. Used by
    # narrator + chronicler to keep the character's voice grounded in
    # their home mythology even when they're somewhere alien.
    pack_origin: str | None = None  # defaults to pack_id at bootstrap

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
    x: float = 0.0  # position within tile (or world, for continuous map)
    y: float = 0.0
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

    # ── Beliefs (stored in state_extra so no schema change) ──
    # Convention: state_extra["beliefs"] is a dict[str, str] mapping
    # topic/agent-id to a terse belief sentence. These are evolved by the
    # dialogue loop and other LLM-driven pathways.

    def get_beliefs(self) -> dict[str, str]:
        beliefs = self.state_extra.get("beliefs")
        if not isinstance(beliefs, dict):
            return {}
        return beliefs

    def set_belief(self, topic: str, belief: str) -> None:
        if not topic or not belief:
            return
        beliefs = self.state_extra.setdefault("beliefs", {})
        beliefs[topic] = belief[:200]  # clamp to something sensible

    def get_weekly_plan(self) -> dict:
        plan = self.state_extra.get("weekly_plan")
        return plan if isinstance(plan, dict) else {}

    # ── Internal mind: needs / emotions / motivations ──
    # Following AgentSociety's structured-mind model. Stored in state_extra
    # to avoid schema migration; promoted to first-class fields if they stay.
    #
    # needs:       Maslow-like drives, decay/grow over time, in [0, 100].
    #              hunger / safety / belonging / esteem / autonomy.
    # emotions:    short-half-life affect, in [0, 100]. Decays toward
    #              baseline. fear / joy / anger / sadness / surprise.
    # motivations: short text strings — current driving urges, set by LLM.

    # Slimmed from 5/5 to 2/3 — only the dimensions actually consumed by
    # downstream code remain. Trim history: belonging / esteem / autonomy
    # / sadness / surprise had no readers. Hunger drives daily routine,
    # safety drives danger reactions; fear/joy/anger drive social tone.
    _DEFAULT_NEEDS = {"hunger": 30.0, "safety": 70.0}
    _DEFAULT_EMOTIONS = {"fear": 0.0, "joy": 30.0, "anger": 0.0}

    def get_needs(self) -> dict[str, float]:
        n = self.state_extra.get("needs")
        if not isinstance(n, dict):
            n = dict(self._DEFAULT_NEEDS)
            self.state_extra["needs"] = n
        return n

    def get_emotions(self) -> dict[str, float]:
        e = self.state_extra.get("emotions")
        if not isinstance(e, dict):
            e = dict(self._DEFAULT_EMOTIONS)
            self.state_extra["emotions"] = e
        return e

    def get_motivations(self) -> list[str]:
        m = self.state_extra.get("motivations")
        return m if isinstance(m, list) else []

    def adjust_need(self, key: str, delta: float) -> None:
        needs = self.get_needs()
        needs[key] = max(0.0, min(100.0, needs.get(key, 50.0) + delta))

    def adjust_emotion(self, key: str, delta: float) -> None:
        emotions = self.get_emotions()
        emotions[key] = max(0.0, min(100.0, emotions.get(key, 0.0) + delta))
