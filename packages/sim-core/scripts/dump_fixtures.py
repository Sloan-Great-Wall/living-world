"""Dump golden fixtures for the TypeScript sim-core parity tests.

Run from repo root:
    .venv/bin/python packages/sim-core/scripts/dump_fixtures.py

Generates JSON fixtures alongside `packages/sim-core/test/fixtures/`:
  - dice_importance.json   — scoreEventImportance cases
  - dice_outcome.json      — outcomeForRoll cases
  - dice_modifiers.json    — environmentalModifiers cases
  - social_metrics.json    — computeSocialMetrics cases

Each fixture's INPUT is plain JSON; the EXPECTED OUTPUT is whatever the
Python implementation produces. The TS tests load the JSON and assert
their port returns the same shape.

This script is the single source of truth for parity. If you change
either side's algorithm, regen the fixtures and update both sides.
"""
from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from living_world.core.agent import Agent, Item, Relationship
from living_world.core.event import LegendEvent
from living_world.metrics.social import compute_social_metrics
from living_world.rules.resolver import (
    _environmental_modifiers,
    score_event_importance,
)
from living_world.world_pack import EventTemplate


FIX_DIR = Path(__file__).resolve().parent.parent / "test" / "fixtures"
FIX_DIR.mkdir(parents=True, exist_ok=True)


# ── helpers ────────────────────────────────────────────────────────────

def _agent_to_lite(a: Agent) -> dict:
    return {
        "agentId": a.agent_id,
        "displayName": a.display_name,
        "attributes": {k: v for k, v in a.attributes.items()
                       if isinstance(v, (int, float))},
        "isHistoricalFigure": bool(a.is_historical_figure),
        "beliefs": a.get_beliefs() if hasattr(a, "get_beliefs") else {},
        "weeklyPlan": a.get_weekly_plan() if hasattr(a, "get_weekly_plan") else {},
        "motivations": a.get_motivations() if hasattr(a, "get_motivations") else [],
        "inventory": [{"tags": list(it.tags), "power": int(it.power)}
                       for it in (a.inventory or [])],
    }


def _agent_for_metrics(a: Agent) -> dict:
    return {
        "agentId": a.agent_id,
        "alive": a.is_alive(),
        "packId": a.pack_id,
        "relationships": [
            {"targetId": r.target_id, "affinity": int(r.affinity)}
            for r in a.relationships.values()
        ],
    }


def _make_agent(aid: str, *, hf: bool = False, attrs=None,
                inventory=None, pack="scp") -> Agent:
    a = Agent(agent_id=aid, pack_id=pack, display_name=aid.title(),
              persona_card="x")
    a.is_historical_figure = hf
    if attrs:
        a.attributes.update(attrs)
    if inventory:
        a.inventory = inventory
    return a


# ── 1. importance scoring ──────────────────────────────────────────────

def gen_importance() -> list[dict]:
    cases = []

    # Case A: vanilla low-importance event
    e = LegendEvent(event_id="e1", tick=1, pack_id="scp", tile_id="t1",
                     event_kind="meal-break", participants=["a"],
                     outcome="neutral", importance=0.1)
    a1 = _make_agent("alice")
    cases.append({
        "name": "vanilla_low",
        "event": {"eventKind": e.event_kind, "outcome": e.outcome,
                   "tileId": e.tile_id, "relationshipChanges": []},
        "participants": [_agent_to_lite(a1)],
        "opts": {"baseImportance": 0.1},
        "expected": score_event_importance(e, [a1], base_importance=0.1),
    })

    # Case B: spotlight kind, base=0.6, two HFs, 2 rel changes, failure
    e2 = LegendEvent(event_id="e2", tick=2, pack_id="scp", tile_id="t1",
                      event_kind="containment-breach", participants=["a", "b"],
                      outcome="failure", importance=0.6)
    e2.relationship_changes = [{"a": "alice", "b": "bob", "delta": -10},
                                {"a": "bob", "b": "alice", "delta": -10}]
    a2 = _make_agent("alice", hf=True)
    a3 = _make_agent("bob", hf=True)
    cases.append({
        "name": "spotlight_two_hfs_failure",
        "event": {"eventKind": e2.event_kind, "outcome": e2.outcome,
                   "tileId": e2.tile_id, "relationshipChanges": [{}, {}]},
        "participants": [_agent_to_lite(a2), _agent_to_lite(a3)],
        "opts": {"baseImportance": 0.6},
        "expected": score_event_importance(e2, [a2, a3], base_importance=0.6),
    })

    # Case C: with active player (huge bump)
    cases.append({
        "name": "with_active_player",
        "event": {"eventKind": "meal-break", "outcome": "neutral",
                   "tileId": "t1", "relationshipChanges": []},
        "participants": [_agent_to_lite(_make_agent("alice"))],
        "opts": {"baseImportance": 0.2, "tileHasActivePlayer": True},
        "expected": score_event_importance(
            LegendEvent(event_id="x", tick=0, pack_id="scp", tile_id="t1",
                         event_kind="meal-break", participants=["a"],
                         outcome="neutral"),
            [_make_agent("alice")],
            tile_has_active_player=True, base_importance=0.2,
        ),
    })
    return cases


# ── 2. outcomeForRoll ──────────────────────────────────────────────────

def gen_outcome() -> list[dict]:
    """For each (template, agents, raw_d20), record what outcome the
    Python code WOULD produce given the SAME pre-roll value. We bypass
    Python's RNG entirely by reimplementing the post-roll branch
    locally — trivial and matches resolver._roll_outcome exactly."""
    def py_outcome(template: EventTemplate, participants, raw):
        cfg = template.dice_roll or {}
        if not cfg:
            return "neutral"
        dc = int(cfg.get("dc", 12))
        stat = cfg.get("stat")
        mod = int(cfg.get("mod", 0))
        bonus = 0
        inv_bonus = 0
        if participants:
            if stat:
                bonuses = []
                for p in participants:
                    v = p.attributes.get(stat, 0)
                    if isinstance(v, (int, float)):
                        bonuses.append(int((float(v) - 10) / 2))
                if bonuses:
                    bonus = max(bonuses)
            from living_world.rules.resolver import EventResolver
            inv_bonuses = [EventResolver._inventory_bonus(p, template)
                            for p in participants]
            inv_bonus = min(5, max(inv_bonuses)) if inv_bonuses else 0
        roll = raw + bonus + mod + inv_bonus
        if roll >= dc:
            return "success"
        if roll <= max(1, dc - 10):
            return "failure"
        return "neutral"

    cases = []
    tmpl = EventTemplate(
        event_kind="containment-test",
        description="x",
        trigger_conditions={"required_tags": ["scp", "test"]},
        dice_roll={"stat": "insight", "dc": 14, "mod": 0},
        cooldown_days=1, base_importance=0.4,
        outcomes={"success": {}, "failure": {}, "neutral": {}},
    )
    a = _make_agent("alice", attrs={"insight": 14})  # mod = +2
    inv_item = Item(name="Amulet", tags=["test"], power=3)
    b = _make_agent("bob", attrs={"insight": 8}, inventory=[inv_item])  # mod=-1, inv=+3
    for raw in [1, 5, 10, 12, 15, 20]:
        cases.append({
            "name": f"two_agents_raw{raw}",
            "template": {
                "eventKind": tmpl.event_kind,
                "baseImportance": tmpl.base_importance,
                "diceRoll": dict(tmpl.dice_roll),
                "triggerConditions": {"requiredTags": list(
                    tmpl.trigger_conditions.get("required_tags") or [])},
            },
            "participants": [_agent_to_lite(a), _agent_to_lite(b)],
            "rawD20": raw,
            "expected": py_outcome(tmpl, [a, b], raw),
        })

    # No-dice template → always neutral
    tmpl_nodice = EventTemplate(
        event_kind="meal-break", description="x",
        trigger_conditions={}, dice_roll={},
        cooldown_days=1, base_importance=0.05, outcomes={},
    )
    cases.append({
        "name": "no_dice_neutral",
        "template": {
            "eventKind": tmpl_nodice.event_kind,
            "baseImportance": tmpl_nodice.base_importance,
            "diceRoll": None,
            "triggerConditions": {"requiredTags": []},
        },
        "participants": [_agent_to_lite(a)],
        "rawD20": 20,
        "expected": "neutral",
    })
    return cases


# ── 3. environmental modifiers ─────────────────────────────────────────

def gen_modifiers() -> list[dict]:
    cases = []
    e = LegendEvent(event_id="e1", tick=10, pack_id="scp", tile_id="t1",
                     event_kind="containment-breach", participants=["a", "b"],
                     outcome="failure", importance=0.6)

    # No priors, no resonance → multiplier 1.0
    a = _make_agent("alice")
    b = _make_agent("bob")

    # Build a tiny mock world surface
    class _W:
        def __init__(self, tick: int, priors: list[LegendEvent]):
            self.current_tick = tick
            self._priors = priors
        def events_since(self, since):
            return [p for p in self._priors if p.tick >= since]

    w0 = _W(10, [])
    cases.append({
        "name": "no_priors_no_resonance",
        "event": {"eventKind": e.event_kind, "outcome": e.outcome,
                   "tileId": e.tile_id, "relationshipChanges": []},
        "participants": [_agent_to_lite(a), _agent_to_lite(b)],
        "ctx": {"currentTick": 10, "priorsInWindow": []},
        "expected": _environmental_modifiers(e, [a, b], w0),
    })

    # 2 same-kind priors → multiplier 0.85**2 ≈ 0.7225
    priors = [
        LegendEvent(event_id="px", tick=8, pack_id="scp", tile_id="t1",
                     event_kind="containment-breach", participants=["a"],
                     outcome="success"),
        LegendEvent(event_id="py", tick=9, pack_id="scp", tile_id="t1",
                     event_kind="containment-breach", participants=["b"],
                     outcome="success"),
    ]
    w1 = _W(10, priors)
    cases.append({
        "name": "novelty_decay_2_priors",
        "event": {"eventKind": e.event_kind, "outcome": e.outcome,
                   "tileId": e.tile_id, "relationshipChanges": []},
        "participants": [_agent_to_lite(a), _agent_to_lite(b)],
        "ctx": {
            "currentTick": 10,
            "priorsInWindow": [
                {"tileId": p.tile_id, "eventKind": p.event_kind} for p in priors
            ],
        },
        "expected": _environmental_modifiers(e, [a, b], w1),
    })

    # Belief resonance: alice has a belief about bob → 1.15
    a2 = _make_agent("alice")
    a2.state_extra["beliefs"] = {"bob": "rival of mine"}
    b2 = _make_agent("bob")
    w2 = _W(10, [])
    cases.append({
        "name": "belief_resonance",
        "event": {"eventKind": e.event_kind, "outcome": e.outcome,
                   "tileId": e.tile_id, "relationshipChanges": []},
        "participants": [_agent_to_lite(a2), _agent_to_lite(b2)],
        "ctx": {"currentTick": 10, "priorsInWindow": []},
        "expected": _environmental_modifiers(e, [a2, b2], w2),
    })
    return cases


# ── 4. social metrics ──────────────────────────────────────────────────

def gen_social() -> list[dict]:
    cases = []

    # Case A: empty
    cases.append({
        "name": "empty",
        "agents": [],
        "opts": {},
        "expected": _metrics_to_json(compute_social_metrics([])),
    })

    # Case B: a small triangle + one isolate
    a = _make_agent("alice")
    b = _make_agent("bob")
    c = _make_agent("carol")
    d = _make_agent("dave")
    a.relationships["bob"] = Relationship(target_id="bob", affinity=80)
    b.relationships["alice"] = Relationship(target_id="alice", affinity=80)
    a.relationships["carol"] = Relationship(target_id="carol", affinity=50)
    c.relationships["alice"] = Relationship(target_id="alice", affinity=50)
    b.relationships["carol"] = Relationship(target_id="carol", affinity=40)
    c.relationships["bob"] = Relationship(target_id="bob", affinity=40)
    # dave isolated
    cases.append({
        "name": "triangle_plus_isolate",
        "agents": [_agent_for_metrics(x) for x in (a, b, c, d)],
        "opts": {},
        "expected": _metrics_to_json(compute_social_metrics([a, b, c, d])),
    })

    # Case C: two disconnected pairs, threshold filters one
    e1 = _make_agent("e")
    f1 = _make_agent("f")
    g1 = _make_agent("g")
    h1 = _make_agent("h")
    e1.relationships["f"] = Relationship(target_id="f", affinity=60)
    f1.relationships["e"] = Relationship(target_id="e", affinity=60)
    g1.relationships["h"] = Relationship(target_id="h", affinity=20)  # below threshold
    h1.relationships["g"] = Relationship(target_id="g", affinity=20)
    cases.append({
        "name": "threshold_filters_weak_pair",
        "agents": [_agent_for_metrics(x) for x in (e1, f1, g1, h1)],
        "opts": {"minAbsAffinity": 30},
        "expected": _metrics_to_json(
            compute_social_metrics([e1, f1, g1, h1], min_abs_affinity=30)
        ),
    })
    return cases


def _metrics_to_json(m) -> dict:
    return {
        "nAgents": m.n_agents,
        "nEdges": m.n_edges,
        "avgDegree": m.avg_degree,
        "isolated": list(m.isolated),
        "components": [list(c) for c in m.components],
        "topCentral": [[a, d] for a, d in m.top_central],
        "clusteringGlobal": m.clustering_global,
        "nComponents": m.n_components,
        "biggestComponentSize": m.biggest_component_size,
    }


# ── main ───────────────────────────────────────────────────────────────

def main() -> None:
    payloads = {
        "dice_importance.json": gen_importance(),
        "dice_outcome.json": gen_outcome(),
        "dice_modifiers.json": gen_modifiers(),
        "social_metrics.json": gen_social(),
    }
    for name, data in payloads.items():
        path = FIX_DIR / name
        path.write_text(json.dumps(data, indent=2, ensure_ascii=False))
        print(f"wrote {path.relative_to(FIX_DIR.parent.parent.parent)}  ({len(data)} cases)")


if __name__ == "__main__":
    main()
