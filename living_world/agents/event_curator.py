"""EventCurator — promote breakout emergent events into the template pool,
and retire chronically dull templates.

Two pure-rule operations (no LLM needed; LLM created the original emergent):

  promote_emergent(event, pack_events)
    Called when an emergent event fires with importance ≥ promote_threshold.
    Synthesizes a reusable EventTemplate from it and registers it in the
    pack's event pool, marked source="promoted". Storyteller can now fire
    it again like any YAML template (with cooldown).

  prune_tail(pack_events, ...)
    Periodically remove templates whose stats are bad — low fire_count
    AND low avg_importance — but never touch source="yaml" templates
    (the hand-authored core stays). Only "promoted" templates can be
    elevated AND retired by the system.

Result: the world's repertoire grows organically. Hand-authored templates
form a stable core; LLM emergent events that earn their keep enter the
pool; failed experiments fade.
"""

from __future__ import annotations

from living_world.core.event import LegendEvent
from living_world.world_pack import EventTemplate


def make_template_from_emergent(event: LegendEvent) -> EventTemplate:
    """Synthesize a reusable EventTemplate from one emergent LegendEvent.

    The narrative becomes the success-template; outcome-specific branches
    are minimal because the LLM produced one specific instance, not a
    family. Cooldown defaults to 7 days so it doesn't dominate the pool.
    """
    narrative = event.template_rendering or event.best_rendering()
    # Make the template render with the same body but a participant-name
    # placeholder so future fires can substitute different agents.
    if event.participants:
        first_name = event.participants[0]
        # Replace agent_id occurrences with $a for the template — best effort.
        templated = narrative.replace(first_name, "$a")
    else:
        templated = narrative
    return EventTemplate(
        event_kind=event.event_kind,
        description=f"Promoted from an emergent event on day {event.tick}.",
        trigger_conditions={"min_participants": max(1, len(event.participants))},
        dice_roll={},  # no dice — outcome was already authored
        outcomes={
            event.outcome or "neutral": {"template": templated},
        },
        cooldown_days=7,
        base_importance=min(0.6, max(0.2, event.importance * 0.8)),
        source="promoted",
        # Inherit one fire (this very event) so the new template starts
        # with non-zero stats and survives the next prune pass.
        fire_count=1,
        importance_sum=event.importance,
        last_fired_tick=event.tick,
    )


def promote_emergent(
    event: LegendEvent,
    pack_events: dict[str, EventTemplate],
    *,
    threshold: float = 0.7,
) -> EventTemplate | None:
    """If the emergent event qualifies, register it in the pack pool.

    Skips:
      - already-existing event_kind (don't overwrite)
      - importance below threshold
    Returns the new template, or None if no promotion happened.
    """
    if not event.is_emergent:
        return None
    if event.importance < threshold:
        return None
    if event.event_kind in pack_events:
        return None
    tpl = make_template_from_emergent(event)
    pack_events[event.event_kind] = tpl
    return tpl


def prune_tail(
    pack_events: dict[str, EventTemplate],
    current_tick: int,
    *,
    min_age_ticks: int = 14,
    keep_floor_per_pack: int = 30,
) -> list[str]:
    """Drop promoted templates that aren't earning their keep.

    A template is a candidate for retirement when ALL hold:
      - source == "promoted" (never touch yaml-authored)
      - has been around for ≥ min_age_ticks
      - hasn't fired in the last min_age_ticks
      - avg_importance < 0.35 OR fire_count < 2

    Won't reduce the pool below `keep_floor_per_pack` total entries.
    Returns the event_kinds that were dropped (for logging).
    """
    if len(pack_events) <= keep_floor_per_pack:
        return []
    dropped: list[str] = []
    candidates = []
    for kind, tpl in pack_events.items():
        if tpl.source != "promoted":
            continue
        age = current_tick - tpl.last_fired_tick
        if age < min_age_ticks:
            continue
        if tpl.avg_importance < 0.35 or tpl.fire_count < 2:
            candidates.append((kind, tpl.fire_count, tpl.avg_importance))
    # Worst first — lowest avg_importance, then lowest fire_count.
    candidates.sort(key=lambda x: (x[2], x[1]))
    for kind, _, _ in candidates:
        if len(pack_events) <= keep_floor_per_pack:
            break
        del pack_events[kind]
        dropped.append(kind)
    return dropped
