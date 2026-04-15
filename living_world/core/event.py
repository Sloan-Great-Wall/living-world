"""Event proposals (from Storyteller) and realized legend events (post stat-machine)."""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class Importance(float, Enum):
    """Thresholds for tier routing — see stat-machine-design.md."""

    TIER1_ONLY = 0.0
    TIER2_THRESHOLD = 0.2
    TIER3_THRESHOLD = 0.6


class EventProposal(BaseModel):
    """
    Storyteller's 'maybe this should happen today' candidate.
    Stat machine decides whether to realize it via dice roll + stakeholder checks.
    """

    proposal_id: str
    pack_id: str
    tile_id: str
    event_kind: str  # matches an entry in pack's events/*.yaml
    priority: float = 0.5  # 0..1, storyteller's preference
    required_tags: list[str] = Field(default_factory=list)  # stakeholder filter
    context: dict[str, Any] = Field(default_factory=dict)


class LegendEvent(BaseModel):
    """
    A realized event — what actually happened. Append-only.
    The raw struct feeds Tier 2 enhancement and Tier 3 reflection.
    """

    event_id: str
    tick: int
    pack_id: str
    tile_id: str
    event_kind: str
    participants: list[str]  # agent_ids
    outcome: str  # "success" | "failure" | "neutral" | custom
    stat_changes: dict[str, dict[str, float]] = Field(default_factory=dict)
    # stat_changes[agent_id]["attribute_name"] = delta

    relationship_changes: list[dict[str, Any]] = Field(default_factory=list)
    # [{"a": id, "b": id, "delta": int}, ...]

    # narrative rendering
    template_rendering: str = ""  # Tier 1 template output
    enhanced_rendering: str | None = None  # Tier 2 output, if importance >= 0.2
    spotlight_rendering: str | None = None  # Tier 3 output, if importance >= 0.6

    importance: float = 0.0  # computed by score_event_importance()
    tier_used: int = 1  # 1 | 2 | 3, for observability

    def best_rendering(self) -> str:
        """Return the highest-tier narrative available."""
        return self.spotlight_rendering or self.enhanced_rendering or self.template_rendering
