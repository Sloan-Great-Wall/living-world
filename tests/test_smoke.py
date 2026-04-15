"""Smoke tests — verify pack loading + tick loop produces events."""

from __future__ import annotations

from pathlib import Path

from living_world.core.world import World
from living_world.tick_loop import TickEngine
from living_world.world_pack import load_all_packs

PACKS_DIR = Path(__file__).resolve().parents[1] / "world_packs"


def _bootstrap(packs: list[str]) -> tuple[World, TickEngine]:
    loaded = load_all_packs(PACKS_DIR, packs)
    world = World()
    for pack in loaded:
        world.mark_pack_loaded(pack.pack_id)
        for tile in pack.tiles:
            world.add_tile(tile)
        for agent in pack.personas:
            world.add_agent(agent)
    return world, TickEngine(world, loaded, seed=7)


def test_single_pack_scp_runs():
    world, engine = _bootstrap(["scp"])
    assert world.summary()["agents_total"] >= 3
    stats = engine.run(30)
    total = sum(s.events_realized for s in stats)
    # Over 30 days with 3 tiles and 3 agents, storyteller should generate something.
    assert total > 0, "SCP pack produced zero events — storyteller/events table broken"


def test_single_pack_liaozhai_runs():
    world, engine = _bootstrap(["liaozhai"])
    stats = engine.run(30)
    assert sum(s.events_realized for s in stats) > 0


def test_mixed_packs_run():
    world, engine = _bootstrap(["scp", "liaozhai", "cthulhu"])
    assert world.summary()["packs"] == 3
    stats = engine.run(50)
    events = sum(s.events_realized for s in stats)
    assert events > 10, f"Mixed 3-pack run produced only {events} events"
    # verify each pack contributed
    packs_with_events = {e.pack_id for e in world.events_since(1)}
    assert packs_with_events == {"scp", "liaozhai", "cthulhu"}, packs_with_events


def test_importance_scoring_works():
    world, engine = _bootstrap(["scp", "liaozhai", "cthulhu"])
    engine.run(50)
    all_events = world.events_since(1)
    importances = [e.importance for e in all_events]
    assert max(importances) > 0.2, "No event crossed Tier 2 threshold — scoring broken"
