"""Consequence propagation — chain reactions from events."""

from __future__ import annotations

from pathlib import Path

from living_world.core.world import World
from living_world.tick_loop import TickEngine
from living_world.world_pack import load_all_packs

PACKS_DIR = Path(__file__).resolve().parents[1] / "world_packs"


def test_lethal_event_emotion_ripples_to_witnesses():
    """Witnesses to a lethal event get an emotion ripple (fear up).
    The old per-event STAT_RIPPLES table was replaced with categorical
    emotion deltas — verify witness fear actually rises.
    """
    import uuid
    from living_world.core.event import LegendEvent
    from living_world.tick_loop import TickStats

    packs = load_all_packs(PACKS_DIR, ["scp"])
    world = World()
    for p in packs:
        world.mark_pack_loaded(p.pack_id)
        for t in p.tiles:
            world.add_tile(t)
        for a in p.personas:
            world.add_agent(a)

    engine = TickEngine(world, packs, seed=42)
    tile_id = next(iter(t.tile_id for t in world.all_tiles()
                        if len(world.agents_in_tile(t.tile_id)) >= 2))
    residents = world.agents_in_tile(tile_id)
    victim = residents[0]
    witnesses = residents[1:]

    # Snapshot baseline emotions
    baseline = {w.agent_id: w.get_emotions().get("fear", 0.0) for w in witnesses}

    world.current_tick = 1
    event = LegendEvent(
        event_id=str(uuid.uuid4()), tick=1, pack_id="scp",
        tile_id=tile_id, event_kind="173-snap-neck",
        participants=[victim.agent_id], outcome="failure",
        template_rendering=f"[{tile_id}] {victim.display_name} died.",
        importance=0.7,
    )
    engine._process_event(event, TickStats(tick=1))

    # At least one witness's fear must have risen.
    rose = [w for w in witnesses
            if w.get_emotions().get("fear", 0.0) > baseline[w.agent_id]]
    assert rose, "Witness emotion ripple did not fire — fear should rise after lethal event."


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
