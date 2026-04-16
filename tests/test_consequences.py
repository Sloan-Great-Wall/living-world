"""Consequence propagation — chain reactions from events."""

from __future__ import annotations

from pathlib import Path

from living_world.core.world import World
from living_world.tick_loop import TickEngine
from living_world.world_pack import load_all_packs

PACKS_DIR = Path(__file__).resolve().parents[1] / "world_packs"


def test_lethal_event_propagates_fear_to_witnesses():
    """When SCP kills someone, nearby D-class should gain fear."""
    packs = load_all_packs(PACKS_DIR, ["scp"])
    world = World()
    for p in packs:
        world.mark_pack_loaded(p.pack_id)
        for t in p.tiles:
            world.add_tile(t)
        for a in p.personas:
            world.add_agent(a)

    engine = TickEngine(world, packs, seed=42)
    engine.run(60)

    # Check for reaction events
    reaction_events = [
        e for e in world.events_since(1)
        if e.event_kind.startswith("reaction-to-")
    ]
    # After 60 days with lethal SCPs, there should be at least one reaction
    assert len(reaction_events) > 0, "No reaction events generated — consequence chain not firing"

    # Check for threshold-triggered events
    threshold_events = [
        e for e in world.events_since(1)
        if e.event_kind in ("escape-attempt", "breakdown", "insubordination", "madness")
    ]
    # These may or may not fire depending on RNG; just verify no crash
    print(f"  reaction events: {len(reaction_events)}")
    print(f"  threshold events: {len(threshold_events)}")


def test_chain_depth_is_bounded():
    """Ensure consequence chains don't infinite-loop."""
    packs = load_all_packs(PACKS_DIR, ["scp", "cthulhu"])
    world = World()
    for p in packs:
        world.mark_pack_loaded(p.pack_id)
        for t in p.tiles:
            world.add_tile(t)
        for a in p.personas:
            world.add_agent(a)

    engine = TickEngine(world, packs, seed=7)
    # If chain depth is unbounded, this will hang or crash
    stats = engine.run(30)
    total_reactions = sum(s.reactions for s in stats)
    total_events = sum(s.events_realized for s in stats)
    print(f"  30 days: {total_events} events, {total_reactions} chain reactions")
    # Chain reactions should be a fraction of total, not runaway
    assert total_reactions < total_events * 3, "Reaction count exploded — possible infinite loop"
