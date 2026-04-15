"""Main tick loop — drives storytellers + stat machine. Tier 1 only for now."""

from __future__ import annotations

import random
from dataclasses import dataclass

from living_world.core.world import World
from living_world.llm.router import EnhancementRouter
from living_world.memory.memory_store import AgentMemoryStore
from living_world.persistence.repository import Repository
from living_world.statmachine.historical_figures import HistoricalFigureRegistry
from living_world.statmachine.interactions import InteractionEngine
from living_world.statmachine.movement import MovementPolicy
from living_world.statmachine.resolver import EventResolver
from living_world.storyteller.tile_storyteller import TileStoryteller
from living_world.world_pack.loader import WorldPack


@dataclass
class TickStats:
    tick: int
    proposals: int = 0
    events_realized: int = 0
    spotlight_candidates: int = 0
    promotions: int = 0
    movements: int = 0
    tier1: int = 0
    tier2: int = 0
    tier3: int = 0


class TickEngine:
    """Wires together storytellers + resolver + world + registry + router."""

    def __init__(
        self,
        world: World,
        packs: list[WorldPack],
        seed: int = 42,
        router: EnhancementRouter | None = None,
        repository: Repository | None = None,
        memory: AgentMemoryStore | None = None,
        snapshot_every_ticks: int = 10,
        reflect_every_ticks: int = 7,
    ) -> None:
        self.world = world
        self.packs = {p.pack_id: p for p in packs}
        self.rng = random.Random(seed)
        self.resolver = EventResolver(world, random.Random(seed + 1))
        self.hf_registry = HistoricalFigureRegistry(world)
        self.movement = MovementPolicy(world, random.Random(seed + 2))
        self.interactions = InteractionEngine(world, random.Random(seed + 3))
        self.router = router or EnhancementRouter()
        self.repository = repository
        self.memory = memory
        self.snapshot_every_ticks = snapshot_every_ticks
        self.reflect_every_ticks = reflect_every_ticks

        # one storyteller per tile, using its primary pack's storyteller config
        self.storytellers: dict[str, TileStoryteller] = {}
        for tile in world.all_tiles():
            pack = self.packs.get(tile.primary_pack)
            if pack is None:
                continue
            self.storytellers[tile.tile_id] = TileStoryteller(
                tile=tile,
                config=pack.manifest.storyteller,
                event_pool=pack.events,
                rng=random.Random(seed ^ hash(tile.tile_id)),
            )

    def _event_template(self, pack_id: str, kind: str):
        pack = self.packs.get(pack_id)
        if pack is None:
            return None
        return pack.events.get(kind)

    def step(self) -> TickStats:
        self.world.current_tick += 1
        t = self.world.current_tick
        stats = TickStats(tick=t)

        # ── Movement phase: agents relocate BEFORE events resolve,
        # so new co-location can trigger new interactions this tick.
        moves = self.movement.tick()
        stats.movements = len(moves)

        # ── Emergent interactions (lethal encounters, companionship, flight) ──
        for emergent in self.interactions.tick():
            self.router.enhance(emergent)
            self.world.record_event(emergent)
            stats.events_realized += 1
            if emergent.importance >= 0.6:
                stats.spotlight_candidates += 1
            self.hf_registry.observe_event(emergent)

        for tile_id, st in self.storytellers.items():
            proposals = st.tick_daily(t)
            stats.proposals += len(proposals)
            for prop in proposals:
                template = self._event_template(prop.pack_id, prop.event_kind)
                if template is None:
                    continue
                event = self.resolver.realize(prop, template, t)
                if event is None:
                    continue
                # enhancement via Tier 2/3 router (mutates event in place)
                self.router.enhance(event)
                self.world.record_event(event)
                if self.repository is not None:
                    try:
                        self.repository.append_event(event)
                    except Exception as exc:  # noqa: BLE001
                        print(f"[persist] append_event failed: {exc}")
                stats.events_realized += 1
                if event.importance >= 0.6:
                    stats.spotlight_candidates += 1

                # promote newcomers if this event was notable enough
                promoted = self.hf_registry.observe_event(event)
                stats.promotions += len(promoted)

                # write memory entries for each participant (only if event has meaningful content)
                if self.memory is not None and event.importance >= 0.1:
                    for aid in event.participants:
                        self.memory.remember(
                            agent_id=aid, tick=t,
                            doc=event.best_rendering(),
                            kind="raw", importance=event.importance,
                            metadata={"event_id": event.event_id, "kind": event.event_kind},
                        )

        # periodic demotion (every 7 days)
        if t % 7 == 0:
            self.hf_registry.demote_inactive(t)

        # periodic reflection (only for historical figures to save embed calls)
        if self.memory is not None and t % self.reflect_every_ticks == 0:
            for agent in self.world.historical_figures():
                self.memory.reflect(agent.agent_id, t)

        # periodic full-world snapshot
        if self.repository is not None and t % self.snapshot_every_ticks == 0:
            try:
                self.repository.save_world(self.world)
            except Exception as exc:  # noqa: BLE001
                print(f"[persist] snapshot failed: {exc}")

        stats.tier1 = self.router.stats.tier1
        stats.tier2 = self.router.stats.tier2
        stats.tier3 = self.router.stats.tier3
        return stats

    def run(self, days: int) -> list[TickStats]:
        return [self.step() for _ in range(days)]
