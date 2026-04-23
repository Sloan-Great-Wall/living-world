"""FastAPI sim API for the Tauri dashboard.

ENDPOINTS
---------
GET  /api/world              snapshot for top-bar stats
GET  /api/feature_status     which LLM modules are wired
GET  /api/agents             agent list (lightweight)
GET  /api/agent/{id}         full agent detail
GET  /api/events             recent events
GET  /api/chronicle          chapter list
GET  /api/social             social network metrics
GET  /api/event_kinds        event-kind frequency
GET  /api/settings           current settings dict
GET  /api/packs_available    which packs the user can load
POST /api/bootstrap          create a new world  body: {packs:[...], seed:int}
POST /api/tick               advance N ticks    body: {n:int}

Single shared engine instance (Stage A single-user model). Re-bootstrap
discards the previous world.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from living_world import PACKS_DIR


class BootstrapBody(BaseModel):
    packs: list[str]
    seed: int = 42


class TickBody(BaseModel):
    n: int = 1
from living_world.config import load_settings
from living_world.factory import bootstrap_world, make_engine
from living_world.queries import (
    diversity_summary,
    event_kind_distribution,
    export_chronicle_markdown,
    feature_status,
)


class _State:
    world: Any = None
    engine: Any = None
    loaded_packs: list[str] = []
    settings = load_settings()


STATE = _State()


def _need_engine():
    if STATE.engine is None:
        raise HTTPException(409, "No world loaded. POST /api/bootstrap first.")


# ── camelCase by API hygiene rule (KNOWN_ISSUES TS-port plan).
# Every key returned to the frontend is camelCase so the eventual
# TS-sim port produces identical JSON shape — zero-change UI migration.

def _agent_dict(a, full: bool = False) -> dict:
    base = {
        "id": a.agent_id, "name": a.display_name, "pack": a.pack_id,
        "alignment": a.alignment, "isHf": a.is_historical_figure,
        "alive": a.is_alive(), "tile": a.current_tile,
        "x": a.x, "y": a.y, "tags": sorted(a.tags),
    }
    if not full:
        return base
    base.update({
        "persona": (a.persona_card or "").strip(),
        "goal": a.current_goal,
        "needs": a.get_needs(),
        "emotions": a.get_emotions(),
        "attributes": dict(a.attributes),
        "beliefs": a.get_beliefs(),
        "motivations": a.get_motivations(),
        "weeklyPlan": a.get_weekly_plan(),
        "relationships": [
            {"target": r.target_id, "kind": r.kind, "affinity": r.affinity}
            for r in sorted(a.relationships.values(),
                            key=lambda r: -abs(r.affinity))[:10]
        ],
    })
    return base


def _event_dict(e) -> dict:
    return {
        "id": e.event_id, "tick": e.tick, "pack": e.pack_id, "tile": e.tile_id,
        "kind": e.event_kind, "outcome": e.outcome,
        "importance": e.importance, "tier": e.tier_used,
        "isEmergent": e.is_emergent, "participants": e.participants,
        "narrative": e.best_rendering(),
    }


def _world_snapshot() -> dict:
    if STATE.world is None:
        return {"loaded": False, "tick": 0, "packs": [], "agentsAlive": 0,
                "agentsTotal": 0, "eventsTotal": 0, "deaths": 0,
                "chapters": 0, "tiles": 0, "diversity": None,
                "modelTier2": STATE.settings.llm.ollama_tier2_model,
                "modelTier3": STATE.settings.llm.ollama_tier3_model}
    w = STATE.world
    return {
        "loaded": True, "tick": w.current_tick, "packs": STATE.loaded_packs,
        "agentsAlive": sum(1 for _ in w.living_agents()),
        "agentsTotal": sum(1 for _ in w.all_agents()),
        "eventsTotal": w.event_count(),
        "deaths": sum(1 for a in w.all_agents() if not a.is_alive()),
        "chapters": len(w.chapters),
        "tiles": sum(1 for _ in w.all_tiles()),
        "diversity": diversity_summary(w),
        "modelTier2": STATE.settings.llm.ollama_tier2_model,
        "modelTier3": STATE.settings.llm.ollama_tier3_model,
    }


def _tile_dict(t) -> dict:
    return {
        "id": t.tile_id, "name": t.display_name,
        "pack": t.primary_pack, "type": t.tile_type,
        "x": getattr(t, "x", 0.0), "y": getattr(t, "y", 0.0),
    }


def create_app() -> FastAPI:
    app = FastAPI(title="Living World API", version="0.1.0")
    # Permissive CORS for vite dev (1420) and Tauri webview
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"], allow_headers=["*"],
    )

    @app.post("/api/bootstrap")
    def bootstrap(payload: BootstrapBody):
        if not payload.packs:
            raise HTTPException(400, "packs cannot be empty")
        world, loaded = bootstrap_world(PACKS_DIR, payload.packs)
        STATE.world = world
        STATE.engine = make_engine(world, loaded, STATE.settings, payload.seed)
        STATE.loaded_packs = payload.packs
        return _world_snapshot()

    @app.post("/api/tick")
    def tick(payload: TickBody):
        _need_engine()
        if payload.n < 1 or payload.n > 100:
            raise HTTPException(400, "n must be 1..100")
        STATE.engine.run(payload.n)
        return _world_snapshot()

    @app.get("/api/world")
    def world():
        return _world_snapshot()

    @app.get("/api/feature_status")
    def features():
        _need_engine()
        return [
            {"name": fs.name, "on": fs.on, "detail": fs.detail}
            for fs in feature_status(STATE.engine)
        ]

    @app.get("/api/agents")
    def agents():
        _need_engine()
        return [_agent_dict(a) for a in STATE.world.all_agents()]

    @app.get("/api/agent/{agent_id}")
    def agent(agent_id: str):
        _need_engine()
        a = STATE.world.get_agent(agent_id)
        if a is None:
            raise HTTPException(404, f"unknown agent {agent_id}")
        out = _agent_dict(a, full=True)
        # camelCase by API hygiene rule (KNOWN_ISSUES TS-port plan)
        out["recentEvents"] = [
            _event_dict(e) for e in STATE.world.events_since(1)
            if agent_id in e.participants
        ][-15:]
        return out

    @app.get("/api/tiles")
    def tiles():
        _need_engine()
        return [_tile_dict(t) for t in STATE.world.all_tiles()]

    @app.get("/api/events")
    def events(since: int = 1, limit: int = 80):
        _need_engine()
        evts = STATE.world.events_since(since)
        return [_event_dict(e) for e in evts[-limit:]]

    @app.get("/api/chronicle")
    def chronicle():
        _need_engine()
        return STATE.world.chapters

    @app.get("/api/chronicle.md")
    def chronicle_md():
        _need_engine()
        return {"markdown": export_chronicle_markdown(STATE.world)}

    @app.get("/api/event_kinds")
    def event_kinds(top_k: int = 10):
        _need_engine()
        return event_kind_distribution(STATE.world, top_k=top_k)

    @app.get("/api/settings")
    def settings_get():
        return STATE.settings.model_dump()

    @app.post("/api/settings")
    def settings_set(payload: dict):
        """Patch the live settings + persist to settings.yaml.

        Accepts a partial dict — only top-level sections present in the
        payload are merged. Returns the merged settings dict.

        NOTE: Most settings only take effect on next bootstrap (engine
        is built from settings at bootstrap time). Caller should
        prompt the user to Reset → Simulate again after important
        changes (model swap, packs, feature flags).
        """
        from living_world.config import save_settings, Settings
        current = STATE.settings.model_dump()
        for section, fields in payload.items():
            if isinstance(fields, dict) and isinstance(current.get(section), dict):
                current[section].update(fields)
            else:
                current[section] = fields
        try:
            new_settings = Settings(**current)
        except Exception as e:
            raise HTTPException(400, f"invalid settings: {e}")
        STATE.settings = new_settings
        save_settings(new_settings)
        return STATE.settings.model_dump()

    @app.post("/api/reset")
    def reset():
        """Drop the loaded world. The frontend should then re-call
        /api/bootstrap with the desired packs."""
        STATE.world = None
        STATE.engine = None
        STATE.loaded_packs = []
        return {"ok": True}

    @app.get("/api/packs_available")
    def packs_available():
        return sorted(
            p.name for p in PACKS_DIR.iterdir()
            if p.is_dir() and (p / "pack.yaml").exists()
        )

    @app.get("/api/templates")
    def templates():
        """Expose loaded event TEMPLATES per pack — for Library 'Stories' tab."""
        _need_engine()
        out: list[dict] = []
        for pack_id, pack in STATE.engine.packs.items():
            for kind, t in pack.events.items():
                out.append({
                    "pack": pack_id,
                    "eventKind": kind,
                    "description": getattr(t, "description", "") or "",
                    "baseImportance": getattr(t, "base_importance", 0.0),
                    "source": getattr(t, "source", "yaml"),
                })
        out.sort(key=lambda r: (r["pack"], -r["baseImportance"]))
        return out

    @app.get("/api/personas")
    def personas():
        """Expose loaded YAML personas per pack — for Library 'Characters' tab.

        These are the AUTHORED set, not just the spawned ones. Useful when
        you want to see "who could appear" vs "who's currently in the run".
        """
        _need_engine()
        out: list[dict] = []
        for pack_id, pack in STATE.engine.packs.items():
            for p in pack.personas:
                out.append({
                    "id": p.agent_id,
                    "name": p.display_name,
                    "pack": pack_id,
                    "alignment": getattr(p, "alignment", "neutral"),
                    "isHf": getattr(p, "is_historical_figure", False),
                    "tags": sorted(getattr(p, "tags", set())),
                    "persona": (getattr(p, "persona_card", "") or "").strip(),
                })
        return out

    @app.get("/api/health")
    def health():
        return {"ok": True, "loaded": STATE.world is not None}

    return app


app = create_app()
