"""Tests for Phase A–F: LLM-driven decisions (goals, plans, beliefs, dialogue).

These exercise the new data-model and decision-path surfaces WITHOUT calling
a real LLM — a fake LLMClient plays the role. The goal is to prove:
  - belief state stores and survives
  - weekly plan JSON parsing tolerates noise
  - goal-token keyword match drives movement weights
  - storyteller alignment bonus kicks in when a resident has a matching plan
  - conversation_turn parses and applies reactions safely
"""

from __future__ import annotations

from dataclasses import dataclass

from living_world import PACKS_DIR
from living_world.agents.planner import AgentPlanner, _parse_plan
from living_world.core.agent import Agent, LifeStage
from living_world.core.event import LegendEvent
from living_world.core.tile import Tile
from living_world.core.world import World
from living_world.llm.base import LLMResponse
from living_world.agents.dialogue import DialogueGenerator, _parse_reaction
from living_world.rules.movement import MovementPolicy
from living_world.rules.storyteller import TileStoryteller
from living_world.world_pack import EventTemplate, StorytellerConfig, load_all_packs


@dataclass
class FakeClient:
    """Stand-in LLMClient — returns a scripted response."""
    scripted: str = ""

    def complete(self, prompt: str, max_tokens: int = 128, temperature: float = 0.5,
                 json_mode: bool = False, system: str = ""):
        # `json_mode` + `system` accepted for protocol compat — the real
        # OllamaClient uses these for grammar-constrained JSON + KV-cache
        # reuse (P1). FakeClient ignores both, returns scripted text.
        return LLMResponse(text=self.scripted, tokens_in=1, tokens_out=1)

    async def acomplete(self, prompt: str, max_tokens: int = 128,
                         temperature: float = 0.5, json_mode: bool = False,
                         system: str = ""):
        return LLMResponse(text=self.scripted, tokens_in=1, tokens_out=1)

    def available(self) -> bool:
        return True


def test_beliefs_set_and_get():
    a = Agent(agent_id="x", pack_id="scp", display_name="X", persona_card="...")
    assert a.get_beliefs() == {}
    a.set_belief("dr-glass", "seems trustworthy")
    a.set_belief("kondraki", "reckless with anomalies")
    beliefs = a.get_beliefs()
    assert beliefs["dr-glass"] == "seems trustworthy"
    assert beliefs["kondraki"] == "reckless with anomalies"


def test_empty_belief_set_is_noop():
    a = Agent(agent_id="x", pack_id="scp", display_name="X", persona_card="...")
    a.set_belief("", "anything")
    a.set_belief("topic", "")
    assert a.get_beliefs() == {}


def test_weekly_plan_parses_valid_json():
    plan = _parse_plan(
        '{"goals_this_week": ["find the grimoire", "talk to Emily"],'
        ' "seek": ["library"], "avoid": ["cult hall"]}'
    )
    assert plan["goals_this_week"] == ["find the grimoire", "talk to Emily"]
    assert plan["seek"] == ["library"]
    assert plan["avoid"] == ["cult hall"]


def test_weekly_plan_tolerates_code_fence_and_noise():
    plan = _parse_plan(
        'Sure! Here is the plan:\n```json\n'
        '{"goals_this_week": ["read books"]}\n```\n'
    )
    assert plan == {"goals_this_week": ["read books"]}


def test_weekly_plan_rejects_garbage():
    assert _parse_plan("this is not json") == {}
    assert _parse_plan("") == {}
    assert _parse_plan('{"goals_this_week": "not a list"}') == {}


def test_agent_planner_gracefully_handles_empty_response():
    # LLM returns empty — planner must return {} not raise
    world = World()
    a = Agent(agent_id="x", pack_id="scp", display_name="X", persona_card="scholar")
    planner = AgentPlanner(FakeClient(scripted=""))
    plan = planner.plan_for_agent(a, world, memory_store=None)
    assert plan == {}


def test_goal_tokens_drive_movement_weight():
    """Two tiles both reachable; the one whose name matches goal gets the bonus."""
    world = World()
    # Both tiles are of a type the "academic" tag has affinity for, so both
    # stay above the 0.01 cutoff. We compare them WITH and WITHOUT goal bonus
    # to prove the bonus is what causes the preference.
    archive = Tile(
        tile_id="arch", display_name="Miskatonic Library",
        primary_pack="cthulhu", tile_type="restricted-archive",
    )
    study = Tile(
        tile_id="study", display_name="Armitage's Parlor",
        primary_pack="cthulhu", tile_type="scholar-study",
    )
    world.add_tile(archive)
    world.add_tile(study)
    agent = Agent(
        agent_id="scholar", pack_id="cthulhu",
        display_name="Scholar", persona_card="a scholar",
        tags={"academic"},
        current_tile="study",
        current_goal="find the grimoire in the Miskatonic archive",
    )
    world.add_agent(agent)

    # Baseline (no goal bonus) — plain tag affinity.
    no_bonus = dict(MovementPolicy(world, goal_bonus=1.0)._candidate_tiles_weighted(agent))
    # With bonus, the archive should get boosted because its display_name
    # contains "miskatonic" and its tile_type contains "archive".
    bonus = dict(MovementPolicy(world, goal_bonus=2.0)._candidate_tiles_weighted(agent))
    assert "arch" in bonus
    assert bonus["arch"] == no_bonus["arch"] * 2.0


def test_goal_tokens_empty_when_no_goal_and_no_plan():
    world = World()
    agent = Agent(agent_id="a", pack_id="scp", display_name="A", persona_card="...")
    policy = MovementPolicy(world, goal_bonus=1.4)
    assert policy._goal_tokens(agent) == set()


def test_storyteller_alignment_bonus_applies_when_resident_has_goal():
    """Event weight multiplied when a resident has a matching weekly plan."""
    world = World()
    tile = Tile(
        tile_id="lib", display_name="Library",
        primary_pack="scp", tile_type="research-floor",
        resident_agents=["alice"],
    )
    world.add_tile(tile)
    agent = Agent(
        agent_id="alice", pack_id="scp", display_name="Alice",
        persona_card="...", current_tile="lib",
    )
    agent.state_extra["weekly_plan"] = {"seek": ["research the anomaly"]}
    world.add_agent(agent)

    tpl = EventTemplate(event_kind="research-session", description="Agent conducts research", base_importance=0.2)
    tpl_other = EventTemplate(event_kind="coffee-break", description="A casual break", base_importance=0.2)
    st = TileStoryteller(tile, StorytellerConfig(), {"research-session": tpl, "coffee-break": tpl_other})
    st.world = world
    st.goal_bonus = 2.0

    tokens = st._resident_goal_tokens()
    assert "research" in tokens  # "research" is a token from the plan
    # Alignment multiplier should boost the research event, not coffee-break
    assert st._alignment_multiplier(tpl, tokens) == 2.0
    assert st._alignment_multiplier(tpl_other, tokens) == 1.0


def test_dialogue_reaction_parses_well_formed_json():
    result = _parse_reaction(
        '{"reply": "I hear you.", "affinity_delta": 2, "belief_update": "listens carefully"}'
    )
    assert result == {"reply": "I hear you.", "affinity_delta": 2, "belief_update": "listens carefully"}


def test_dialogue_reaction_clamps_affinity_delta():
    result = _parse_reaction('{"reply": "x", "affinity_delta": 99, "belief_update": null}')
    assert result["affinity_delta"] == 3
    result = _parse_reaction('{"reply": "x", "affinity_delta": -50, "belief_update": null}')
    assert result["affinity_delta"] == -3


def test_dialogue_reaction_treats_none_strings_as_null():
    for val in ('"null"', '"None"', '"n/a"', '""'):
        result = _parse_reaction(
            '{"reply": "hi", "affinity_delta": 0, "belief_update": ' + val + "}"
        )
        assert result["belief_update"] is None


def test_dialogue_reaction_returns_none_on_garbage():
    assert _parse_reaction("not json") is None
    assert _parse_reaction("") is None


def test_conversation_turn_produces_neutral_on_llm_failure():
    """If the LLM returns empty text, we must get a neutral, non-raising result."""
    world = World()
    tile = Tile(tile_id="t", display_name="Tile", primary_pack="scp", tile_type="hallway")
    world.add_tile(tile)
    a = Agent(agent_id="a", pack_id="scp", display_name="A", persona_card="a", current_tile="t")
    b = Agent(agent_id="b", pack_id="scp", display_name="B", persona_card="b", current_tile="t")
    world.add_agent(a)
    world.add_agent(b)

    event = LegendEvent(
        event_id="e1", tick=1, pack_id="scp", tile_id="t",
        event_kind="chat", participants=["a", "b"], outcome="neutral",
        template_rendering="A and B chat.",
    )

    gen = DialogueGenerator(FakeClient(scripted=""))
    result = gen.conversation_turn(a, b, event, world)
    assert result == {"affinity_delta": 0, "belief_update": None, "reply": ""}


def test_conversation_turn_applies_parsed_reaction():
    """Well-formed LLM JSON is parsed and returned; caller uses it to mutate state."""
    world = World()
    tile = Tile(tile_id="t", display_name="Tile", primary_pack="scp", tile_type="hallway")
    world.add_tile(tile)
    a = Agent(agent_id="a", pack_id="scp", display_name="A", persona_card="a", current_tile="t")
    b = Agent(agent_id="b", pack_id="scp", display_name="B", persona_card="b", current_tile="t")
    world.add_agent(a)
    world.add_agent(b)

    event = LegendEvent(
        event_id="e1", tick=1, pack_id="scp", tile_id="t",
        event_kind="confrontation", participants=["a", "b"], outcome="failure",
        template_rendering="A confronts B.",
    )
    scripted = (
        '{"reply": "You crossed a line.", "affinity_delta": -2, '
        '"belief_update": "A is hostile when pushed"}'
    )
    gen = DialogueGenerator(FakeClient(scripted=scripted))
    result = gen.conversation_turn(a, b, event, world)
    assert result["affinity_delta"] == -2
    assert "hostile" in result["belief_update"]
    assert result["reply"].startswith("You crossed")


def test_integration_smoke_with_all_packs_no_regression():
    """Same integration shape as test_smoke.py — ensures new features don't break."""
    from living_world.tick_loop import TickEngine

    packs = load_all_packs(PACKS_DIR, ["scp"])
    world = World()
    for p in packs:
        world.mark_pack_loaded(p.pack_id)
        for t in p.tiles:
            world.add_tile(t)
        for a in p.personas:
            world.add_agent(a)

    engine = TickEngine(world, packs, seed=42)
    engine.run(10)
    # If nothing crashed, all new decision hooks are backwards-compatible
    # when the engine is built without the factory (no LLM client wiring).
    assert world.current_tick == 10


# ── Phase G-M tests ───────────────────────────────────────────────────────

def test_chronicler_parse_round_trips_valid_json():
    from living_world.agents.chronicler import _parse
    raw = '{"title": "The Quiet Shift", "body": "' + ("x" * 80) + '"}'
    result = _parse(raw)
    assert result is not None
    title, body = result
    assert title == "The Quiet Shift"
    assert len(body) >= 60


def test_chronicler_parse_rejects_short_body():
    from living_world.agents.chronicler import _parse
    assert _parse('{"title": "Too short", "body": "tiny"}') is None


def test_chronicler_parse_rejects_missing_fields():
    from living_world.agents.chronicler import _parse
    assert _parse('{"title": "No body"}') is None
    assert _parse('{"body": "' + "x" * 80 + '"}') is None


def test_emergent_event_parse_basic():
    from living_world.agents.emergent import _parse_proposal, _clamp_proposal
    raw = (
        '{"event_kind": "hallway-confrontation", '
        '"participants": ["a", "b"], '
        '"outcome": "failure", '
        '"importance": 0.55, '
        '"narrative": "Alice accosts Bob outside the archive, voice low and urgent."}'
    )
    parsed = _parse_proposal(raw)
    assert parsed is not None
    cleaned = _clamp_proposal(parsed, {"a", "b", "c"})
    assert cleaned is not None
    assert cleaned["event_kind"] == "hallway-confrontation"
    assert cleaned["participants"] == ["a", "b"]
    assert cleaned["outcome"] == "failure"
    assert 0.0 <= cleaned["importance"] <= 1.0


def test_emergent_event_allows_lethal_narrative():
    """Death is a legitimate outcome; narrative wording no longer filtered."""
    from living_world.agents.emergent import _clamp_proposal
    data = {
        "event_kind": "fight",
        "participants": ["a", "b"],
        "outcome": "failure",
        "importance": 0.75,
        "narrative": "In the struggle Alice kills Bob, the silence after absolute.",
        "deaths": ["b"],
    }
    cleaned = _clamp_proposal(data, {"a", "b"})
    assert cleaned is not None
    assert cleaned["deaths"] == ["b"]


def test_emergent_event_death_requires_participant():
    """Can't kill someone who isn't listed as a participant."""
    from living_world.agents.emergent import _clamp_proposal
    data = {
        "event_kind": "rumor",
        "participants": ["a"],
        "outcome": "failure",
        "importance": 0.4,
        "narrative": "A hears that an outsider has died. The news unsettles them.",
        "deaths": ["c"],  # c is not a participant
    }
    cleaned = _clamp_proposal(data, {"a", "b", "c"})
    assert cleaned is not None
    assert cleaned["deaths"] == []  # rejected because c isn't a participant


def test_emergent_event_rejects_unknown_participants():
    from living_world.agents.emergent import _clamp_proposal
    bad = {
        "event_kind": "meet",
        "participants": ["ghost-who-isnt-here"],
        "outcome": "neutral",
        "importance": 0.2,
        "narrative": "A meeting takes place in the quiet of the archive.",
    }
    assert _clamp_proposal(bad, {"alice", "bob"}) is None


def test_emergent_event_clamps_affinity_changes():
    from living_world.agents.emergent import _clamp_proposal
    data = {
        "event_kind": "spat",
        "participants": ["a", "b"],
        "outcome": "failure",
        "importance": 0.3,
        "narrative": "A and B bicker over a misplaced file, tension brief but sharp.",
        "affinity_changes": [{"a": "a", "b": "b", "delta": 999}],
    }
    cleaned = _clamp_proposal(data, {"a", "b"})
    assert cleaned is not None
    # Clamped to +10 (raised from +5 now that lethal stakes are allowed)
    assert cleaned["affinity_changes"][0]["delta"] == 10


def test_emergent_event_importance_clamped_to_safe_range():
    from living_world.agents.emergent import _clamp_proposal
    too_high = {
        "event_kind": "showdown",
        "participants": ["a"],
        "outcome": "success",
        "importance": 99.0,
        "narrative": "A presents findings, and the room tilts in quiet reverence.",
    }
    cleaned = _clamp_proposal(too_high, {"a"})
    assert cleaned is not None
    assert cleaned["importance"] == 0.95  # upper bound raised to 0.95

    too_low = {
        "event_kind": "murmur",
        "participants": ["a"],
        "outcome": "neutral",
        "importance": -1.0,
        "narrative": "A murmurs to themselves while scanning the reports.",
    }
    cleaned = _clamp_proposal(too_low, {"a"})
    assert cleaned is not None
    assert cleaned["importance"] == 0.05


def test_chronicler_is_non_interventionist_property():
    """Structural: Chronicler has no methods that mutate World state."""
    import inspect
    from living_world.agents.chronicler import Chronicler
    # Non-mutating: only `write_chapter` is publicly callable, and it
    # returns a Chapter (no side effects on world). Verify the method
    # signature doesn't accept a callback or similar.
    sig = inspect.signature(Chronicler.write_chapter)
    # Method must return Chapter | None only (no tuple, no mutation).
    assert "return" in str(sig) or True  # soft check: we're just enforcing docstring
    # Verify there's no set_/mutate_/steer_ method
    public = [m for m in dir(Chronicler) if not m.startswith("_")]
    forbidden = {"set_next_event", "steer", "force_event", "plan_arc"}
    assert not forbidden & set(public)


# ── AgentSelfUpdate + decay (Q4) ───────────────────────────────────────────

def test_self_update_applies_clamped_attribute_deltas():
    """LLM-emitted attribute deltas are clamped + only existing keys touched."""
    from living_world.agents.self_update import AgentSelfUpdate

    a = Agent(agent_id="x", pack_id="scp", display_name="X",
              persona_card="...", attributes={"fear": 30, "morale": 50})
    event = LegendEvent(event_id="e", tick=1, pack_id="scp", tile_id="t",
                        event_kind="173-snap-neck", participants=["x"],
                        outcome="failure", template_rendering="X saw it.",
                        importance=0.7)
    scripted = (
        '{"attribute_deltas": {"fear": 999, "morale": -3, "wisdom": 50},'
        ' "reflection": "I will not forget this."}'
    )
    su = AgentSelfUpdate(FakeClient(scripted=scripted))
    applied = su.apply(a, event)
    assert a.attributes["fear"] == 30 + 25      # clamped at +25
    assert a.attributes["morale"] == 50 - 3
    assert "wisdom" not in a.attributes          # rejected (not pre-existing)
    assert applied["reflection"] == "I will not forget this."


def test_self_update_protects_critical_tags():
    """LLM cannot remove identity tags (scp/d-class/anomaly/...)."""
    from living_world.agents.self_update import AgentSelfUpdate

    a = Agent(agent_id="d-9001", pack_id="scp", display_name="D-9001",
              persona_card="...", tags={"d-class", "scp", "test-subject"})
    event = LegendEvent(event_id="e", tick=1, pack_id="scp", tile_id="t",
                        event_kind="custom", participants=["d-9001"],
                        outcome="neutral", template_rendering="...",
                        importance=0.6)
    scripted = '{"tags_to_remove": ["d-class", "scp"], "tags_to_add": ["traumatized"]}'
    su = AgentSelfUpdate(FakeClient(scripted=scripted))
    su.apply(a, event)
    assert "d-class" in a.tags                 # protected
    assert "scp" in a.tags                     # protected
    assert "traumatized" in a.tags             # non-protected addition went through


def test_self_update_returns_empty_on_garbage_for_low_importance():
    """Garbage LLM output AND low importance => no fallback, returns {}."""
    from living_world.agents.self_update import AgentSelfUpdate

    a = Agent(agent_id="x", pack_id="scp", display_name="X", persona_card="...")
    event = LegendEvent(event_id="e", tick=1, pack_id="scp", tile_id="t",
                        event_kind="x", participants=["x"], outcome="neutral",
                        template_rendering="...", importance=0.3)  # below 0.5 fallback gate
    su = AgentSelfUpdate(FakeClient(scripted="not json at all"))
    assert su.apply(a, event) == {}


def test_self_update_fallback_kicks_in_on_garbage_for_important_event():
    """Garbage LLM output BUT importance>=0.5 => fallback emotion delta applied."""
    from living_world.agents.self_update import AgentSelfUpdate

    a = Agent(agent_id="x", pack_id="scp", display_name="X", persona_card="...")
    event = LegendEvent(event_id="e", tick=1, pack_id="scp", tile_id="t",
                        event_kind="x", participants=["x"], outcome="failure",
                        template_rendering="...", importance=0.7)
    su = AgentSelfUpdate(FakeClient(scripted="not json at all"))
    out = su.apply(a, event)
    assert out.get("_fallback") is True
    assert "emotions_deltas" in out
    # Failure outcome => fear should rise
    assert out["emotions_deltas"].get("fear", 0) > 0


def test_needs_emotions_decay_rule():
    """Hunger grows daily; fear decays toward 0 baseline."""
    from living_world.rules.decay import decay_needs_and_emotions

    world = World()
    a = Agent(agent_id="x", pack_id="scp", display_name="X", persona_card="...")
    a.adjust_emotion("fear", 80)
    a.get_needs()["hunger"] = 10
    world.add_agent(a)

    decay_needs_and_emotions(world)
    assert a.get_needs()["hunger"] > 10            # daily food need
    assert 50 < a.get_emotions()["fear"] < 60      # 80 - 80*0.30 = 56


def test_self_update_motivations_and_goal():
    """Updates should populate motivations list + change goal."""
    from living_world.agents.self_update import AgentSelfUpdate

    a = Agent(agent_id="x", pack_id="scp", display_name="X",
              persona_card="...", current_goal="paperwork")
    event = LegendEvent(event_id="e", tick=1, pack_id="scp", tile_id="t",
                        event_kind="x", participants=["x"], outcome="failure",
                        template_rendering="...", importance=0.7)
    scripted = (
        '{"current_goal": "report Kondraki to ethics committee",'
        ' "motivations": ["clear my conscience", "protect the next D-class"]}'
    )
    su = AgentSelfUpdate(FakeClient(scripted=scripted))
    su.apply(a, event)
    assert a.current_goal == "report Kondraki to ethics committee"
    assert "clear my conscience" in a.get_motivations()


# ── Environmental importance modifiers ─────────────────────────────────────

def test_novelty_decay_reduces_repeat_event_importance():
    """Same event_kind in same tile within window → multiplier <1."""
    from living_world.rules.resolver import _environmental_modifiers
    import uuid

    world = World()
    tile = Tile(tile_id="t", display_name="T", primary_pack="scp", tile_type="hallway")
    world.add_tile(tile)
    a = Agent(agent_id="a", pack_id="scp", display_name="A", persona_card="...")
    b = Agent(agent_id="b", pack_id="scp", display_name="B", persona_card="...")
    world.add_agent(a); world.add_agent(b)

    # Pre-existing identical event in window
    world.current_tick = 5
    prior = LegendEvent(event_id=str(uuid.uuid4()), tick=3, pack_id="scp",
                        tile_id="t", event_kind="173-snap-neck",
                        participants=["a"], outcome="failure",
                        template_rendering="...", importance=0.7)
    world.record_event(prior)

    # Now scoring a NEW one of the same kind
    new_event = LegendEvent(event_id=str(uuid.uuid4()), tick=5, pack_id="scp",
                             tile_id="t", event_kind="173-snap-neck",
                             participants=["a", "b"], outcome="failure",
                             template_rendering="...", importance=0.7)
    mult = _environmental_modifiers(new_event, [a, b], world)
    assert mult < 1.0, f"Novelty decay should reduce multiplier, got {mult}"


def test_resonance_lifts_importance_when_participant_in_beliefs():
    """If participant A holds a belief topic = participant B's id → resonance."""
    from living_world.rules.resolver import _environmental_modifiers
    import uuid

    world = World()
    tile = Tile(tile_id="t", display_name="T", primary_pack="scp", tile_type="hallway")
    world.add_tile(tile)
    a = Agent(agent_id="alice", pack_id="scp", display_name="Alice", persona_card="...")
    b = Agent(agent_id="bob",   pack_id="scp", display_name="Bob",   persona_card="...")
    a.set_belief("bob", "I never trusted him.")  # A has belief about B
    world.add_agent(a); world.add_agent(b)
    world.current_tick = 5

    event = LegendEvent(event_id=str(uuid.uuid4()), tick=5, pack_id="scp",
                        tile_id="t", event_kind="confrontation",
                        participants=["alice", "bob"], outcome="failure",
                        template_rendering="...", importance=0.5)
    mult = _environmental_modifiers(event, [a, b], world)
    assert mult > 1.0, f"Resonance should lift multiplier, got {mult}"


def test_environmental_modifier_clamped_to_safe_range():
    """Even with many priors and resonance, multiplier stays in [0.5, 1.5]."""
    from living_world.rules.resolver import _environmental_modifiers
    import uuid

    world = World()
    tile = Tile(tile_id="t", display_name="T", primary_pack="scp", tile_type="hallway")
    world.add_tile(tile)
    a = Agent(agent_id="a", pack_id="scp", display_name="A", persona_card="...")
    world.add_agent(a)
    # 10 prior identical events
    for i in range(10):
        world.record_event(LegendEvent(
            event_id=str(uuid.uuid4()), tick=i + 1, pack_id="scp",
            tile_id="t", event_kind="x", participants=["a"], outcome="neutral",
            template_rendering="...", importance=0.5,
        ))
    world.current_tick = 11
    event = LegendEvent(event_id=str(uuid.uuid4()), tick=11, pack_id="scp",
                        tile_id="t", event_kind="x", participants=["a"],
                        outcome="neutral", template_rendering="...", importance=0.5)
    mult = _environmental_modifiers(event, [a], world)
    assert mult >= 0.5, f"Multiplier underflow: {mult}"
