"""End-to-end API integration — exercises the FastAPI surface against
TestClient and asserts every response parses cleanly as the Pydantic
schema we ship over the wire (and therefore as the TS types generated
from it).

Why this exists (Phase 3+ audit gap):
  - Pydantic models on the *output* side only validate when the dict
    is constructed. They DON'T re-validate when FastAPI serializes
    them to JSON. A server-side bug that builds a model from `**dict`
    with the wrong key would still ship.
  - The TS-side tests (vitest) verify TypeScript matches the
    generated schema; they do NOT verify Python actually produces
    that schema at runtime.
  - This test closes the loop: real HTTP → real serialization → real
    Pydantic re-validation on the way back in.

Discipline: no LLM here. Bootstrap + a couple of ticks + every GET
endpoint hit. Should run in <5 seconds.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from living_world.web.schemas import (
    Agent,
    Chapter,
    EventTemplateRow,
    FeatureStatus,
    Health,
    Ok,
    PersonaRow,
    SocialGraph,
    Tile,
    WorldEvent,
    WorldSnapshot,
)

# ── Fixtures ───────────────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def client():
    """Build a FastAPI TestClient with the live engine wiring; bootstrap
    a tiny world and run a few ticks so every list endpoint has data.

    We import inside the fixture so the global STATE doesn't leak across
    test modules (each module that touches server.py gets a fresh state).
    """
    from living_world.config import load_settings
    from living_world.web import server as srv

    # Strip every LLM-bound feature; rules-only for determinism.
    settings = load_settings()
    settings.llm.tier2_provider = "none"
    settings.llm.tier3_provider = "none"
    settings.llm.dynamic_dialogue_enabled = False
    settings.llm.llm_movement_enabled = False
    settings.llm.weekly_planning_enabled = False
    settings.llm.conversation_loop_enabled = False
    settings.llm.chronicler_enabled = False
    settings.llm.emergent_events_enabled = False
    settings.llm.subjective_perception_enabled = False
    settings.llm.self_update_enabled = False
    settings.llm.conscious_override_enabled = False
    settings.memory.enabled = False
    srv.STATE.settings = settings

    c = TestClient(srv.app)
    r = c.post("/api/bootstrap", json={"packs": ["scp", "liaozhai", "cthulhu"], "seed": 42})
    assert r.status_code == 200, r.text
    r = c.post("/api/tick", json={"n": 4})
    assert r.status_code == 200, r.text
    return c


# ── Health probe + bootstrap path (negative + positive) ────────────────────


def test_health_endpoint_shape():
    """/api/health works without bootstrap and returns a typed Health."""
    from living_world.web import server as srv

    c = TestClient(srv.app)
    r = c.get("/api/health")
    assert r.status_code == 200
    Health.model_validate(r.json())  # raises on shape mismatch


def test_bootstrap_with_empty_packs_400():
    from living_world.web import server as srv

    c = TestClient(srv.app)
    r = c.post("/api/bootstrap", json={"packs": [], "seed": 42})
    assert r.status_code == 400


# ── Every GET endpoint round-trips a Pydantic model ────────────────────────


def test_world_endpoint(client):
    r = client.get("/api/world")
    assert r.status_code == 200
    snap = WorldSnapshot.model_validate(r.json())
    assert snap.loaded is True
    assert snap.tick == 4
    # Diversity field deleted in 2026-04-26 audit — assert it isn't snuck back
    assert "diversity" not in r.json()


def test_feature_status_endpoint(client):
    r = client.get("/api/feature_status")
    assert r.status_code == 200
    rows = [FeatureStatus.model_validate(x) for x in r.json()]
    assert all(isinstance(row.on, bool) for row in rows)
    # Sanity: every row has a non-empty name
    assert all(row.name for row in rows)


def test_agents_endpoint(client):
    r = client.get("/api/agents")
    assert r.status_code == 200
    agents = [Agent.model_validate(x) for x in r.json()]
    assert len(agents) > 0
    # Lightweight projection: full-detail fields should be None.
    assert all(a.persona is None for a in agents)


def test_agent_detail_endpoint(client):
    # Pick whichever agent showed up; we don't care which.
    list_resp = client.get("/api/agents").json()
    aid = list_resp[0]["id"]
    r = client.get(f"/api/agent/{aid}")
    assert r.status_code == 200
    a = Agent.model_validate(r.json())
    # Detail call DOES populate the optional fields:
    assert a.persona is not None
    assert a.recentEvents is not None  # might be empty list, not None


def test_agent_detail_404(client):
    r = client.get("/api/agent/no-such-agent-id-xyz")
    assert r.status_code == 404


def test_tiles_endpoint(client):
    r = client.get("/api/tiles")
    assert r.status_code == 200
    tiles = [Tile.model_validate(x) for x in r.json()]
    assert len(tiles) > 0


def test_events_endpoint(client):
    r = client.get("/api/events?since=1&limit=200")
    assert r.status_code == 200
    events = [WorldEvent.model_validate(x) for x in r.json()]
    # 4 ticks rules-only with 3 packs reliably emits at least one event
    assert len(events) > 0
    # outcome literal must be one of the three values
    assert all(e.outcome in ("success", "failure", "neutral") for e in events)


def test_chronicle_endpoint(client):
    r = client.get("/api/chronicle")
    assert r.status_code == 200
    [Chapter.model_validate(c) for c in r.json()]
    # Empty list is fine — chronicler is disabled in this fixture.


def test_social_graph_endpoint(client):
    """The endpoint that powers the dashboard's SocialPanel — first
    real consumer of @living-world/sim-core. Validate the wire format
    matches the Pydantic shape AND structurally looks computable."""
    r = client.get("/api/social_graph")
    assert r.status_code == 200
    payload = SocialGraph.model_validate(r.json())
    assert len(payload.agents) > 0
    # Each entry has the four fields the TS sim-core consumes:
    a = payload.agents[0]
    assert hasattr(a, "agentId")
    assert hasattr(a, "packId")
    assert hasattr(a, "alive")
    assert isinstance(a.relationships, list)


def test_templates_endpoint(client):
    r = client.get("/api/templates")
    assert r.status_code == 200
    rows = [EventTemplateRow.model_validate(x) for x in r.json()]
    assert len(rows) > 0


def test_personas_endpoint(client):
    r = client.get("/api/personas")
    assert r.status_code == 200
    rows = [PersonaRow.model_validate(x) for x in r.json()]
    assert len(rows) > 0


def test_packs_available(client):
    r = client.get("/api/packs_available")
    assert r.status_code == 200
    packs = r.json()
    assert isinstance(packs, list)
    assert "scp" in packs


# ── Routes that should NOT exist (deleted in 2026-04-26 audit) ─────────────


@pytest.mark.parametrize("path", ["/api/event_kinds", "/api/chronicle.md"])
def test_deleted_routes_return_404(client, path):
    """Regression guard: simplification audit removed these. If a future
    refactor accidentally re-adds them, this test catches it."""
    r = client.get(path)
    assert r.status_code == 404


# ── Tick + reset round-trip ────────────────────────────────────────────────


def test_tick_advances_clock(client):
    before = WorldSnapshot.model_validate(client.get("/api/world").json())
    r = client.post("/api/tick", json={"n": 2})
    assert r.status_code == 200
    after = WorldSnapshot.model_validate(r.json())
    assert after.tick == before.tick + 2


def test_tick_n_out_of_range_400(client):
    r = client.post("/api/tick", json={"n": 0})
    assert r.status_code == 400
    r = client.post("/api/tick", json={"n": 999})
    assert r.status_code == 400


def test_reset_clears_world():
    """Reset is destructive; isolate it in its own client."""
    from living_world.web import server as srv

    c = TestClient(srv.app)
    c.post("/api/bootstrap", json={"packs": ["scp"], "seed": 42})
    r = c.post("/api/reset")
    assert r.status_code == 200
    Ok.model_validate(r.json())
    # /api/world after reset should not raise — returns the empty snapshot
    snap = WorldSnapshot.model_validate(c.get("/api/world").json())
    assert snap.loaded is False
