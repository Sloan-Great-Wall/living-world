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
    "containment-breach", "descent", "possession", "cult-ritual",
    "renlao-tryst", "karmic-return", "heart-swap", "yaksha-attack",
    "682-tests", "silver-key", "096-sighting-risk", "o5-memo",
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


class EventResolver:
    def __init__(self, world: World, rng: random.Random | None = None) -> None:
        self.world = world
        self.rng = rng or random.Random()

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

    def _render_template(
        self,
        template_str: str,
        participants: list[Agent],
        tile_id: str,
    ) -> str:
        if not template_str:
            names = [p.display_name for p in participants]
            return f"[{tile_id}] {', '.join(names) or '(none)'} — event occurred."
        mapping = {
            "tile": tile_id,
            "a": participants[0].display_name if participants else "?",
            "b": participants[1].display_name if len(participants) >= 2 else "?",
            "c": participants[2].display_name if len(participants) >= 3 else "?",
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
                    return None   # character wouldn't do this
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
        event.template_rendering = rendering

        event.importance = score_event_importance(
            event, participants,
            base_importance=float(template.base_importance),
        )
        # If consciousness intervened, annotate so UI can show the ⟡ mark
        if verdict is not None and verdict.adjusts:
            event.stat_changes.setdefault("_consciousness", {})
            event.stat_changes["_consciousness"]["override"] = 1.0
            if verdict.reason:
                event.template_rendering = (
                    event.template_rendering
                    + f"  ⟡ {verdict.reason}"
                )
        return event
