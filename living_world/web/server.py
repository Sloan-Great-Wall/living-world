"""FastAPI sim API for the Tauri dashboard.

Every route declares a `response_model` pointing at `living_world.web.schemas`.
That schema is the SINGLE source of truth for the cross-layer contract:

    Python Pydantic ─► OpenAPI JSON ─► openapi-ts ─► TS types

Run `make schema` to regenerate both `api-schema/openapi.json` and the
TS types under `dashboard-tauri/src/types/api.generated.ts`. Any field
rename on this side will red-line the dashboard at `tsc --noEmit` time.

ENDPOINTS
---------
GET  /api/world              world snapshot / top-bar stats
GET  /api/feature_status     which LLM modules are wired
GET  /api/agents             agent list (lightweight)
GET  /api/agent/{id}         full agent detail
GET  /api/tiles              tile list
GET  /api/events             recent events
GET  /api/chronicle          chapter list
GET  /api/social_graph       thin projection for client-side sim-core
GET  /api/settings           current settings dict
POST /api/settings           patch settings
GET  /api/packs_available    which packs the user can load
GET  /api/templates          authored event templates
GET  /api/personas           authored personas
POST /api/bootstrap          create a new world  body: {packs:[...], seed:int}
POST /api/tick               advance N ticks    body: {n:int}
POST /api/reset              drop the loaded world

Aggregations the dashboard used to fetch (event_kinds, chronicle.md,
WorldSnapshot.diversity) are now computed client-side via
@living-world/sim-core. The server stays a thin data tap.

Single shared engine instance (Stage A single-user model). Re-bootstrap
discards the previous world.
"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from living_world import PACKS_DIR
from living_world.config import load_settings
from living_world.factory import bootstrap_world, make_engine
from living_world.queries import feature_status
from living_world.web.schemas import (
    Agent,
    BootstrapBody,
    Chapter,
    EventTemplateRow,
    FeatureStatus,
    Health,
    Ok,
    PersonaRow,
    Relationship,
    SocialAgent,
    SocialGraph,
    SocialRelationship,
    TickBody,
    Tile,
    WorldEvent,
    WorldSnapshot,
)


class _State:
    world: Any = None
    engine: Any = None
    loaded_packs: list[str] = []
    settings = load_settings()


STATE = _State()


def _need_engine() -> None:
    if STATE.engine is None:
        raise HTTPException(409, "No world loaded. POST /api/bootstrap first.")


# ── Typed builders (operate on sim objects, return Pydantic models) ─────────
# These replace the old _agent_dict / _event_dict / _tile_dict helpers that
# returned raw dicts. Shape is now enforced at runtime by Pydantic AND at
# compile time by openapi-ts in the dashboard. See schemas.py for the
# camelCase convention rationale.


def _build_event(e: Any) -> WorldEvent:
    return WorldEvent(
        id=e.event_id,
        tick=e.tick,
        pack=e.pack_id,
        tile=e.tile_id,
        kind=e.event_kind,
        outcome=e.outcome,
        importance=e.importance,
        tier=e.tier_used,
        isEmergent=e.is_emergent,
        participants=list(e.participants),
        narrative=e.best_rendering(),
    )


def _build_tile(t: Any) -> Tile:
    return Tile(
        id=t.tile_id,
        name=t.display_name,
        pack=t.primary_pack,
        type=t.tile_type,
        x=float(getattr(t, "x", 0.0)),
        y=float(getattr(t, "y", 0.0)),
    )


def _build_agent(a: Any, *, full: bool = False) -> Agent:
    base = {
        "id": a.agent_id,
        "name": a.display_name,
        "pack": a.pack_id,
        "alignment": a.alignment,
        "isHf": a.is_historical_figure,
        "alive": a.is_alive(),
        "tile": a.current_tile,
        "x": a.x,
        "y": a.y,
        "tags": sorted(a.tags),
    }
    if not full:
        return Agent(**base)
    base.update(
        {
            "persona": (a.persona_card or "").strip(),
            "goal": a.current_goal,
            "needs": a.get_needs(),
            "emotions": a.get_emotions(),
            "attributes": dict(a.attributes),
            "beliefs": a.get_beliefs(),
            "motivations": a.get_motivations(),
            "weeklyPlan": a.get_weekly_plan(),
            "relationships": [
                Relationship(target=r.target_id, kind=r.kind, affinity=r.affinity)
                for r in sorted(a.relationships.values(), key=lambda r: -abs(r.affinity))[:10]
            ],
        }
    )
    return Agent(**base)


def _build_world_snapshot() -> WorldSnapshot:
    if STATE.world is None:
        return WorldSnapshot(
            loaded=False,
            tick=0,
            packs=[],
            agentsAlive=0,
            agentsTotal=0,
            eventsTotal=0,
            deaths=0,
            chapters=0,
            tiles=0,
            modelTier2=STATE.settings.llm.ollama_tier2_model,
            modelTier3=STATE.settings.llm.ollama_tier3_model,
        )
    w = STATE.world
    return WorldSnapshot(
        loaded=True,
        tick=w.current_tick,
        packs=STATE.loaded_packs,
        agentsAlive=sum(1 for _ in w.living_agents()),
        agentsTotal=sum(1 for _ in w.all_agents()),
        eventsTotal=w.event_count(),
        deaths=sum(1 for a in w.all_agents() if not a.is_alive()),
        chapters=len(w.chapters),
        tiles=sum(1 for _ in w.all_tiles()),
        modelTier2=STATE.settings.llm.ollama_tier2_model,
        modelTier3=STATE.settings.llm.ollama_tier3_model,
    )


# ── App ────────────────────────────────────────────────────────────────────


def create_app() -> FastAPI:
    app = FastAPI(title="Living World API", version="0.1.0")
    # Permissive CORS for vite dev (1420) and Tauri webview
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.post("/api/bootstrap", response_model=WorldSnapshot)
    def bootstrap(payload: BootstrapBody) -> WorldSnapshot:
        if not payload.packs:
            raise HTTPException(400, "packs cannot be empty")
        world, loaded = bootstrap_world(PACKS_DIR, payload.packs)
        STATE.world = world
        STATE.engine = make_engine(world, loaded, STATE.settings, payload.seed)
        STATE.loaded_packs = payload.packs
        return _build_world_snapshot()

    @app.post("/api/tick", response_model=WorldSnapshot)
    def tick(payload: TickBody) -> WorldSnapshot:
        _need_engine()
        if payload.n < 1 or payload.n > 100:
            raise HTTPException(400, "n must be 1..100")
        STATE.engine.run(payload.n)
        return _build_world_snapshot()

    @app.get("/api/world", response_model=WorldSnapshot)
    def world() -> WorldSnapshot:
        return _build_world_snapshot()

    @app.get("/api/feature_status", response_model=list[FeatureStatus])
    def features() -> list[FeatureStatus]:
        _need_engine()
        return [
            FeatureStatus(name=fs.name, on=fs.on, detail=fs.detail)
            for fs in feature_status(STATE.engine)
        ]

    @app.get("/api/agents", response_model=list[Agent])
    def agents() -> list[Agent]:
        _need_engine()
        return [_build_agent(a) for a in STATE.world.all_agents()]

    @app.get("/api/agent/{agent_id}", response_model=Agent)
    def agent(agent_id: str) -> Agent:
        _need_engine()
        a = STATE.world.get_agent(agent_id)
        if a is None:
            raise HTTPException(404, f"unknown agent {agent_id}")
        out = _build_agent(a, full=True)
        out.recentEvents = [
            _build_event(e) for e in STATE.world.events_since(1) if agent_id in e.participants
        ][-15:]
        return out

    @app.get("/api/tiles", response_model=list[Tile])
    def tiles() -> list[Tile]:
        _need_engine()
        return [_build_tile(t) for t in STATE.world.all_tiles()]

    @app.get("/api/social_graph", response_model=SocialGraph)
    def social_graph() -> SocialGraph:
        """Lightweight projection for client-side social-metrics compute.

        Returns just (agentId, packId, alive, relationships) — exactly
        what `@living-world/sim-core` `computeSocialMetrics` consumes.
        Keeping the heavy computation client-side proves the TS port is
        a real consumer (not just an isomorphic re-implementation
        sitting unused). Server stays a thin data tap.
        """
        _need_engine()
        return SocialGraph(
            agents=[
                SocialAgent(
                    agentId=a.agent_id,
                    packId=a.pack_id,
                    alive=a.is_alive(),
                    relationships=[
                        SocialRelationship(targetId=r.target_id, affinity=int(r.affinity))
                        for r in a.relationships.values()
                    ],
                )
                for a in STATE.world.all_agents()
            ]
        )

    @app.get("/api/events", response_model=list[WorldEvent])
    def events(since: int = 1, limit: int = 80) -> list[WorldEvent]:
        _need_engine()
        evts = STATE.world.events_since(since)
        return [_build_event(e) for e in evts[-limit:]]

    @app.get("/api/chronicle", response_model=list[Chapter])
    def chronicle() -> list[Chapter]:
        _need_engine()
        # world.chapters is already a list[dict] with the right shape.
        return [Chapter(**c) for c in STATE.world.chapters]

    # NOTE: /api/event_kinds and /api/chronicle.md were removed in the
    # 2026-04-26 simplification audit. The dashboard now computes both
    # client-side via @living-world/sim-core (eventKindDistribution +
    # exportChronicleMarkdown) from a single /api/events + /api/chronicle
    # fetch — saving two HTTP routes + two Pydantic models. Server stays
    # a thin data tap; aggregation lives where the user is.

    @app.get("/api/settings")
    def settings_get() -> dict[str, Any]:
        """Settings shape is deep + dynamic — exposed as open dict for now.
        Typing it is a follow-up (one Pydantic model per section)."""
        return STATE.settings.model_dump()

    @app.post("/api/settings")
    def settings_set(payload: dict) -> dict[str, Any]:
        """Patch the live settings + persist to settings.yaml.

        Accepts a partial dict — only top-level sections present in the
        payload are merged. Returns the merged settings dict.

        NOTE: Most settings only take effect on next bootstrap (engine
        is built from settings at bootstrap time). Caller should
        prompt the user to Reset → Simulate again after important
        changes (model swap, packs, feature flags).
        """
        from living_world.config import Settings, save_settings

        current = STATE.settings.model_dump()
        for section, fields in payload.items():
            if isinstance(fields, dict) and isinstance(current.get(section), dict):
                current[section].update(fields)
            else:
                current[section] = fields
        try:
            new_settings = Settings(**current)
        except Exception as e:
            raise HTTPException(400, f"invalid settings: {e}") from e
        STATE.settings = new_settings
        save_settings(new_settings)
        return STATE.settings.model_dump()

    @app.post("/api/reset", response_model=Ok)
    def reset() -> Ok:
        """Drop the loaded world. The frontend should then re-call
        /api/bootstrap with the desired packs."""
        STATE.world = None
        STATE.engine = None
        STATE.loaded_packs = []
        return Ok()

    @app.get("/api/packs_available", response_model=list[str])
    def packs_available() -> list[str]:
        return sorted(
            p.name for p in PACKS_DIR.iterdir() if p.is_dir() and (p / "pack.yaml").exists()
        )

    @app.get("/api/templates", response_model=list[EventTemplateRow])
    def templates() -> list[EventTemplateRow]:
        """Expose loaded event TEMPLATES per pack — for Library 'Stories' tab."""
        _need_engine()
        out: list[EventTemplateRow] = []
        for pack_id, pack in STATE.engine.packs.items():
            for kind, t in pack.events.items():
                out.append(
                    EventTemplateRow(
                        pack=pack_id,
                        eventKind=kind,
                        description=getattr(t, "description", "") or "",
                        baseImportance=getattr(t, "base_importance", 0.0),
                        source=getattr(t, "source", "yaml"),
                    )
                )
        out.sort(key=lambda r: (r.pack, -r.baseImportance))
        return out

    @app.get("/api/personas", response_model=list[PersonaRow])
    def personas() -> list[PersonaRow]:
        """Expose loaded YAML personas per pack — for Library 'Characters' tab.

        These are the AUTHORED set, not just the spawned ones. Useful when
        you want to see "who could appear" vs "who's currently in the run".
        """
        _need_engine()
        out: list[PersonaRow] = []
        for pack_id, pack in STATE.engine.packs.items():
            for p in pack.personas:
                out.append(
                    PersonaRow(
                        id=p.agent_id,
                        name=p.display_name,
                        pack=pack_id,
                        alignment=getattr(p, "alignment", "neutral"),
                        isHf=getattr(p, "is_historical_figure", False),
                        tags=sorted(getattr(p, "tags", set())),
                        persona=(getattr(p, "persona_card", "") or "").strip(),
                    )
                )
        return out

    @app.get("/api/health", response_model=Health)
    def health() -> Health:
        return Health(ok=True, loaded=STATE.world is not None)

    return app


app = create_app()
