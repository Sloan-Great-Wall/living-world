"""Verify repository wiring — engine writes to repo, repo can replay."""

from __future__ import annotations

from pathlib import Path

from living_world.core.world import World
from living_world.llm import EnhancementRouter, MockTier2Client, MockTier3Client
from living_world.persistence import MemoryRepository
from living_world.tick_loop import TickEngine
from living_world.world_pack import load_all_packs

PACKS_DIR = Path(__file__).resolve().parents[1] / "world_packs"


def test_memory_repo_captures_events_and_snapshot():
    packs = load_all_packs(PACKS_DIR, ["scp", "liaozhai"])
    world = World()
    for p in packs:
        world.mark_pack_loaded(p.pack_id)
        for t in p.tiles:
            world.add_tile(t)
        for a in p.personas:
            world.add_agent(a)

    repo = MemoryRepository()
    repo.save_world(world)
    router = EnhancementRouter(tier2=MockTier2Client(), tier3=MockTier3Client())
    engine = TickEngine(world, packs, seed=11, router=router, repository=repo, snapshot_every_ticks=5)
    engine.run(20)

    # memory repo holds a reference to the same World, so world_events == repo list
    replayed = repo.list_events(since_tick=0, limit=1000)
    assert len(replayed) == world.event_count()
    assert all(e.tier_used in (1, 2, 3) for e in replayed)

    # round-trip save/load
    back = repo.load_world()
    assert back is world


def test_pack_filter_works():
    packs = load_all_packs(PACKS_DIR, ["scp", "liaozhai"])
    world = World()
    for p in packs:
        world.mark_pack_loaded(p.pack_id)
        for t in p.tiles:
            world.add_tile(t)
        for a in p.personas:
            world.add_agent(a)

    repo = MemoryRepository()
    repo.save_world(world)
    engine = TickEngine(world, packs, seed=3, repository=repo)
    engine.run(15)

    scp_only = repo.list_events(pack_id="scp")
    assert all(e.pack_id == "scp" for e in scp_only)
    assert 0 < len(scp_only) < world.event_count()
