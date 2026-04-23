"""TickEngine phases — the 11 stages of one virtual day.

Refactor of the old 150-LOC `TickEngine.step()` god-method into an
explicit pipeline of small classes. Each phase has a single
responsibility, can be enabled/disabled/reordered, and may fail
without crashing the rest of the tick.

See KNOWN_ISSUES.md issue #2.

CONTRACT
--------
Each Phase exposes:
  - `name: str`              — short id for logging / metrics
  - `run(engine, t, stats)`  — mutate engine.world / stats; raise on
                                 fatal failure (caught by step()).

Phases consume the engine instance as a service container — they read
optional members like `engine.chronicler`, `engine.agent_planner`,
etc. and no-op if the member is None. This keeps phases independent
of which LLM modules are wired in.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from living_world.rules.decay import auto_satisfy_routine_needs, decay_needs_and_emotions
from living_world.rules.heat import hot_tiles as _rule_hot_tiles
from living_world.agents.event_curator import promote_emergent, prune_tail


# ── Base ───────────────────────────────────────────────────────────────────

class Phase(ABC):
    """One stage of a tick. Single responsibility, fails in isolation."""

    name: str = "phase"

    @abstractmethod
    def run(self, engine, t: int, stats) -> None: ...


# ── Concrete phases (declared in execution order) ──────────────────────────

class DecayPhase(Phase):
    name = "decay"
    def run(self, engine, t, stats):
        decay_needs_and_emotions(engine.world)


class NeedsSatisfyPhase(Phase):
    """Hungry agents eat, threatened ones rest. Pure rule layer."""
    name = "needs_satisfy"
    def run(self, engine, t, stats):
        auto_satisfy_routine_needs(engine.world, engine.rng)


class ColdStartPlanPhase(Phase):
    """Mark any HF without a weekly_plan as stale so ReplanPhase fills it.

    Eliminates the goal=None void on tick 1 instead of waiting for the
    weekly cadence (t % 7 == 0). See KNOWN_ISSUES #14 / planner notes.
    """
    name = "cold_start_plan"
    def run(self, engine, t, stats):
        if engine.agent_planner is None:
            return
        for agent in engine.world.historical_figures():
            if not agent.state_extra.get("weekly_plan"):
                agent.state_extra["plan_stale"] = True


class ReplanStalePhase(Phase):
    name = "replan_stale"
    def run(self, engine, t, stats):
        engine._replan_stale_agents(t)


class MovementPhase(Phase):
    name = "movement"
    def run(self, engine, t, stats):
        moves = engine.movement.tick()
        stats.movements = len(moves)
        log = engine.tick_logger
        if log:
            for agent_id, from_tile, to_tile, method in moves:
                log.movement(agent_id, from_tile, to_tile, method)


class InteractionsPhase(Phase):
    """Lethal encounters, companionship, flight — pure rule layer."""
    name = "interactions"
    def run(self, engine, t, stats):
        log = engine.tick_logger
        for emergent in engine.interactions.tick():
            if log:
                log.interaction(
                    emergent.event_kind, emergent.participants,
                    emergent.outcome, emergent.tile_id,
                )
            engine._process_event(emergent, stats)


class StorytellerPhase(Phase):
    """Per-tile storyteller proposes events; resolver realises them."""
    name = "storyteller"
    def run(self, engine, t, stats):
        log = engine.tick_logger
        for tile_id, st in engine.storytellers.items():
            proposals = st.tick_daily(t)
            stats.proposals += len(proposals)
            for prop in proposals:
                if log:
                    log.storyteller_proposal(tile_id, prop.event_kind, prop.priority)
                template = engine._event_template(prop.pack_id, prop.event_kind)
                if template is None:
                    continue
                event = engine.resolver.realize(
                    prop, template, t, consciousness=engine.consciousness,
                )
                if event is None:
                    continue
                if log:
                    log.event_resolved(
                        event.event_id, event.event_kind, event.tile_id,
                        event.participants, event.outcome,
                        roll=None, dc=None,
                        importance=event.importance,
                        conscious_verdict=None,
                    )
                engine._process_event(event, stats)


class EmergentPhase(Phase):
    """LLM invents novel events on hot tiles + curator promotes hits."""
    name = "emergent"
    def run(self, engine, t, stats):
        if engine.emergent_proposer is None:
            return
        log = engine.tick_logger
        hot = _rule_hot_tiles(engine.world, limit=engine.emergent_max_per_tick)
        for tile in hot:
            event = engine.emergent_proposer.propose(tile, engine.world)
            if event is None:
                continue
            if log:
                log.emergent_event(
                    event.event_kind, event.tile_id, event.participants,
                )
            engine._process_event(event, stats)
            pack = engine.packs.get(event.pack_id)
            if pack is not None:
                promoted = promote_emergent(event, pack.events)
                if promoted is not None and log:
                    log.template_promoted(
                        event.event_kind, event.pack_id, event.importance,
                    )


class WeeklyMaintenancePhase(Phase):
    """Demote inactive HFs + prune chronically dull promoted templates.

    Fires every 7 ticks. Never touches YAML-authored templates.
    """
    name = "weekly_maintenance"
    def run(self, engine, t, stats):
        if t % 7 != 0:
            return
        engine.hf_registry.demote_inactive(t)
        log = engine.tick_logger
        for pack_id, pack in engine.packs.items():
            dropped = prune_tail(pack.events, t)
            if dropped and log:
                for kind in dropped:
                    log.template_pruned(kind, pack_id)


class ChroniclerPhase(Phase):
    """说书人 — descriptive chapter summaries every N ticks. Never steers."""
    name = "chronicler"
    def run(self, engine, t, stats):
        if engine.chronicler is None:
            return
        if t - engine._last_chronicle_tick < engine.chronicle_every_ticks:
            return
        log = engine.tick_logger
        for pack_id in engine.world.loaded_packs:
            chapter = engine.chronicler.write_chapter(
                engine.world, pack_id,
                since_tick=max(1, engine._last_chronicle_tick + 1),
            )
            if chapter is None:
                continue
            engine.world.add_chapter({
                "tick": chapter.tick,
                "pack_id": chapter.pack_id,
                "title": chapter.title,
                "body": chapter.body,
                "event_ids": chapter.event_ids,
            })
            if log:
                log.chapter_written(chapter.tick, chapter.title)
        engine._last_chronicle_tick = t


class WeeklyPlanPhase(Phase):
    """One LLM call per (HF) agent every plan_every_ticks days."""
    name = "weekly_plan"
    def run(self, engine, t, stats):
        if engine.agent_planner is None:
            return
        if t % engine.plan_every_ticks != 0:
            return
        log = engine.tick_logger
        targets = (
            list(engine.world.historical_figures())
            if engine.plan_hf_only
            else [a for a in engine.world.living_agents()]
        )
        for agent in targets:
            plan = engine.agent_planner.plan_for_agent(agent, engine.world, engine.memory)
            if plan:
                agent.state_extra["weekly_plan"] = plan
                agent.state_extra["weekly_plan_tick"] = t
                if log:
                    log.plan_generated(agent.agent_id, plan)


class ReflectionPhase(Phase):
    """Park-style memory reflection + decay (HF-only to keep embed cost low).

    Order matters: reflect FIRST (so the abstraction sees fresh raw
    memories), THEN decay (so we never prune a raw memory that the
    reflection step is about to fold into a belief).
    """
    name = "reflection"
    def run(self, engine, t, stats):
        if engine.memory is None:
            return
        if t % engine.reflect_every_ticks != 0:
            return
        log = engine.tick_logger
        for agent in engine.world.historical_figures():
            beliefs_before = len(agent.get_beliefs())
            entry = engine.memory.reflect(agent.agent_id, t, agent=agent)
            engine.memory.decay(agent.agent_id, t)
            beliefs_after = len(agent.get_beliefs())
            n_new = beliefs_after - beliefs_before
            if log and entry is not None and hasattr(log, "reflection"):
                log.reflection(agent.agent_id, t, n_new)


class SnapshotPhase(Phase):
    name = "snapshot"
    def run(self, engine, t, stats):
        if engine.repository is None:
            return
        if t % engine.snapshot_every_ticks != 0:
            return
        try:
            engine.repository.save_world(engine.world)
        except Exception as exc:  # noqa: BLE001 — persist failure is non-fatal
            print(f"[persist] snapshot failed: {exc}")


# ── Default pipeline ───────────────────────────────────────────────────────

DEFAULT_PIPELINE: list[Phase] = [
    DecayPhase(),
    NeedsSatisfyPhase(),
    ColdStartPlanPhase(),
    ReplanStalePhase(),
    MovementPhase(),
    InteractionsPhase(),
    StorytellerPhase(),
    EmergentPhase(),
    WeeklyMaintenancePhase(),
    ChroniclerPhase(),
    WeeklyPlanPhase(),
    ReflectionPhase(),
    SnapshotPhase(),
]
