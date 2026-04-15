"""Shared helpers to bootstrap a world + run simulation from dashboard + CLI."""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path

from living_world.config import Settings
from living_world.core.world import World
from living_world.llm import EnhancementRouter, MockTier2Client, MockTier3Client, OllamaClient, TierBudget
from living_world.llm.base import LLMClient
from living_world.llm.dialogue import DialogueGenerator
from living_world.llm.move_advisor import LLMMoveAdvisor
from living_world.memory import AgentMemoryStore, MockEmbedder, OllamaEmbedder
from living_world.persistence import MemoryRepository, PostgresRepository
from living_world.persistence.repository import Repository
from living_world.statmachine.debate import DebatePhase
from living_world.statmachine.historical_figures import PromotionConfig
from living_world.tick_loop import TickEngine
from living_world.world_pack import load_all_packs


def build_tier_client(
    provider: str,
    *,
    ollama_model: str,
    ollama_url: str,
    timeout: float,
    declared_tier: int,
) -> LLMClient | None:
    if provider == "mock":
        return MockTier2Client() if declared_tier == 2 else MockTier3Client()
    if provider == "ollama":
        return OllamaClient(
            model=ollama_model,
            base_url=ollama_url,
            declared_tier=declared_tier,
            timeout=timeout,
        )
    return None


def build_router(settings: Settings) -> EnhancementRouter:
    t2 = build_tier_client(
        settings.llm.tier2_provider,
        ollama_model=settings.llm.ollama_tier2_model,
        ollama_url=settings.llm.ollama_base_url,
        timeout=settings.llm.ollama_timeout_seconds,
        declared_tier=2,
    )
    t3 = build_tier_client(
        settings.llm.tier3_provider,
        ollama_model=settings.llm.ollama_tier3_model,
        ollama_url=settings.llm.ollama_base_url,
        timeout=settings.llm.ollama_timeout_seconds,
        declared_tier=3,
    )
    budget = TierBudget(
        tier2_tokens_limit=settings.budget.tier2_tokens_per_day,
        tier3_tokens_limit=settings.budget.tier3_tokens_per_day,
    )
    # Optional advanced LLM components
    dialogue = None
    if settings.llm.dynamic_dialogue_enabled and t3 is not None:
        dialogue = DialogueGenerator(t3)

    debate = None
    if settings.llm.debate_enabled and t3 is not None and t2 is not None:
        debate = DebatePhase(
            orchestrator=t3, worker=t2,
            min_stakeholders=settings.llm.debate_min_stakeholders,
            max_stakeholders=settings.llm.debate_max_stakeholders,
        )

    router = EnhancementRouter(
        tier2=t2, tier3=t3, budget=budget,
        dialogue_generator=dialogue,
        debate_phase=debate,
        debate_threshold=settings.llm.debate_threshold,
        # world is set later by make_engine after bootstrap
    )
    router.TIER2_THRESHOLD = settings.importance.tier2_threshold
    router.TIER3_THRESHOLD = settings.importance.tier3_threshold
    return router


def bootstrap_world(packs_dir: Path, pack_ids: list[str]) -> tuple[World, list]:
    loaded = load_all_packs(packs_dir, pack_ids)
    world = World()
    for pack in loaded:
        world.mark_pack_loaded(pack.pack_id)
        for tile in pack.tiles:
            world.add_tile(tile)
        for agent in pack.personas:
            world.add_agent(agent)
    return world, loaded


def build_repository(settings: Settings) -> Repository:
    if settings.persistence.backend == "postgres":
        return PostgresRepository(settings.persistence.postgres_dsn)
    return MemoryRepository()


def build_memory_store(settings: Settings) -> AgentMemoryStore | None:
    if not settings.memory.enabled or settings.memory.embedder == "none":
        return None
    if settings.memory.embedder == "ollama":
        embedder = OllamaEmbedder(
            model=settings.memory.ollama_embed_model,
            base_url=settings.llm.ollama_base_url,
        )
    else:
        embedder = MockEmbedder()
    return AgentMemoryStore(embedder=embedder)


def make_engine(world: World, loaded: list, settings: Settings, seed: int, repository: Repository | None = None) -> TickEngine:
    router = build_router(settings)
    router.world = world  # router needs world ref for dialogue/debate
    memory = build_memory_store(settings)
    engine = TickEngine(
        world, loaded, seed=seed, router=router,
        repository=repository,
        memory=memory,
        snapshot_every_ticks=settings.persistence.snapshot_every_ticks,
        reflect_every_ticks=settings.memory.reflect_every_ticks,
    )
    # Optional LLM-driven movement advisor
    if settings.llm.llm_movement_enabled:
        t2 = build_tier_client(
            settings.llm.tier2_provider,
            ollama_model=settings.llm.ollama_tier2_model,
            ollama_url=settings.llm.ollama_base_url,
            timeout=settings.llm.ollama_timeout_seconds,
            declared_tier=2,
        )
        if t2 is not None:
            engine.movement.llm_advisor = LLMMoveAdvisor(t2)
            engine.movement.llm_hf_only = settings.llm.llm_movement_hf_only
            engine.movement.llm_chance = settings.llm.llm_movement_chance
    hf_cfg = settings.historical_figures
    engine.hf_registry.config = PromotionConfig(
        spotlight_threshold=hf_cfg.spotlight_threshold,
        notable_threshold=hf_cfg.notable_threshold,
        notable_count_for_promotion=hf_cfg.notable_count_for_promotion,
        strong_relationship_affinity=hf_cfg.strong_relationship_affinity,
        inactivity_days_for_demotion=hf_cfg.inactivity_days_for_demotion,
    )
    # Apply storyteller overrides if set
    so = settings.storyteller
    for st in engine.storytellers.values():
        if so.force_personality:
            st.config.personality = so.force_personality
        if so.max_events_per_day_override is not None:
            st.config.max_events_per_day = so.max_events_per_day_override
        if so.tension_target_override is not None:
            st.config.tension_target = so.tension_target_override
    return engine


def group_events_by_day(world: World) -> dict[int, dict[str, list]]:
    by_day: dict[int, dict[str, list]] = defaultdict(lambda: defaultdict(list))
    for e in world.events_since(1):
        by_day[e.tick][e.pack_id].append(e)
    return by_day
