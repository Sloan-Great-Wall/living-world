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
from living_world.statmachine.importance import score_event_importance
from living_world.world_pack.loader import EventTemplate


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

    def _roll_outcome(self, template: EventTemplate, participants: list[Agent]) -> str:
        """Simple DC check. 'success' / 'failure' / 'neutral'."""
        cfg = template.dice_roll or {}
        if not cfg:
            return "neutral"
        dc = int(cfg.get("dc", 12))
        stat = cfg.get("stat")
        mod = int(cfg.get("mod", 0))
        bonus = 0
        if stat and participants:
            # take the best modifier across participants
            bonuses = []
            for p in participants:
                v = p.attributes.get(stat, 0)
                if isinstance(v, (int, float)):
                    bonuses.append(int((float(v) - 10) / 2))  # D&D-style
            if bonuses:
                bonus = max(bonuses)
        roll = self.rng.randint(1, 20) + bonus + mod
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

        outcome = self._roll_outcome(template, participants)
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
        return event
