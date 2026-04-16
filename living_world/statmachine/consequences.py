"""Consequence propagation — the chain-reaction engine.

When an event resolves, this module:
  1. Applies stat/attribute changes to ALL affected agents (not just participants)
  2. Detects threshold crossings (fear > 80 → flee; sanity ≤ 0 → breakdown)
  3. Generates REACTION events from affected agents
  4. Those reactions may trigger further consequences (up to MAX_CHAIN_DEPTH)

This is what makes the world feel alive:
    SCP-173 kills D-9001 →
        witnesses gain fear +25 →
        D-9007 (fear now 90) attempts escape →
        escape fails → D-9007 punished, compliance -20 →
        Dr. Glass notices morale pattern → files report

Without this module, events are dead-end snapshots.
"""

from __future__ import annotations

import random
import uuid
from dataclasses import dataclass, field
from typing import Any

from living_world.core.agent import Agent
from living_world.core.event import LegendEvent
from living_world.core.world import World


MAX_CHAIN_DEPTH = 3  # prevent infinite loops
MAX_REACTIONS_PER_EVENT = 4  # cap how many agents react to one event


# ══════════════════════════════════════════════════════════════
# Propagation rules — attribute changes that ripple to non-participants
# ══════════════════════════════════════════════════════════════

@dataclass
class PropagationRule:
    """When event_kind matches and conditions hold, apply changes to witnesses."""
    event_kind: str
    witness_tags: set[str]           # which agents in the same tile are affected
    exclude_participants: bool = True # don't double-apply to direct participants
    attribute_changes: dict[str, float] = field(default_factory=dict)
    relationship_delta_to_victim: int = 0  # sympathy/fear toward the victim
    relationship_delta_to_attacker: int = 0  # fear/hatred toward the attacker
    narrative_template: str = ""


# These fire on witnesses in the same tile as the event
PROPAGATION_RULES: list[PropagationRule] = [
    # --- SCP lethal events spread fear ---
    PropagationRule(
        event_kind="173-snap-neck",
        witness_tags={"d-class", "staff", "researcher"},
        attribute_changes={"fear": 25, "morale": -15},
        relationship_delta_to_attacker=-30,
        narrative_template="[{tile}] {witness} saw what SCP-173 did to {victim}. They haven't spoken since.",
    ),
    PropagationRule(
        event_kind="682-breach",
        witness_tags={"d-class", "staff", "researcher", "field-agent"},
        attribute_changes={"fear": 20, "morale": -10},
        relationship_delta_to_attacker=-20,
        narrative_template="[{tile}] {witness} was in the corridor when SCP-682 broke through. The screaming hasn't stopped echoing.",
    ),
    PropagationRule(
        event_kind="049-treatment",
        witness_tags={"d-class", "staff"},
        attribute_changes={"fear": 15, "morale": -8},
        narrative_template="[{tile}] {witness} heard the Plague Doctor's tools through the wall. They filed no report.",
    ),
    PropagationRule(
        event_kind="106-pocket-dimension",
        witness_tags={"d-class", "staff"},
        attribute_changes={"fear": 30, "morale": -20},
        narrative_template="[{tile}] {witness} watched {victim} sink into the floor. The stain remains.",
    ),
    PropagationRule(
        event_kind="096-rampage",
        witness_tags={"d-class", "staff", "researcher"},
        attribute_changes={"fear": 35, "morale": -25},
        narrative_template="[{tile}] {witness} heard SCP-096's scream. Some sounds don't leave you.",
    ),
    # --- Cthulhu sanity ripple ---
    PropagationRule(
        event_kind="descent",
        witness_tags={"investigator", "academic", "local"},
        attribute_changes={"sanity": -8},
        narrative_template="[{tile}] {witness} watched {victim} lose composure. A familiar dread settled deeper.",
    ),
    PropagationRule(
        event_kind="cult-ritual",
        witness_tags={"investigator", "local", "law-enforcement"},
        attribute_changes={"sanity": -5, "arcane_knowledge": 2},
        narrative_template="[{tile}] {witness} overheard fragments of the rite. They understood more than they wanted to.",
    ),
    PropagationRule(
        event_kind="possession",
        witness_tags={"investigator", "academic"},
        attribute_changes={"sanity": -12},
        narrative_template="[{tile}] {witness} was in the room when {victim}'s voice changed. The memory won't compress.",
    ),
    # --- Liaozhai supernatural ripple ---
    PropagationRule(
        event_kind="yaksha-takes-soul",
        witness_tags={"scholar", "mortal"},
        attribute_changes={"courage": -15, "fear_of_buddhism": -10},
        narrative_template="[{tile}] {witness} smelled something wrong in the air and whispered a sutra they didn't know they remembered.",
    ),
    PropagationRule(
        event_kind="renlao-tryst",
        witness_tags={"scholar", "mortal", "fox-spirit"},
        attribute_changes={"charm": 3},
        narrative_template="[{tile}] {witness} sensed the warmth between {victim} and another. Even the lanterns seemed gentler.",
    ),
    # --- Positive propagation: SCP-999 cheers everyone ---
    PropagationRule(
        event_kind="999-uplift",
        witness_tags={"d-class", "staff", "researcher"},
        attribute_changes={"morale": 8, "fear": -5},
        narrative_template="[{tile}] {witness} saw SCP-999 and couldn't help a half-smile.",
    ),
]


# ══════════════════════════════════════════════════════════════
# Threshold triggers — when an attribute crosses a line, generate a reaction event
# ══════════════════════════════════════════════════════════════

@dataclass
class ThresholdTrigger:
    """When `attribute` passes `threshold` in the given direction, fire a reaction."""
    attribute: str
    threshold: float
    direction: str  # "above" or "below"
    reaction_kind: str
    reaction_template: str
    attribute_reset: dict[str, float] = field(default_factory=dict)  # optional reset after trigger
    kills: bool = False
    tags_required: set[str] = field(default_factory=set)  # only agents with these tags


THRESHOLD_TRIGGERS: list[ThresholdTrigger] = [
    # --- Fear overwhelm → escape attempt ---
    ThresholdTrigger(
        attribute="fear", threshold=80, direction="above",
        reaction_kind="escape-attempt",
        reaction_template="[{tile}] {agent} broke. They ran for the nearest exit, eyes wide, breath ragged.",
        attribute_reset={"fear": -30},  # spent the adrenaline
        tags_required={"d-class"},
    ),
    # --- Morale collapse → breakdown (sentient mortals only) ---
    ThresholdTrigger(
        attribute="morale", threshold=10, direction="below",
        reaction_kind="breakdown",
        reaction_template="[{tile}] {agent} sat down on the floor and did not get up. Dr. Glass was called.",
        attribute_reset={"morale": 15},
        tags_required={"d-class", "staff", "researcher", "field-agent", "psychologist",
                        "scholar", "mortal", "investigator"},
    ),
    # --- Sanity zero → madness (mortals only, not cosmic entities) ---
    ThresholdTrigger(
        attribute="sanity", threshold=5, direction="below",
        reaction_kind="madness",
        reaction_template="[{tile}] {agent} began speaking in a language they have never studied. The episode lasted forty minutes.",
        attribute_reset={"sanity": 15},
        tags_required={"investigator", "academic", "local", "reporter",
                        "d-class", "staff", "researcher", "scholar", "mortal"},
    ),
    # --- Cultivation breakthrough ---
    ThresholdTrigger(
        attribute="cultivation", threshold=90, direction="above",
        reaction_kind="breakthrough",
        reaction_template="[{tile}] {agent} felt a meridian open. The wind stirred where no window stood.",
        tags_required={"fox-spirit", "deity"},
    ),
    # --- Fear of Buddhism drops → yaksha weakens ---
    ThresholdTrigger(
        attribute="fear_of_buddhism", threshold=20, direction="below",
        reaction_kind="yaksha-emboldened",
        reaction_template="[{tile}] The yaksha's shadow stretched further tonight. The old monk's sutras felt thinner.",
        tags_required={"demon"},
    ),
    # --- Insight threshold → pattern discovery ---
    ThresholdTrigger(
        attribute="insight", threshold=95, direction="above",
        reaction_kind="pattern-discovered",
        reaction_template="[{tile}] {agent} connected the dots. The implications made them close the notebook and lock the drawer.",
        attribute_reset={"insight": -5},
        tags_required={"researcher", "psychologist", "investigator"},
    ),
    # --- Compliance collapse → insubordination ---
    ThresholdTrigger(
        attribute="compliance", threshold=15, direction="below",
        reaction_kind="insubordination",
        reaction_template="[{tile}] {agent} refused a direct order. The silence afterward was absolute.",
        attribute_reset={"compliance": 10},
        tags_required={"d-class"},
    ),
]


# ══════════════════════════════════════════════════════════════
# Main engine
# ══════════════════════════════════════════════════════════════

class ConsequencePropagator:
    """Processes an event's aftermath: attribute ripple → threshold checks → reaction events."""

    def __init__(self, world: World, rng: random.Random | None = None) -> None:
        self.world = world
        self.rng = rng or random.Random()
        # build lookup for propagation rules
        self._prop_by_kind: dict[str, list[PropagationRule]] = {}
        for rule in PROPAGATION_RULES:
            self._prop_by_kind.setdefault(rule.event_kind, []).append(rule)

    def _apply_attr_delta(self, agent: Agent, attr: str, delta: float) -> None:
        """Safely adjust a numeric attribute. Create if missing."""
        cur = agent.attributes.get(attr, 50)
        if isinstance(cur, (int, float)):
            agent.attributes[attr] = max(0, min(100, float(cur) + delta))

    def _check_thresholds(self, agent: Agent, tick: int) -> list[LegendEvent]:
        """If any attribute crossed a trigger threshold, generate reaction events."""
        reactions: list[LegendEvent] = []
        for trigger in THRESHOLD_TRIGGERS:
            # Tag filter
            if trigger.tags_required and not (trigger.tags_required & agent.tags):
                continue
            val = agent.attributes.get(trigger.attribute)
            if val is None or not isinstance(val, (int, float)):
                continue
            val = float(val)
            fired = (
                (trigger.direction == "above" and val >= trigger.threshold)
                or (trigger.direction == "below" and val <= trigger.threshold)
            )
            if not fired:
                continue
            # Don't repeat the same trigger for the same agent within 5 ticks
            cooldown_key = f"_trigger_cd_{trigger.reaction_kind}"
            last_fired = agent.state_extra.get(cooldown_key, 0)
            if tick - last_fired < 5:
                continue
            agent.state_extra[cooldown_key] = tick

            # Apply resets
            for attr, delta in trigger.attribute_reset.items():
                self._apply_attr_delta(agent, attr, delta)

            text = trigger.reaction_template.format(
                tile=agent.current_tile, agent=agent.display_name,
            )
            evt = LegendEvent(
                event_id=str(uuid.uuid4()),
                tick=tick,
                pack_id=agent.pack_id,
                tile_id=agent.current_tile,
                event_kind=trigger.reaction_kind,
                participants=[agent.agent_id],
                outcome="failure" if trigger.kills else "neutral",
                template_rendering=text,
                importance=0.55,
            )
            reactions.append(evt)
        return reactions

    def propagate(self, event: LegendEvent, tick: int, depth: int = 0) -> list[LegendEvent]:
        """Main entry. Returns list of reaction events (may be empty).

        Reactions are themselves fed back through propagate() up to MAX_CHAIN_DEPTH.
        """
        if depth >= MAX_CHAIN_DEPTH:
            return []

        all_reactions: list[LegendEvent] = []

        # ── Step 1: Attribute ripple to witnesses ──
        rules = self._prop_by_kind.get(event.event_kind, [])
        for rule in rules:
            tile = self.world.get_tile(event.tile_id)
            if tile is None:
                continue
            witnesses = self.world.agents_in_tile(tile.tile_id)
            participant_ids = set(event.participants)

            affected_count = 0
            for witness in witnesses:
                if not witness.is_alive():
                    continue
                if rule.exclude_participants and witness.agent_id in participant_ids:
                    continue
                if not (rule.witness_tags & witness.tags):
                    continue
                if affected_count >= MAX_REACTIONS_PER_EVENT:
                    break

                # Apply attribute changes
                for attr, delta in rule.attribute_changes.items():
                    self._apply_attr_delta(witness, attr, delta)

                # Relationship changes toward victim/attacker
                if rule.relationship_delta_to_victim and len(event.participants) >= 2:
                    victim_id = event.participants[1]
                    witness.adjust_affinity(victim_id, rule.relationship_delta_to_victim, tick)
                if rule.relationship_delta_to_attacker and event.participants:
                    attacker_id = event.participants[0]
                    witness.adjust_affinity(attacker_id, rule.relationship_delta_to_attacker, tick)

                # Log the witness reaction
                if rule.narrative_template:
                    # victim = second participant (the one killed/affected)
                    victim_name = "someone"
                    if len(event.participants) >= 2:
                        v = self.world.get_agent(event.participants[1])
                        victim_name = v.display_name if v else "someone"
                    elif len(event.participants) == 1:
                        v = self.world.get_agent(event.participants[0])
                        victim_name = v.display_name if v else "someone"
                    text = rule.narrative_template.format(
                        tile=event.tile_id,
                        witness=witness.display_name,
                        victim=victim_name,
                    )
                    reaction_evt = LegendEvent(
                        event_id=str(uuid.uuid4()),
                        tick=tick,
                        pack_id=witness.pack_id,
                        tile_id=event.tile_id,
                        event_kind=f"reaction-to-{event.event_kind}",
                        participants=[witness.agent_id],
                        outcome="neutral",
                        template_rendering=text,
                        importance=0.30,
                    )
                    all_reactions.append(reaction_evt)
                    affected_count += 1

        # ── Step 2: Threshold checks on ALL agents in the tile ──
        tile = self.world.get_tile(event.tile_id)
        if tile is not None:
            for agent in self.world.agents_in_tile(tile.tile_id):
                if not agent.is_alive():
                    continue
                threshold_reactions = self._check_thresholds(agent, tick)
                all_reactions.extend(threshold_reactions)

        # ── Step 3: Recursive — reactions may trigger further consequences ──
        next_gen: list[LegendEvent] = []
        for reaction in all_reactions:
            next_gen.extend(self.propagate(reaction, tick, depth=depth + 1))
        all_reactions.extend(next_gen)

        return all_reactions
