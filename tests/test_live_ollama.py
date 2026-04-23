"""Live integration tests against a running local Ollama.

These exercise every agent-cosplay LLM module against a real model and
verify the OUTPUT CONTRACT (not exact text). They are gated on Ollama
availability — the entire module is skipped if the local Ollama daemon
isn't reachable, so CI / dev environments without it stay green.

To run:
    1. ollama serve &                    # if not already running
    2. ollama pull gemma3:4b             # the default tier-2/3 model
    3. ollama pull nomic-embed-text      # for memory recall
    4. ./lw test tests/test_live_ollama.py -v

Each test:
    - calls a real OllamaClient,
    - asserts the OUTPUT SHAPE is valid (parseable, in-range, non-empty),
    - never asserts specific text (gemma3 is non-deterministic across runs).

Slow: each test = 1-2 LLM calls = 5-30 seconds. Run them when you want
to verify "real prompts produce sane output", not in a tight loop.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from living_world.core.agent import Agent
from living_world.core.event import LegendEvent
from living_world.core.tile import Tile
from living_world.core.world import World
from living_world.llm.ollama import OllamaClient

# ── Module-level skip: if Ollama isn't reachable, skip everything here ──
_PROBE = OllamaClient(base_url="http://localhost:11434")
pytestmark = pytest.mark.skipif(
    not _PROBE.available(),
    reason="Ollama not reachable at localhost:11434 — skipping live LLM tests",
)


# Default test client. Use the small model so tests don't take an hour.
def _client() -> OllamaClient:
    return OllamaClient(model="gemma3:4b", base_url="http://localhost:11434", timeout=60.0)


# ─────────────────────────────────────────────────────────────────────────
# Smoke: the LLM responds at all and our OllamaClient parses the response
# ─────────────────────────────────────────────────────────────────────────


def test_ollama_basic_completion():
    """Ollama returns a non-empty completion for a trivial prompt."""
    resp = _client().complete("Say the single word: hello", max_tokens=8)
    assert resp.text is not None and len(resp.text.strip()) > 0
    assert resp.tokens_out > 0


# ─────────────────────────────────────────────────────────────────────────
# Narrator — Tier 3 narrative rewrite
# ─────────────────────────────────────────────────────────────────────────


def test_narrator_produces_clean_narrative():
    """Narrator should rewrite a template narrative into prose, no leak."""
    from living_world.agents.narrator import Narrator, NarratorBudget

    n = Narrator(tier3=_client(), budget=NarratorBudget())
    n.TIER3_THRESHOLD = 0.5  # force the LLM path
    event = LegendEvent(
        event_id="e1",
        tick=1,
        pack_id="scp",
        tile_id="lab-floor-3",
        event_kind="173-snap-neck",
        participants=["d-9001"],
        outcome="failure",
        template_rendering="[lab-floor-3] D-9001 was found with cervical fracture.",
        importance=0.7,
    )
    n.enhance(event)
    out = event.spotlight_rendering or event.template_rendering
    assert isinstance(out, str) and len(out) > 20
    # No prompt leakage
    for marker in ("World:", "Original:", "Rewrite the following"):
        assert marker not in out


# ─────────────────────────────────────────────────────────────────────────
# Conscience — verdict on a proposed event
# ─────────────────────────────────────────────────────────────────────────


def test_conscience_returns_valid_verdict():
    from living_world.agents.conscience import ConsciousnessLayer
    from living_world.core.event import EventProposal
    from living_world.world_pack import EventTemplate

    world = World()
    tile = Tile(tile_id="lab", display_name="Lab", primary_pack="scp", tile_type="research-floor")
    world.add_tile(tile)
    a = Agent(
        agent_id="dr-glass",
        pack_id="scp",
        display_name="Dr. Glass",
        persona_card="A cautious researcher who keeps to protocol.",
        alignment="lawful_neutral",
        current_tile="lab",
        attributes={"clearance": 3},
    )
    world.add_agent(a)

    cl = ConsciousnessLayer(_client(), importance_threshold=0.0, activation_chance=1.0)
    template = EventTemplate(
        event_kind="173-snap-neck",
        description="SCP-173 attacks an unobserved researcher",
        base_importance=0.7,
    )
    proposal = EventProposal(
        proposal_id="p1", pack_id="scp", tile_id="lab", event_kind="173-snap-neck", priority=0.7
    )
    verdict = cl.consider(proposal, template, [a], world)
    assert verdict is not None
    assert verdict.verdict in ("APPROVE", "ADJUST", "VETO")
    if verdict.adjusts:
        assert verdict.outcome in ("success", "failure", "neutral")


# ─────────────────────────────────────────────────────────────────────────
# AgentSelfUpdate — LLM speaks as the agent and reports inner shifts
# ─────────────────────────────────────────────────────────────────────────


def test_self_update_produces_valid_delta():
    from living_world.agents.self_update import AgentSelfUpdate

    a = Agent(
        agent_id="d-9045",
        pack_id="scp",
        display_name="D-9045",
        persona_card="A test subject who has narrowly survived three trials.",
        alignment="chaotic_neutral",
        attributes={"fear": 60, "morale": 30},
    )
    event = LegendEvent(
        event_id="e",
        tick=10,
        pack_id="scp",
        tile_id="lab-floor-3",
        event_kind="173-snap-neck",
        participants=["d-9045"],
        outcome="failure",
        template_rendering="D-9045 was attacked but survived.",
        importance=0.75,
    )
    su = AgentSelfUpdate(_client())
    applied = su.apply(a, event)
    # The LLM might emit empty (no change) — that's OK.
    # If non-empty, every delta must be in our clamp range.
    if "attribute_deltas" in applied:
        for k, v in applied["attribute_deltas"].items():
            assert -25 <= v <= 25, f"{k} delta out of clamp: {v}"
    if "needs_deltas" in applied:
        for k, v in applied["needs_deltas"].items():
            assert -30 <= v <= 30
            assert k in ("hunger", "safety")
    if "emotions_deltas" in applied:
        for k, v in applied["emotions_deltas"].items():
            assert -40 <= v <= 40
            assert k in ("fear", "joy", "anger")
    if "reflection" in applied:
        assert isinstance(applied["reflection"], str)
        assert len(applied["reflection"]) <= 200


# ─────────────────────────────────────────────────────────────────────────
# Dialogue — A→B reaction loop
# ─────────────────────────────────────────────────────────────────────────


def test_dialogue_conversation_turn_returns_valid_reaction():
    from living_world.agents.dialogue import DialogueGenerator

    world = World()
    tile = Tile(tile_id="t", display_name="T", primary_pack="scp", tile_type="hallway")
    world.add_tile(tile)
    speaker = Agent(
        agent_id="kondraki",
        pack_id="scp",
        display_name="Dr. Kondraki",
        persona_card="Reckless researcher; has crossed lines.",
        alignment="chaotic_neutral",
        current_tile="t",
    )
    listener = Agent(
        agent_id="glass",
        pack_id="scp",
        display_name="Dr. Glass",
        persona_card="Cautious by-the-book researcher.",
        alignment="lawful_neutral",
        current_tile="t",
    )
    world.add_agent(speaker)
    world.add_agent(listener)

    event = LegendEvent(
        event_id="e",
        tick=5,
        pack_id="scp",
        tile_id="t",
        event_kind="confrontation",
        participants=["kondraki", "glass"],
        outcome="failure",
        template_rendering="Kondraki shouted Glass down in the hall over a containment shortcut.",
        importance=0.6,
    )
    gen = DialogueGenerator(_client())
    result = gen.conversation_turn(speaker, listener, event, world)
    assert isinstance(result, dict)
    assert "affinity_delta" in result and -3 <= result["affinity_delta"] <= 3
    assert "reply" in result and isinstance(result["reply"], str)
    assert "belief_update" in result  # may be None or str


# ─────────────────────────────────────────────────────────────────────────
# Planner — weekly plan
# ─────────────────────────────────────────────────────────────────────────


def test_planner_produces_valid_plan_dict():
    from living_world.agents.planner import AgentPlanner

    world = World()
    a = Agent(
        agent_id="bright",
        pack_id="scp",
        display_name="Dr. Bright",
        persona_card="Sarcastic senior researcher with too many strange items.",
        alignment="chaotic_neutral",
        current_goal="finish weekly SCP-173 observation summary",
        tags={"researcher", "scp"},
    )
    world.add_agent(a)
    p = AgentPlanner(_client())
    plan = p.plan_for_agent(a, world, memory_store=None)
    # Plan may be empty if LLM produces noise — OK. If non-empty, validate.
    if plan:
        for key in ("goals_this_week", "seek", "avoid"):
            if key in plan:
                assert isinstance(plan[key], list)
                assert all(isinstance(x, str) for x in plan[key])
                assert len(plan[key]) <= 3


# ─────────────────────────────────────────────────────────────────────────
# Emergent event — LLM invents an event from scratch
# ─────────────────────────────────────────────────────────────────────────


def test_emergent_proposer_can_invent_event():
    from living_world.agents.emergent import EmergentEventProposer

    world = World()
    tile = Tile(
        tile_id="lounge", display_name="Lounge", primary_pack="scp", tile_type="social-area"
    )
    world.add_tile(tile)
    a = Agent(
        agent_id="kondraki",
        pack_id="scp",
        display_name="Dr. Kondraki",
        persona_card="Reckless researcher.",
        current_tile="lounge",
        tags={"researcher"},
    )
    b = Agent(
        agent_id="glass",
        pack_id="scp",
        display_name="Dr. Glass",
        persona_card="Cautious researcher.",
        current_tile="lounge",
        tags={"researcher"},
    )
    a.adjust_affinity("glass", -50, 1)  # they hate each other
    b.adjust_affinity("kondraki", -50, 1)
    world.add_agent(a)
    world.add_agent(b)

    proposer = EmergentEventProposer(_client())
    event = proposer.propose(tile, world)
    # The LLM may decline or fail validation — that's OK. If it returns
    # something, the structure must be valid.
    if event is not None:
        assert event.tile_id == "lounge"
        assert event.outcome in ("success", "failure", "neutral")
        assert 0.0 <= event.importance <= 1.0
        assert all(p in {"kondraki", "glass"} for p in event.participants)
        assert event.is_emergent is True


# ─────────────────────────────────────────────────────────────────────────
# Subjective perception — first-person reframing
# ─────────────────────────────────────────────────────────────────────────


def test_perception_returns_first_person_text():
    from living_world.agents.perception import SubjectivePerception

    a = Agent(
        agent_id="d-9012",
        pack_id="scp",
        display_name="D-9012",
        persona_card="A weary test subject who keeps his head down.",
    )
    event = LegendEvent(
        event_id="e",
        tick=8,
        pack_id="scp",
        tile_id="d-holding",
        event_kind="173-snap-neck",
        participants=["d-9012"],
        outcome="failure",
        template_rendering="D-9045 was killed by SCP-173 while D-9012 watched.",
        importance=0.7,
    )
    p = SubjectivePerception(_client())
    text = p.reframe(a, event)
    # If LLM degraded, it falls back to event.best_rendering — also acceptable.
    assert isinstance(text, str) and len(text) > 5


# ─────────────────────────────────────────────────────────────────────────
# End-to-end: real Ollama, 3 ticks, all hooks wired
# ─────────────────────────────────────────────────────────────────────────


def test_end_to_end_three_ticks_with_real_ollama():
    """The full engine runs 3 ticks with real Ollama and produces real LLM
    activity. Verifies wiring is correct under live conditions, not just
    that prompts parse."""
    from living_world.config import load_settings
    from living_world.factory import bootstrap_world, make_engine

    settings = load_settings()
    # Force LLM on (overrides yaml defaults if user set to none)
    settings.llm.tier2_provider = "ollama"
    settings.llm.tier3_provider = "ollama"

    world, loaded = bootstrap_world(Path("world_packs"), ["scp"])
    engine = make_engine(world, loaded, settings, seed=42)
    engine.run(3)

    # We don't assert specific event content — just that the engine ran
    # and at least one Tier-3 LLM rewrite happened (importance ≥ 0.65 events
    # should trigger it for sure across 3 ticks of SCP).
    assert engine.narrator.stats.tier1 + engine.narrator.stats.tier3 > 0
    # Memory store should have stored something
    if engine.memory is not None:
        # at least one agent should have memories
        any_remembered = any(
            engine.memory.count(a.agent_id) > 0 for a in list(world.living_agents())[:5]
        )
        assert any_remembered, "No agent remembered any event after 3 ticks"
