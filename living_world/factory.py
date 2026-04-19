"""Shared helpers to bootstrap a world + run simulation from dashboard + CLI."""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path

from living_world.config import Settings
from living_world.core.world import World
from living_world.llm import OllamaClient
from living_world.llm.base import LLMClient
from living_world.agents.narrator import Narrator, NarratorBudget
from living_world.agents.perception import SubjectivePerception
from living_world.agents.self_update import AgentSelfUpdate
from living_world.agents.dialogue import DialogueGenerator
from living_world.agents.move_advisor import LLMMoveAdvisor
from living_world.memory import AgentMemoryStore, OllamaEmbedder
from living_world.persistence import MemoryRepository, Repository
from living_world.rules.historical_figures import PromotionConfig
from living_world.agents.planner import AgentPlanner
from living_world.agents.chronicler import Chronicler
from living_world.agents.emergent import EmergentEventProposer
from living_world.tick_logger import TickLogger
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
    if provider == "ollama":
        return OllamaClient(
            model=ollama_model,
            base_url=ollama_url,
            declared_tier=declared_tier,
            timeout=timeout,
        )
    return None


def build_narrator(settings: Settings) -> Narrator:
    t3 = build_tier_client(
        settings.llm.tier3_provider,
        ollama_model=settings.llm.ollama_tier3_model,
        ollama_url=settings.llm.ollama_base_url,
        timeout=settings.llm.ollama_timeout_seconds,
        declared_tier=3,
    )
    budget = NarratorBudget(tokens_limit=settings.budget.tier3_tokens_per_day)
    narrator = Narrator(tier3=t3, budget=budget)
    narrator.TIER3_THRESHOLD = settings.importance.tier3_threshold
    return narrator


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
    return MemoryRepository()


def build_memory_store(settings: Settings) -> AgentMemoryStore | None:
    if not settings.memory.enabled or settings.memory.embedder == "none":
        return None
    embedder = OllamaEmbedder(
        model=settings.memory.ollama_embed_model,
        base_url=settings.llm.ollama_base_url,
    )
    return AgentMemoryStore(embedder=embedder)


def make_engine(world: World, loaded: list, settings: Settings, seed: int, repository: Repository | None = None, tick_logger: TickLogger | None = None) -> TickEngine:
    narrator = build_narrator(settings)
    memory = build_memory_store(settings)
    engine = TickEngine(
        world, loaded, seed=seed, narrator=narrator,
        repository=repository,
        memory=memory,
        snapshot_every_ticks=settings.persistence.snapshot_every_ticks,
        reflect_every_ticks=settings.memory.reflect_every_ticks,
    )
    engine.tick_logger = tick_logger
    # Optional LLM-driven movement advisor
    # LLM-driven movement advisor + consciousness layer share a Tier 2 client
    agent_client = None
    if settings.llm.llm_movement_enabled or settings.llm.conscious_override_enabled:
        agent_client = build_tier_client(
            settings.llm.tier2_provider,
            ollama_model=settings.llm.ollama_tier2_model,
            ollama_url=settings.llm.ollama_base_url,
            timeout=settings.llm.ollama_timeout_seconds,
            declared_tier=2,
        )

    if settings.llm.llm_movement_enabled and agent_client is not None:
        engine.movement.llm_advisor = LLMMoveAdvisor(agent_client, memory_store=memory)
        engine.movement.llm_hf_only = settings.llm.llm_movement_hf_only
        engine.movement.llm_chance = settings.llm.llm_movement_chance
    engine.movement.memory_store = memory
    engine.movement.goal_bonus = settings.llm.goal_driven_movement_bonus

    # Weekly planner — one LLM call per HF per week, produces structured plan
    if settings.llm.weekly_planning_enabled and agent_client is not None:
        engine.agent_planner = AgentPlanner(agent_client)
        engine.plan_hf_only = settings.llm.weekly_planning_hf_only

    # A→B dialogue reaction loop. Mutates affinity + beliefs from
    # actual conversation content. If no Tier-3 client, never fires.
    if agent_client is not None:
        engine.dialogue_generator = DialogueGenerator(agent_client)
    engine.conversation_loop_enabled = settings.llm.conversation_loop_enabled

    # Chronicler — descriptive chapter summaries. Never steers.
    # Uses Tier 3 if available (richer prose), otherwise Tier 2.
    tier3_client_for_chronicler = build_tier_client(
        settings.llm.tier3_provider,
        ollama_model=settings.llm.ollama_tier3_model,
        ollama_url=settings.llm.ollama_base_url,
        timeout=settings.llm.ollama_timeout_seconds,
        declared_tier=3,
    )
    chronicler_client = tier3_client_for_chronicler or agent_client
    if settings.llm.chronicler_enabled and chronicler_client is not None:
        engine.chronicler = Chronicler(chronicler_client)
        engine.chronicle_every_ticks = settings.llm.chronicle_every_ticks

    # Emergent event proposer — LLM invents novel events
    if settings.llm.emergent_events_enabled and agent_client is not None:
        engine.emergent_proposer = EmergentEventProposer(agent_client)
        engine.emergent_max_per_tick = settings.llm.emergent_max_per_tick

    # Subjective perception — each agent's memory is rewritten from their POV.
    if settings.llm.subjective_perception_enabled and agent_client is not None:
        engine.perception = SubjectivePerception(agent_client)
        engine.perception_threshold = settings.llm.subjective_perception_threshold

    # AgentSelfUpdate — LLM mutates participant's inner state after big events.
    if settings.llm.self_update_enabled and agent_client is not None:
        engine.self_update = AgentSelfUpdate(agent_client)
        engine.self_update_threshold = settings.llm.self_update_threshold

    if settings.llm.conscious_override_enabled and agent_client is not None:
        from living_world.agents.conscience import ConsciousnessLayer
        engine.consciousness = ConsciousnessLayer(
            agent_client,
            importance_threshold=settings.llm.conscious_override_threshold,
            activation_chance=settings.llm.conscious_override_chance,
            memory=memory,  # enables memory-informed veto/adjust decisions
        )

    hf_cfg = settings.historical_figures
    engine.hf_registry.config = PromotionConfig(
        spotlight_threshold=hf_cfg.spotlight_threshold,
        notable_threshold=hf_cfg.notable_threshold,
        notable_count_for_promotion=hf_cfg.notable_count_for_promotion,
        strong_relationship_affinity=hf_cfg.strong_relationship_affinity,
        inactivity_days_for_demotion=hf_cfg.inactivity_days_for_demotion,
    )
    # Apply storyteller overrides if set, plus wire the world + goal bonus
    # for Phase E (goal-aligned event weighting).
    so = settings.storyteller
    for st in engine.storytellers.values():
        if so.force_personality:
            st.config.personality = so.force_personality
        if so.max_events_per_day_override is not None:
            st.config.max_events_per_day = so.max_events_per_day_override
        if so.tension_target_override is not None:
            st.config.tension_target = so.tension_target_override
        st.world = world
        st.goal_bonus = settings.llm.goal_aligned_event_bonus
    return engine


def group_events_by_day(world: World) -> dict[int, dict[str, list]]:
    by_day: dict[int, dict[str, list]] = defaultdict(lambda: defaultdict(list))
    for e in world.events_since(1):
        by_day[e.tick][e.pack_id].append(e)
    return by_day


def build_world_state_json(
    world: World,
    *,
    selected_agent: str | None = None,
    max_events: int = 50,
) -> dict:
    """Serialize World state into the JSON shape consumed by the Canvas map JS."""
    tiles = []
    for t in world.all_tiles():
        tiles.append({
            "tile_id": t.tile_id,
            "display_name": t.display_name,
            "primary_pack": t.primary_pack,
            "tile_type": t.tile_type,
            "x": t.x,
            "y": t.y,
            "radius": t.radius,
        })

    agents = []
    for a in world.all_agents():
        if not a.is_alive():
            continue
        agents.append({
            "agent_id": a.agent_id,
            "display_name": a.display_name,
            "pack_id": a.pack_id,
            "is_historical_figure": a.is_historical_figure,
            "tags": sorted(a.tags),
            "current_tile": a.current_tile,
            "x": a.x,
            "y": a.y,
            "persona_card": a.persona_card,
            "current_goal": a.current_goal,
            "life_stage": a.life_stage.value,
            "age": a.age,
            "attributes": {k: v for k, v in list(a.attributes.items())[:8]},
        })

    recent_events = []
    all_events = world.events_since(1)
    for e in all_events[-max_events:]:
        recent_events.append({
            "event_id": e.event_id,
            "tick": e.tick,
            "pack_id": e.pack_id,
            "event_kind": e.event_kind,
            "importance": e.importance,
            "tier_used": e.tier_used,
            "narrative": e.best_rendering(),
            "participants": e.participants,
        })

    return {
        "tick": world.current_tick,
        "packs": world.loaded_packs,
        "tiles": tiles,
        "agents": agents,
        "recent_events": recent_events,
        "selected_agent": selected_agent,
    }
