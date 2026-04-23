"""Unit tests for modules added in the 2026-04-22 audit.

Covers:
  - agents/reflector.py        — Park-style belief synthesis
  - memory/memory_store decay  — Park-style pruning
  - phases.py                  — DEFAULT_PIPELINE shape + isolation
  - queries.py                 — read-only world helpers
  - emergent injuries          — gravity-bug regression (KNOWN_ISSUES #1)

All tests use FakeClient / mock embedder; no real LLM or Ollama needed.
"""

from __future__ import annotations

from dataclasses import dataclass

from living_world.core.agent import Agent, Relationship
from living_world.core.event import LegendEvent
from living_world.core.tile import Tile
from living_world.core.world import World
from living_world.llm.base import LLMResponse

# ── shared fakes ──────────────────────────────────────────────────────────


@dataclass
class FakeClient:
    """Returns a scripted text. Accepts json_mode + system kwargs for
    protocol parity with the real OllamaClient (P1 KV-cache support)."""

    scripted: str = ""

    def complete(
        self,
        prompt: str,
        max_tokens: int = 256,
        temperature: float = 0.7,
        json_mode: bool = False,
        system: str = "",
    ):
        return LLMResponse(text=self.scripted, tokens_in=1, tokens_out=1)

    async def acomplete(
        self,
        prompt: str,
        max_tokens: int = 256,
        temperature: float = 0.7,
        json_mode: bool = False,
        system: str = "",
    ):
        return LLMResponse(text=self.scripted, tokens_in=1, tokens_out=1)

    def available(self) -> bool:
        return True


class FakeEmbedder:
    def embed(self, text: str) -> list[float]:
        # tiny deterministic 3-dim vector based on text length
        return [1.0, float(len(text) % 3), 0.0]


# ── reflector.py ──────────────────────────────────────────────────────────


def test_reflector_emits_beliefs_and_writes_them_back():
    from living_world.agents.reflector import MemoryReflector

    a = Agent(agent_id="x", pack_id="scp", display_name="X", persona_card="careful")
    scripted = (
        '{"beliefs": ['
        '  {"topic": "scp-173", "belief": "do not blink"},'
        '  {"topic": "myself", "belief": "I survive when alert"}'
        "]}"
    )
    r = MemoryReflector(FakeClient(scripted=scripted))
    out = r.reflect(a, ["raw memory 1", "raw memory 2", "raw memory 3"])
    assert len(out) == 2
    assert {b["topic"] for b in out} == {"scp-173", "myself"}
    # Side-effect: written onto the agent
    assert a.get_beliefs()["scp-173"] == "do not blink"
    assert r.stats["ok"] == 1
    assert r.stats["beliefs_emitted"] == 2


def test_reflector_returns_empty_on_short_memory_list():
    from living_world.agents.reflector import MemoryReflector

    a = Agent(agent_id="x", pack_id="scp", display_name="X", persona_card="x")
    r = MemoryReflector(FakeClient(scripted='{"beliefs": [{"topic":"t","belief":"b"}]}'))
    assert r.reflect(a, ["only one memory"]) == []
    assert r.stats["calls"] == 0  # never even called LLM


def test_reflector_handles_garbage_json():
    from living_world.agents.reflector import MemoryReflector

    a = Agent(agent_id="x", pack_id="scp", display_name="X", persona_card="x")
    r = MemoryReflector(FakeClient(scripted="not json"))
    out = r.reflect(a, ["m1", "m2", "m3"])
    assert out == []
    assert r.stats["empty"] == 1


# ── memory_store decay ────────────────────────────────────────────────────


def test_decay_no_op_under_cap():
    from living_world.memory.memory_store import AgentMemoryStore

    s = AgentMemoryStore(FakeEmbedder())
    for i in range(50):
        s.remember("a", tick=i, doc=f"e{i}", importance=0.3)
    assert s.decay("a", current_tick=100, max_per_agent=200) == 0
    assert s.count("a") == 50


def test_decay_prunes_when_over_cap():
    from living_world.memory.memory_store import AgentMemoryStore

    s = AgentMemoryStore(FakeEmbedder())
    # 250 entries of varying importance; cap at 200
    for i in range(250):
        s.remember("a", tick=i, doc=f"e{i}", importance=0.05 + (i % 10) * 0.09)
    dropped = s.decay("a", current_tick=100, max_per_agent=200)
    assert dropped == 50  # 20% of 250
    assert s.count("a") == 200


def test_decay_access_count_boosts_survival():
    """Among entries of the SAME age, high access_count should outscore
    low access_count. (Old entries still get decayed by recency — that's
    correct; access boost can't fully compensate for being ancient.)"""
    from living_world.memory.memory_store import AgentMemoryStore

    s = AgentMemoryStore(FakeEmbedder())
    # All entries at the same recent tick — recency factor is constant.
    for i in range(250):
        e = s.remember("a", tick=95, doc=f"e{i}", importance=0.2)
        # Half are heavily-recalled
        if i < 125:
            e.access_count = 100
    dropped = s.decay("a", current_tick=100, max_per_agent=200)
    assert dropped == 50
    survivors = s.backend.list_all_for("a")
    survived_ids = {int(e.doc[1:]) for e in survivors}
    # All 50 droppees should come from the no-access half (i in [125, 250))
    for i in range(125):
        assert i in survived_ids, f"high-access memory e{i} got pruned"


def test_recall_bumps_access_when_current_tick_supplied():
    from living_world.memory.memory_store import AgentMemoryStore

    s = AgentMemoryStore(FakeEmbedder())
    s.remember("a", 1, "hello world", importance=0.5)
    r = s.recall("a", "hello", top_k=1, current_tick=5)
    assert r[0].access_count == 1
    assert r[0].last_accessed_tick == 5
    # second recall further bumps
    s.recall("a", "hello", top_k=1, current_tick=8)
    assert r[0].access_count == 2
    assert r[0].last_accessed_tick == 8


def test_recall_legacy_k_kwarg_still_works():
    """Dashboard uses recall(..., top_k=N); some legacy code uses k=N."""
    from living_world.memory.memory_store import AgentMemoryStore

    s = AgentMemoryStore(FakeEmbedder())
    for i in range(5):
        s.remember("a", i, f"m{i}", importance=0.3)
    assert len(s.recall("a", "q", k=3)) == 3
    assert len(s.recall("a", "q", top_k=2)) == 2


# ── phases.py ─────────────────────────────────────────────────────────────


def test_default_pipeline_has_canonical_phase_order():
    from living_world.phases import DEFAULT_PIPELINE

    names = [p.name for p in DEFAULT_PIPELINE]
    # Decay must run before agents act on hunger; movement must come
    # before interactions (which depend on co-location); chronicler must
    # come after the events it summarises; snapshot last.
    assert names.index("decay") < names.index("needs_satisfy")
    assert names.index("movement") < names.index("interactions")
    assert names.index("storyteller") < names.index("chronicler")
    assert names[-1] == "snapshot"


def test_phase_failure_does_not_kill_subsequent_phases():
    """A bad phase logs + continues; later phases still run."""
    from living_world.phases import Phase

    class BoomPhase(Phase):
        name = "boom"

        def run(self, engine, t, stats):
            raise RuntimeError("intentional")

    class CountPhase(Phase):
        name = "count"

        def __init__(self):
            self.runs = 0

        def run(self, engine, t, stats):
            self.runs += 1

    # Mock minimal engine
    class StubLog:
        errors: list = []

        def phase_error(self, name, exc):
            self.errors.append((name, exc))

        def tick_start(self, t):
            pass

        def tick_end(self, t, s):
            pass

    counter = CountPhase()
    log = StubLog()

    class StubEngine:
        pipeline = [BoomPhase(), counter]
        tick_logger = log
        narrator = type("N", (), {"stats": type("S", (), {"tier1": 0, "tier3": 0})()})()

    # Borrow the real step() driver
    from living_world.tick_loop import TickEngine

    eng = StubEngine()
    eng.world = type("W", (), {"current_tick": 0})()
    # call the bound method directly with stub
    TickEngine.step(eng)
    assert counter.runs == 1, "counter phase should have run despite boom"
    assert log.errors and log.errors[0][0] == "boom"


# ── chronicler boundary (regression: v7 produced 0 chapters) ─────────────


def test_chronicler_phase_boundary_fires_at_exactly_every_ticks():
    """With chronicle_every_ticks=N and _last_chronicle_tick=0, the gate
    must let the chronicler RUN at exactly t=N (not t=N+1). v7 ran 14
    ticks with every=14 and got 0 chapters — this regression test pins
    the boundary so future tweaks don't silently break it again."""
    from living_world.phases import ChroniclerPhase

    class FakeChronicler:
        def __init__(self):
            self.calls = []
            self.stats = {"window_too_small": 0, "llm_error": 0, "parse_fail": 0}

        def write_chapter(self, world, pack_id, since_tick, min_events=2):
            self.calls.append((world.current_tick, pack_id, since_tick))
            from living_world.agents.chronicler import Chapter

            return Chapter(
                tick=world.current_tick, pack_id=pack_id, title="t", body="b" * 80, event_ids=[]
            )

    w = World()
    w.add_tile(Tile(tile_id="t1", display_name="T1", primary_pack="scp", tile_type="lab"))
    w.mark_pack_loaded("scp")
    fc = FakeChronicler()

    class StubEngine:
        chronicler = fc
        _last_chronicle_tick = 0
        chronicle_every_ticks = 14
        world = w
        tick_logger = None

    eng = StubEngine()
    phase = ChroniclerPhase()

    # Ticks 1..13: gate must skip
    for t in range(1, 14):
        eng.world.current_tick = t
        phase.run(eng, t, None)
    assert fc.calls == [], "chronicler must NOT fire before tick==every"

    # Tick 14: gate must fire (this is the v7 regression)
    eng.world.current_tick = 14
    phase.run(eng, 14, None)
    assert len(fc.calls) == 1, "chronicler MUST fire at t=every (regression)"
    assert fc.calls[0] == (14, "scp", 1)
    assert eng._last_chronicle_tick == 14

    # Ticks 15..27: skip again
    fc.calls.clear()
    for t in range(15, 28):
        eng.world.current_tick = t
        phase.run(eng, t, None)
    assert fc.calls == []

    # Tick 28: fire #2
    eng.world.current_tick = 28
    phase.run(eng, 28, None)
    assert len(fc.calls) == 1
    assert fc.calls[0] == (28, "scp", 15)


def test_chronicler_phase_does_not_advance_cursor_on_total_failure():
    """If every pack returns None (LLM down / window too small), cursor
    stays put so the next tick retries — instead of silently losing the
    whole window."""
    from living_world.phases import ChroniclerPhase

    class DeadChronicler:
        stats = {"window_too_small": 1, "llm_error": 0, "parse_fail": 0}

        def write_chapter(self, world, pack_id, since_tick, min_events=2):
            return None

    w = World()
    w.add_tile(Tile(tile_id="t1", display_name="T1", primary_pack="scp", tile_type="lab"))
    w.mark_pack_loaded("scp")

    class StubEngine:
        chronicler = DeadChronicler()
        _last_chronicle_tick = 0
        chronicle_every_ticks = 14
        world = w
        tick_logger = None

    eng = StubEngine()
    eng.world.current_tick = 14
    ChroniclerPhase().run(eng, 14, None)
    # Cursor un-advanced → next tick retries.
    assert eng._last_chronicle_tick == 0


# ── queries.py ────────────────────────────────────────────────────────────


def _make_world_with_events():
    """Tiny fixture world: 2 tiles, 4 agents, a handful of events."""
    w = World()
    w.add_tile(Tile(tile_id="t1", display_name="T1", primary_pack="scp", tile_type="lab"))
    w.add_tile(Tile(tile_id="t2", display_name="T2", primary_pack="liaozhai", tile_type="garden"))
    a = Agent(agent_id="a", pack_id="scp", display_name="A", persona_card="x", current_tile="t1")
    b = Agent(agent_id="b", pack_id="scp", display_name="B", persona_card="x", current_tile="t1")
    a.relationships["b"] = Relationship(target_id="b", affinity=80)
    b.relationships["a"] = Relationship(target_id="a", affinity=80)
    w.add_agent(a)
    w.add_agent(b)
    # Some events
    for i, kind in enumerate(["x", "y", "x", "z", "x"], start=1):
        ev = LegendEvent(
            event_id=f"e{i}",
            tick=i,
            pack_id="scp",
            tile_id="t1",
            event_kind=kind,
            participants=["a"],
            outcome="neutral",
            template_rendering="...",
            importance=0.4,
        )
        w.record_event(ev) if hasattr(w, "record_event") else w._events.append(ev)
    w.current_tick = 5
    return w


def test_diversity_summary():
    from living_world.queries import diversity_summary

    w = _make_world_with_events()
    s = diversity_summary(w)
    assert s["total"] == 5
    assert s["unique"] == 3
    assert s["top_kind"] == "x"
    assert s["top_pct"] == 60.0  # 3 of 5 events are kind "x"


def test_event_kind_distribution_and_grouping():
    from living_world.queries import event_kind_distribution, events_by_day, events_by_pack

    w = _make_world_with_events()
    dist = event_kind_distribution(w, top_k=3)
    assert dist[0] == ("x", 3)
    bp = events_by_pack(w)
    assert "scp" in bp and len(bp["scp"]) == 5
    bd = events_by_day(w)
    assert sorted(bd.keys()) == [1, 2, 3, 4, 5]


# ── emergent injuries regression (gravity bug, KNOWN_ISSUES #1) ───────────


def test_emergent_injuries_drops_unknown_strings_silently():
    """Old behavior: 'gravity' as injury entry rejected the whole proposal.
    New behavior: drop the bad entry, accept the rest."""
    from living_world.agents.emergent import _clamp_proposal

    proposal = {
        "event_kind": "conflict",
        "participants": ["alice", "bob"],
        "outcome": "failure",
        "importance": 0.7,
        "narrative": "A long-enough narrative line about Alice and Bob fighting.",
        "injuries": [
            {"agent_id": "alice", "severity": "grave"},
            "gravity",  # ← LLM mistake — should be silently dropped
            {"agent_id": "the_storm", "severity": "minor"},  # ← unknown id
        ],
    }
    out = _clamp_proposal(proposal, valid_agent_ids={"alice", "bob"})
    assert out is not None, "proposal should NOT be rejected for bad injury entries"
    assert out["injuries"] == [{"agent_id": "alice", "severity": "grave"}]


def test_emergent_injuries_skip_dead():
    from living_world.agents.emergent import _clamp_proposal

    proposal = {
        "event_kind": "deadly-fight",
        "participants": ["alice", "bob"],
        "outcome": "failure",
        "importance": 0.85,
        "narrative": "Alice was slain by Bob in a long-enough narrative line.",
        "deaths": ["alice"],
        "injuries": [{"agent_id": "alice", "severity": "grave"}],  # already dead
    }
    out = _clamp_proposal(proposal, valid_agent_ids={"alice", "bob"})
    assert out is not None
    assert out["deaths"] == ["alice"]
    assert out["injuries"] == []  # death takes precedence


# ── Story-quality regressions (2026-04-22 6-tick run) ─────────────────────


def test_resolver_drops_event_when_template_needs_more_participants_than_available():
    """The "?" placeholder bug: janitor-sees-too-much template uses ${b}
    but storyteller picked only 1 participant. Old behavior: emit
    "${a} 看见 ? 手里拿着..." (literal "?" in text). New: drop event."""
    import random

    from living_world.core.event import EventProposal
    from living_world.rules.resolver import EventResolver
    from living_world.world_pack import EventTemplate

    w = World()
    w.add_tile(Tile(tile_id="t1", display_name="T1", primary_pack="scp", tile_type="hall"))
    a = Agent(
        agent_id="a", pack_id="scp", display_name="Alice", persona_card="x", current_tile="t1"
    )
    w.add_agent(a)

    tpl = EventTemplate(
        event_kind="needs-two",
        description="needs two",
        trigger_conditions={"min_participants": 1, "max_participants": 2},
        outcomes={"neutral": {"template": "${a} sees ${b} sneaking by."}},
        base_importance=0.4,
    )
    prop = EventProposal(
        proposal_id="p1",
        pack_id="scp",
        tile_id="t1",
        event_kind="needs-two",
        priority=0.4,
    )
    resolver = EventResolver(w, random.Random(0))
    event = resolver.realize(prop, tpl, tick=1)
    assert event is None, (
        "resolver must skip events whose template needs ${b} when only one agent is available"
    )


def test_resolver_required_slots_detector():
    from living_world.rules.resolver import EventResolver

    assert EventResolver._required_slots("hello world") == 0
    assert EventResolver._required_slots("$a says hi") == 1
    assert EventResolver._required_slots("${a} meets ${b}") == 2
    assert EventResolver._required_slots("$a · $b · $c") == 3


def test_resolver_world_wide_same_kind_dedup_per_tick():
    """Two tiles with the same event_kind in the same tick: only the first
    realizes; the second is dropped to avoid same-day repetition."""
    import random

    from living_world.core.event import EventProposal
    from living_world.rules.resolver import EventResolver
    from living_world.world_pack import EventTemplate

    w = World()
    w.add_tile(Tile(tile_id="t1", display_name="T1", primary_pack="scp", tile_type="hall"))
    w.add_tile(Tile(tile_id="t2", display_name="T2", primary_pack="scp", tile_type="hall"))
    w.add_agent(
        Agent(agent_id="a", pack_id="scp", display_name="A", persona_card="x", current_tile="t1")
    )
    w.add_agent(
        Agent(agent_id="b", pack_id="scp", display_name="B", persona_card="x", current_tile="t2")
    )
    tpl = EventTemplate(
        event_kind="containment-breach",
        description="x",
        trigger_conditions={"min_participants": 1, "max_participants": 1},
        outcomes={"neutral": {"template": "[$tile] $a was here."}},
        base_importance=0.7,
    )
    resolver = EventResolver(w, random.Random(0))
    p1 = EventProposal(
        proposal_id="p1", pack_id="scp", tile_id="t1", event_kind="containment-breach", priority=0.7
    )
    p2 = EventProposal(
        proposal_id="p2", pack_id="scp", tile_id="t2", event_kind="containment-breach", priority=0.7
    )
    e1 = resolver.realize(p1, tpl, tick=5)
    e2 = resolver.realize(p2, tpl, tick=5)
    assert e1 is not None
    assert e2 is None, "same kind on different tile in same tick should be deduped"
    # Different tick: allowed again
    e3 = resolver.realize(p2, tpl, tick=6)
    assert e3 is not None


def test_emergent_phase_honors_same_kind_per_tick_cap(monkeypatch):
    """Regression: v3 6-tick run had d4/cult-activity-discovery×2 because
    EmergentPhase bypassed EventResolver's SAME_KIND_PER_TICK_CAP. Now
    it consults + bumps the resolver counter directly."""
    from living_world import phases as phases_mod
    from living_world.core.event import LegendEvent

    fired_count = {"v": 0}

    class StubProposer:
        def propose(self, tile, world):
            fired_count["v"] += 1
            return LegendEvent(
                event_id=f"e{fired_count['v']}",
                tick=world.current_tick,
                pack_id="scp",
                tile_id=tile.tile_id,
                event_kind="dup-kind",
                participants=[],
                outcome="neutral",
                template_rendering="...",
                importance=0.5,
                is_emergent=True,
            )

    class StubResolver:
        SAME_KIND_PER_TICK_CAP = 1

        def __init__(self):
            self._kind_tick_count: dict = {}

    class StubLog:
        def emergent_event(self, *a, **kw):
            pass

        def template_promoted(self, *a, **kw):
            pass

    processed: list[str] = []

    class StubEngine:
        emergent_proposer = StubProposer()
        emergent_max_per_tick = 5
        resolver = StubResolver()
        packs: dict = {}
        tick_logger = StubLog()

        def _process_event(self, e, stats):
            processed.append(e.event_id)

    w = World()
    t1 = Tile(tile_id="t1", display_name="T1", primary_pack="scp", tile_type="hall")
    t2 = Tile(tile_id="t2", display_name="T2", primary_pack="scp", tile_type="hall")
    w.add_tile(t1)
    w.add_tile(t2)
    w.current_tick = 5

    # Bypass heat scoring — tell EmergentPhase both tiles are hot.
    monkeypatch.setattr(phases_mod, "_rule_hot_tiles", lambda world, limit: [t1, t2])

    eng = StubEngine()
    eng.world = w
    phases_mod.EmergentPhase().run(eng, 5, type("S", (), {"reactions": 0})())

    assert len(processed) == 1, (
        f"only 1 event of kind 'dup-kind' should be processed in tick 5; "
        f"got {len(processed)}: {processed}"
    )


def test_emergent_pair_cooldown_blocks_repeat_cast():
    """The Strelnikov+O5-03 fixation bug: same agent set should not be
    proposed by emergent again within PAIR_COOLDOWN_TICKS days."""
    from living_world.agents.emergent import EmergentEventProposer
    from living_world.llm.base import LLMResponse

    class StubClient:
        def __init__(self, narrative: str):
            self.text = (
                '{"event_kind":"plot","participants":["alice","bob"],'
                '"outcome":"neutral","importance":0.5,'
                f'"narrative":"{narrative}"}}'
            )

        def complete(self, prompt, max_tokens=128, temperature=0.5, json_mode=False, system=""):
            return LLMResponse(text=self.text, tokens_in=1, tokens_out=1)

        async def acomplete(
            self, prompt, max_tokens=128, temperature=0.5, json_mode=False, system=""
        ):
            return LLMResponse(text=self.text, tokens_in=1, tokens_out=1)

        def available(self):
            return True

    w = World()
    w.add_tile(Tile(tile_id="t1", display_name="T1", primary_pack="scp", tile_type="hall"))
    w.add_agent(
        Agent(
            agent_id="alice", pack_id="scp", display_name="A", persona_card="x", current_tile="t1"
        )
    )
    w.add_agent(
        Agent(agent_id="bob", pack_id="scp", display_name="B", persona_card="x", current_tile="t1")
    )
    tile = w.get_tile("t1")

    proposer = EmergentEventProposer(
        StubClient("Alice and Bob have a long enough narrative sentence here together.")
    )

    w.current_tick = 1
    e1 = proposer.propose(tile, w)
    assert e1 is not None and proposer.stats["ok"] == 1

    # Same pair, +1 tick → should be cooldown-blocked
    w.current_tick = 2
    e2 = proposer.propose(tile, w)
    assert e2 is None
    assert proposer.stats["pair_cooldown"] == 1

    # After cooldown elapses, same pair allowed again
    w.current_tick = 1 + proposer.PAIR_COOLDOWN_TICKS
    e3 = proposer.propose(tile, w)
    assert e3 is not None
    assert proposer.stats["ok"] == 2
