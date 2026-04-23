"""Typed Pydantic response schemas for the FastAPI sim API.

These are the SINGLE source of truth for the cross-layer contract
(AI-Native criterion A — compile-time strict at boundaries):

  Python (here)  ──►  OpenAPI JSON  ──►  openapi-ts  ──►  TS types

Any field added/renamed/removed here flows through the whole chain:
Python dev re-runs `make schema`, dashboard `tsc --noEmit` immediately
red-lines every stale usage. No more hand-synced TS types drifting from
the Python that serves them.

Style rules (stable — please keep):
  - Every field camelCase. Pydantic auto-serialises snake_case attrs via
    `populate_by_name=True` + alias on the few fields we can't rename
    cleanly. But new fields: camelCase from the start.
  - Optional fields end with `| None`; prefer `None` default over `Field(default=None)`
    unless a description is needed.
  - Never return `dict` / `list[dict]` from a route — always a model or
    `list[Model]`. Untyped dicts become `Any` in OpenAPI and AI can't
    reason about the shape.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

# ── Top-bar ────────────────────────────────────────────────────────────────


class DiversitySummary(BaseModel):
    total: int
    unique: int
    top_kind: str | None = None
    top_pct: float


class WorldSnapshot(BaseModel):
    loaded: bool
    tick: int
    packs: list[str]
    agentsAlive: int
    agentsTotal: int
    eventsTotal: int
    deaths: int
    chapters: int
    tiles: int
    diversity: DiversitySummary | None = None
    modelTier2: str
    modelTier3: str


# ── Events & Agents ────────────────────────────────────────────────────────


Outcome = Literal["success", "failure", "neutral"]


class WorldEvent(BaseModel):
    id: str
    tick: int
    pack: str
    tile: str
    kind: str
    outcome: Outcome
    importance: float
    tier: int
    isEmergent: bool
    participants: list[str]
    narrative: str


class Relationship(BaseModel):
    target: str
    kind: str
    affinity: int


class Agent(BaseModel):
    id: str
    name: str
    pack: str
    alignment: str
    isHf: bool
    alive: bool
    tile: str
    x: float
    y: float
    tags: list[str]
    # Full-detail fields (populated only by /api/agent/{id})
    persona: str | None = None
    goal: str | None = None
    needs: dict[str, float] | None = None
    emotions: dict[str, float] | None = None
    attributes: dict[str, float | str] | None = None
    beliefs: dict[str, str] | None = None
    motivations: list[str] | None = None
    weeklyPlan: dict[str, list[str]] | None = None
    relationships: list[Relationship] | None = None
    recentEvents: list[WorldEvent] | None = None


# ── World geometry ─────────────────────────────────────────────────────────


class Tile(BaseModel):
    id: str
    name: str
    pack: str
    type: str
    x: float
    y: float


# ── Library / authored content ─────────────────────────────────────────────


class EventTemplateRow(BaseModel):
    pack: str
    eventKind: str
    description: str
    baseImportance: float
    source: str


class PersonaRow(BaseModel):
    id: str
    name: str
    pack: str
    alignment: str
    isHf: bool
    tags: list[str]
    persona: str


# ── Chronicler output ──────────────────────────────────────────────────────


class Chapter(BaseModel):
    tick: int
    pack_id: str = Field(..., alias="pack_id")  # kept snake for existing FE
    title: str
    body: str
    event_ids: list[str]

    model_config = {"populate_by_name": True}


class ChronicleMarkdown(BaseModel):
    markdown: str


# ── Feature flags / status ─────────────────────────────────────────────────


class FeatureStatus(BaseModel):
    name: str
    on: bool
    detail: str


# ── Social graph (thin projection for client-side sim-core) ────────────────


class SocialRelationship(BaseModel):
    targetId: str
    affinity: int


class SocialAgent(BaseModel):
    agentId: str
    packId: str
    alive: bool
    relationships: list[SocialRelationship]


class SocialGraph(BaseModel):
    agents: list[SocialAgent]


# ── Request bodies ─────────────────────────────────────────────────────────


class BootstrapBody(BaseModel):
    packs: list[str]
    seed: int = 42


class TickBody(BaseModel):
    n: int = 1


# ── Tiny ack shapes ────────────────────────────────────────────────────────


class Ok(BaseModel):
    ok: bool = True


class Health(BaseModel):
    ok: bool
    loaded: bool


# ── Events distribution (event_kinds endpoint) ─────────────────────────────
# The Python helper returns list[tuple[str, int]] — tuples are lossy in
# OpenAPI, wrap them properly here.


class EventKindCount(BaseModel):
    kind: str
    count: int
