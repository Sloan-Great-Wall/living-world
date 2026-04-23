"""Dice-roll resolver. Takes an EventProposal + candidate participants, produces a LegendEvent.

Tier 1 only — no LLM. Output `template_rendering` uses pack event template strings.
"""

from __future__ import annotations

import random
import uuid
from string import Template
from typing import Any

from living_world.core.agent import Agent
from living_world.core.event import EventProposal, LegendEvent
from living_world.core.world import World
from living_world.world_pack import EventTemplate

# ──────────────────────────────────────────────────────────────
# Importance scoring — decides Tier routing
# ──────────────────────────────────────────────────────────────
# Target distribution: ~95% tier1, ~4% tier2, ~1% tier3.
# Primary signal: `base_importance` from event template.
# Modifiers: spotlight kinds, historical figures, player proximity.

SPOTLIGHT_EVENT_KINDS: set[str] = {
    "containment-breach",
    "descent",
    "possession",
    "cult-ritual",
    "renlao-tryst",
    "karmic-return",
    "heart-swap",
    "yaksha-attack",
    "682-tests",
    "silver-key",
    "096-sighting-risk",
    "o5-memo",
}


def score_event_importance(
    event: LegendEvent,
    participants: list[Agent],
    *,
    tile_has_active_player: bool = False,
    base_importance: float = 0.1,
) -> float:
    """Return 0.0-1.0 importance score for tier routing."""
    score = float(base_importance)
    if event.event_kind in SPOTLIGHT_EVENT_KINDS and base_importance >= 0.5:
        score = max(score, 0.7)
    # Only 2+ HFs interacting is notable (single HFs are common)
    if sum(1 for p in participants if p.is_historical_figure) >= 2:
        score += 0.08
    if len(event.relationship_changes) >= 2:
        score += 0.05
    if tile_has_active_player:
        score += 0.35
    if event.outcome == "failure" and base_importance >= 0.5:
        score += 0.1
    return min(1.0, max(0.0, score))


def _environmental_modifiers(
    event: LegendEvent,
    participants: list[Agent],
    world: World,
    *,
    novelty_window: int = 7,
) -> float:
    """Return a multiplier (≈0.5-1.5) reflecting context the base score misses.

    Two signals:

      Novelty decay
        Same event_kind already happened in the same tile in the last
        `novelty_window` ticks → multiplier <1.0. The 3rd 173-snap-neck
        this week is less newsworthy than the 1st.

      Resonance with participant inner state
        Any participant has a strong belief about a co-participant, OR
        a co-participant's name appears in their weekly_plan / motivations
        → multiplier >1.0. This event matters more to them personally.

    Combined multiplicatively. Bounded to [0.5, 1.5] so even hot events
    can't blow past the importance scale, and even stale ones still register.
    """
    multiplier = 1.0

    # ── Novelty decay ──
    since = max(1, world.current_tick - novelty_window)
    same_in_window = sum(
        1
        for e in world.events_since(since)
        if e.tile_id == event.tile_id and e.event_kind == event.event_kind
    )
    if same_in_window >= 1:
        # 1 prior = 0.85, 2 priors = 0.72, 3 priors = 0.61 (geometric)
        multiplier *= 0.85**same_in_window

    # ── Resonance with participant inner state ──
    if len(participants) >= 2:
        ids = {p.agent_id for p in participants}
        names_lower = {p.display_name.lower() for p in participants}
        for p in participants:
            others = ids - {p.agent_id}
            # Belief topic mentions another participant id → resonance
            beliefs = p.get_beliefs() if hasattr(p, "get_beliefs") else {}
            if any(o in beliefs for o in others):
                multiplier *= 1.15
                break
            # Weekly plan / motivations mention another participant by name
            plan = p.get_weekly_plan() if hasattr(p, "get_weekly_plan") else {}
            mots = p.get_motivations() if hasattr(p, "get_motivations") else []
            blob = (
                " ".join(
                    str(x).lower()
                    for key in ("seek", "goals_this_week", "avoid")
                    for x in (plan.get(key) or [])
                )
                + " "
                + " ".join(str(m).lower() for m in mots)
            )
            if any(n in blob for n in names_lower if n != p.display_name.lower()):
                multiplier *= 1.15
                break

    return max(0.5, min(1.5, multiplier))


class EventResolver:
    # World-wide same-tick same-kind dedup: stop the same template from
    # firing more than once across all tiles in the same virtual day.
    # Set to None to disable; integer = max occurrences per tick across world.
    SAME_KIND_PER_TICK_CAP: int = 1

    def __init__(self, world: World, rng: random.Random | None = None) -> None:
        self.world = world
        self.rng = rng or random.Random()
        self._kind_tick_count: dict[tuple[int, str], int] = {}

    def _eligible_participants(
        self, proposal: EventProposal, template: EventTemplate
    ) -> list[Agent]:
        tile = self.world.get_tile(proposal.tile_id)
        if tile is None:
            return []
        all_residents = self.world.agents_in_tile(tile.tile_id)
        required = set(proposal.required_tags)
        if not required:
            return all_residents
        return [a for a in all_residents if required.issubset(a.tags)]

    @staticmethod
    def _inventory_bonus(participant: Agent, template: EventTemplate) -> int:
        """Sum power of items whose tags are relevant to this event template.

        An item contributes its power if any of its tags overlap the event
        template's `required_tags` OR `event_kind`. So the monk's
        九节锡杖 (tags: anti-anomaly) gives him +9 against an "anomaly"
        event, but +0 against a "tea-ceremony" event.
        """
        if not participant.inventory:
            return 0
        kind_l = template.event_kind.lower()
        req = set(template.trigger_conditions.get("required_tags") or [])
        relevant_terms = {kind_l, *(t.lower() for t in req)}
        bonus = 0
        for item in participant.inventory:
            item_terms = {kind_l, *(t.lower() for t in item.tags)}
            # Match if any item tag appears in event's relevant terms,
            # or any event term in item tags (substring is too loose,
            # use exact-set overlap).
            if item_terms & relevant_terms:
                bonus += item.power
        return bonus

    def _roll_outcome(self, template: EventTemplate, participants: list[Agent]) -> str:
        """Simple DC check. 'success' / 'failure' / 'neutral'."""
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
                        bonuses.append(int((float(v) - 10) / 2))  # D&D-style
                if bonuses:
                    bonus = max(bonuses)
            # Inventory bonus: best item-power across participants. Caps at
            # +5 so a magic sword cannot trivialise every roll.
            inv_bonuses = [self._inventory_bonus(p, template) for p in participants]
            inv_bonus = min(5, max(inv_bonuses)) if inv_bonuses else 0
        roll = self.rng.randint(1, 20) + bonus + mod + inv_bonus
        if roll >= dc:
            return "success"
        if roll <= max(1, dc - 10):
            return "failure"
        return "neutral"

    def _apply_outcome(
        self,
        event: LegendEvent,
        participants: list[Agent],
        outcome_spec: dict[str, Any],
        tick: int,
    ) -> None:
        # stat changes
        for stat_change in outcome_spec.get("stat_changes", []) or []:
            target_sel = stat_change.get("target", "any")
            attr = stat_change["attribute"]
            delta = stat_change["delta"]
            targets: list[Agent] = []
            if target_sel == "any" and participants:
                targets = [self.rng.choice(participants)]
            elif target_sel == "all":
                targets = participants
            for t in targets:
                cur = t.attributes.get(attr, 0)
                if isinstance(cur, (int, float)):
                    t.attributes[attr] = float(cur) + float(delta)
                    event.stat_changes.setdefault(t.agent_id, {})[attr] = float(delta)

        # relationship changes (pairwise among participants)
        if len(participants) >= 2:
            for rel_change in outcome_spec.get("relationship_changes", []) or []:
                delta = int(rel_change.get("delta", 0))
                a, b = participants[0], participants[1]
                a.adjust_affinity(b.agent_id, delta, tick)
                b.adjust_affinity(a.agent_id, delta, tick)
                event.relationship_changes.append(
                    {"a": a.agent_id, "b": b.agent_id, "delta": delta}
                )

    @staticmethod
    def _required_slots(template_str: str) -> int:
        """Highest participant slot referenced (a=1, b=2, c=3)."""
        needs = 0
        for slot, n in (
            ("$a", 1),
            ("$b", 2),
            ("$c", 3),
            ("${a}", 1),
            ("${b}", 2),
            ("${c}", 3),
        ):
            if slot in template_str:
                needs = max(needs, n)
        return needs

    def _render_template(
        self,
        template_str: str,
        participants: list[Agent],
        tile_id: str,
    ) -> str | None:
        """Substitute ${a/b/c} with participant names. Returns None if the
        template references more slots than we have participants — the
        caller should skip the event entirely rather than emit a
        "?"-leaking narrative."""
        if not template_str:
            names = [p.display_name for p in participants]
            return f"[{tile_id}] {', '.join(names) or '(none)'} — event occurred."
        if self._required_slots(template_str) > len(participants):
            return None
        mapping = {
            "tile": tile_id,
            "a": participants[0].display_name if participants else "",
            "b": participants[1].display_name if len(participants) >= 2 else "",
            "c": participants[2].display_name if len(participants) >= 3 else "",
        }
        try:
            return Template(template_str).safe_substitute(mapping)
        except Exception:
            return template_str

    def realize(
        self,
        proposal: EventProposal,
        template: EventTemplate,
        tick: int,
        consciousness=None,
    ) -> LegendEvent | None:
        # ── World-wide same-kind cap ──
        if self.SAME_KIND_PER_TICK_CAP is not None:
            key = (tick, proposal.event_kind)
            if self._kind_tick_count.get(key, 0) >= self.SAME_KIND_PER_TICK_CAP:
                return None

        participants = self._eligible_participants(proposal, template)
        min_participants = int((template.trigger_conditions or {}).get("min_participants", 1))
        if len(participants) < min_participants:
            return None

        # limit to top N by dice-relevant stat if specified
        max_participants = int((template.trigger_conditions or {}).get("max_participants", 2))
        if len(participants) > max_participants:
            self.rng.shuffle(participants)
            participants = participants[:max_participants]

        # ─── Subconscious: roll the dice ───
        outcome = self._roll_outcome(template, participants)

        # ─── Conscious: LLM may override ───
        verdict = None
        if consciousness is not None and consciousness.should_activate(template):
            verdict = consciousness.consider(proposal, template, participants, self.world)
            if verdict is not None:
                if verdict.vetoes:
                    return None  # character wouldn't do this
                if verdict.adjusts:
                    outcome = verdict.outcome  # override subconscious roll

        outcome_spec = (template.outcomes or {}).get(outcome, {})

        event = LegendEvent(
            event_id=str(uuid.uuid4()),
            tick=tick,
            pack_id=proposal.pack_id,
            tile_id=proposal.tile_id,
            event_kind=proposal.event_kind,
            participants=[p.agent_id for p in participants],
            outcome=outcome,
        )
        self._apply_outcome(event, participants, outcome_spec, tick)

        rendering = self._render_template(
            outcome_spec.get("template", ""), participants, proposal.tile_id
        )
        if rendering is None:
            # Template requires more participants than available; drop
            # the event so we never emit "?"-leaking narrative. Caller
            # treats None as "skip this proposal, try another".
            return None
        event.template_rendering = rendering

        base_score = score_event_importance(
            event,
            participants,
            base_importance=float(template.base_importance),
        )
        # Environmental modifiers: novelty decay + resonance with inner state.
        # Multiplier ≈ 0.5 - 1.5; clamped at the end to [0, 1].
        env_mult = _environmental_modifiers(event, participants, self.world)
        event.importance = max(0.0, min(1.0, base_score * env_mult))
        # Track usage stats so the Event Library panel + tail elimination
        # have something to score templates by. Mutates the YAML-loaded
        # template object in place; persists for session lifetime only.
        template.fire_count += 1
        template.importance_sum += event.importance
        template.last_fired_tick = tick
        # Bump the world-wide same-kind counter only on successful realize.
        if self.SAME_KIND_PER_TICK_CAP is not None:
            key = (tick, proposal.event_kind)
            self._kind_tick_count[key] = self._kind_tick_count.get(key, 0) + 1
        # If consciousness intervened, annotate so UI can show the ⟡ mark
        if verdict is not None and verdict.adjusts:
            event.stat_changes.setdefault("_consciousness", {})
            event.stat_changes["_consciousness"]["override"] = 1.0
            if verdict.reason:
                event.template_rendering = event.template_rendering + f"  ⟡ {verdict.reason}"
        return event
