"""Consequence engine — the fundamental change layer.

Design principle: there is NO chain depth limit. Every tick is simply:
    all agents act (based on current state) → actions produce changes → next tick.

The chain unfolds ACROSS ticks naturally, not recursively within one tick.
This module handles the "actions produce changes" part:

TWO LAYERS OF CHANGE:
  1. Stat layer (every event, always):
     - Numeric attributes (fear, morale, sanity, cultivation, ...)
     - Relationships (affinity deltas)
     - Inventory (gain/lose items)
     These change freely on every event. Like breathing — constant, cheap.

  2. Description layer (rare, conditional, guarded):
     - persona_card rewrite (e.g. "SCP-049 learned empathy" — massive lore change)
     - Tag mutations (gaining/losing "anomaly", "undead", etc.)
     - Containment class upgrades
     - Life stage transitions (young→prime, prime→deceased)
     These require explicit conditions and are low-probability by design.

Within a single tick, this module is called ONCE per event. No recursion.
The next tick's movement/storyteller/interactions will naturally react to
the changed attributes — that IS the chain reaction.
"""

from __future__ import annotations

import random
import uuid
from dataclasses import dataclass, field
from typing import Any

from living_world.core.agent import Agent, LifeStage
from living_world.core.event import LegendEvent
from living_world.core.world import World


# ══════════════════════════════════════════════════════════════
# STAT LAYER — fires on every qualifying event, modifies numerics
# ══════════════════════════════════════════════════════════════

@dataclass
class StatRipple:
    """When event_kind matches, apply numeric changes to witnesses in the same tile."""
    event_kind: str
    witness_tags: set[str]
    attribute_changes: dict[str, float] = field(default_factory=dict)
    relationship_to_victim: int = 0    # sympathy/horror toward victim
    relationship_to_attacker: int = 0  # hatred/fear toward attacker
    exclude_participants: bool = True
    narrative: str = ""  # short witness-reaction text


STAT_RIPPLES: list[StatRipple] = [
    # SCP lethal
    StatRipple("173-snap-neck", {"d-class", "staff", "researcher"},
               {"fear": 25, "morale": -15}, relationship_to_attacker=-30,
               narrative="[{tile}] {witness} saw what SCP-173 did to {victim}. They haven't spoken since."),
    StatRipple("682-breach", {"d-class", "staff", "researcher", "field-agent"},
               {"fear": 20, "morale": -10}, relationship_to_attacker=-20,
               narrative="[{tile}] {witness} was in the corridor when 682 broke through."),
    StatRipple("049-treatment", {"d-class", "staff"},
               {"fear": 15, "morale": -8},
               narrative="[{tile}] {witness} heard the Plague Doctor's tools through the wall."),
    StatRipple("106-pocket-dimension", {"d-class", "staff"},
               {"fear": 30, "morale": -20},
               narrative="[{tile}] {witness} watched {victim} sink into the floor. The stain remains."),
    StatRipple("096-rampage", {"d-class", "staff", "researcher"},
               {"fear": 35, "morale": -25},
               narrative="[{tile}] {witness} heard SCP-096's scream. Some sounds don't leave you."),
    # Cthulhu
    StatRipple("descent", {"investigator", "academic", "local"},
               {"sanity": -8},
               narrative="[{tile}] {witness} watched {victim} lose composure. A familiar dread settled deeper."),
    StatRipple("cult-ritual", {"investigator", "local", "law-enforcement"},
               {"sanity": -5, "arcane_knowledge": 2},
               narrative="[{tile}] {witness} overheard fragments of the rite. They understood more than they wanted to."),
    StatRipple("possession", {"investigator", "academic"},
               {"sanity": -12},
               narrative="[{tile}] {witness} was in the room when {victim}'s voice changed."),
    # Liaozhai
    StatRipple("yaksha-takes-soul", {"scholar", "mortal"},
               {"courage": -15},
               narrative="[{tile}] {witness} smelled something wrong and whispered a sutra they didn't know they remembered."),
    StatRipple("renlao-tryst", {"scholar", "mortal", "fox-spirit"},
               {"charm": 3},
               narrative="[{tile}] {witness} sensed warmth between {victim} and another. Even the lanterns seemed gentler."),
    # Positive
    StatRipple("999-uplift", {"d-class", "staff", "researcher"},
               {"morale": 8, "fear": -5},
               narrative="[{tile}] {witness} saw SCP-999 and couldn't help a half-smile."),
]


# ══════════════════════════════════════════════════════════════
# DESCRIPTION LAYER — rare mutations to agent identity
# ══════════════════════════════════════════════════════════════

@dataclass
class DescriptionMutation:
    """A rare, guarded change to an agent's core identity.
    Only fires when ALL conditions are met.
    """
    name: str
    # conditions — ALL must be true
    required_tags: set[str] = field(default_factory=set)
    required_event_kinds: set[str] = field(default_factory=set)
    attribute_condition: dict[str, tuple[str, float]] = field(default_factory=dict)
    # e.g. {"fear": (">=", 90), "morale": ("<=", 10)}
    probability: float = 0.1  # even if conditions met, this % actually fires
    # effects
    add_tags: set[str] = field(default_factory=set)
    remove_tags: set[str] = field(default_factory=set)
    set_attributes: dict[str, Any] = field(default_factory=dict)
    new_goal: str | None = None
    new_life_stage: LifeStage | None = None
    narrative: str = ""


DESCRIPTION_MUTATIONS: list[DescriptionMutation] = [
    DescriptionMutation(
        name="d-class-becomes-traumatized",
        required_tags={"d-class"},
        attribute_condition={"fear": (">=", 85), "morale": ("<=", 15)},
        probability=0.3,
        add_tags={"traumatized"},
        new_goal="survive at any cost",
        narrative="[{tile}] {agent} is no longer the person who arrived. The Foundation broke something fundamental.",
    ),
    DescriptionMutation(
        name="investigator-goes-dark",
        required_tags={"investigator"},
        attribute_condition={"sanity": ("<=", 10)},
        probability=0.2,
        add_tags={"corrupted"},
        remove_tags={"investigator"},
        new_goal="seek the truth regardless of cost",
        narrative="[{tile}] {agent} stopped filing reports. Their notes now read like scripture.",
    ),
    DescriptionMutation(
        name="fox-spirit-achieves-form",
        required_tags={"fox-spirit"},
        attribute_condition={"cultivation": (">=", 85)},
        probability=0.15,
        add_tags={"human-form"},
        set_attributes={"cultivation": 90},
        narrative="[{tile}] {agent} felt fur recede. For the first time, they saw their own hands.",
    ),
    DescriptionMutation(
        name="scp-containment-escalation",
        required_tags={"anomaly"},
        required_event_kinds={"containment-breach", "682-breach"},
        attribute_condition={"threat": (">=", 90)},
        probability=0.1,
        set_attributes={"containment_class": "Keter"},
        narrative="[{tile}] O5 Council has reclassified {agent} to Keter. All leave is cancelled.",
    ),
    DescriptionMutation(
        name="scholar-gains-resolve",
        required_tags={"scholar"},
        attribute_condition={"moral_resolve": (">=", 95)},
        probability=0.2,
        add_tags={"unyielding"},
        narrative="[{tile}] {agent}'s spine straightened. Whatever comes next, they will not bend.",
    ),
    DescriptionMutation(
        name="cultist-ascends",
        required_tags={"cultist"},
        attribute_condition={"arcane_knowledge": (">=", 90)},
        probability=0.08,
        add_tags={"ascended"},
        new_life_stage=LifeStage.ELDER,
        narrative="[{tile}] {agent} spoke the final syllable. The room smelled of ozone and salt.",
    ),
]


# ══════════════════════════════════════════════════════════════
# Engine
# ══════════════════════════════════════════════════════════════

class ConsequenceEngine:
    """Applies stat + description changes from a resolved event.

    Called once per event, within a single tick. No recursion.
    The next tick naturally picks up changed attributes.
    """

    def __init__(self, world: World, rng: random.Random | None = None) -> None:
        self.world = world
        self.rng = rng or random.Random()
        self._ripple_by_kind: dict[str, list[StatRipple]] = {}
        for r in STAT_RIPPLES:
            self._ripple_by_kind.setdefault(r.event_kind, []).append(r)

    def _apply_delta(self, agent: Agent, attr: str, delta: float) -> None:
        cur = agent.attributes.get(attr, 50)
        if isinstance(cur, (int, float)):
            agent.attributes[attr] = max(0, min(100, float(cur) + delta))

    def _check_condition(self, agent: Agent, cond: dict[str, tuple[str, float]]) -> bool:
        for attr, (op, threshold) in cond.items():
            val = agent.attributes.get(attr)
            if val is None or not isinstance(val, (int, float)):
                return False
            v = float(val)
            if op == ">=" and v < threshold:
                return False
            if op == "<=" and v > threshold:
                return False
            if op == ">" and v <= threshold:
                return False
            if op == "<" and v >= threshold:
                return False
        return True

    def _victim_name(self, event: LegendEvent) -> str:
        if len(event.participants) >= 2:
            v = self.world.get_agent(event.participants[1])
            return v.display_name if v else "someone"
        if event.participants:
            v = self.world.get_agent(event.participants[0])
            return v.display_name if v else "someone"
        return "someone"

    def apply(self, event: LegendEvent) -> list[LegendEvent]:
        """Process one event's consequences. Returns witness-reaction legend entries."""
        tick = event.tick
        reactions: list[LegendEvent] = []

        # ── Stat layer: ripple to witnesses ──
        for ripple in self._ripple_by_kind.get(event.event_kind, []):
            # Use pre-snapshotted witnesses if available, else fall back to tile scan
            if event.witnesses:
                witness_agents = [
                    self.world.get_agent(wid) for wid in event.witnesses
                ]
                witness_agents = [a for a in witness_agents if a is not None and a.is_alive()]
            else:
                tile = self.world.get_tile(event.tile_id)
                if tile is None:
                    continue
                participant_ids = set(event.participants)
                witness_agents = [
                    a for a in self.world.agents_in_tile(tile.tile_id)
                    if a.is_alive() and a.agent_id not in participant_ids
                ]
            witnesses = [a for a in witness_agents if ripple.witness_tags & a.tags]
            for witness in witnesses[:4]:
                for attr, delta in ripple.attribute_changes.items():
                    self._apply_delta(witness, attr, delta)
                if ripple.relationship_to_attacker and event.participants:
                    witness.adjust_affinity(event.participants[0], ripple.relationship_to_attacker, tick)
                if ripple.relationship_to_victim and len(event.participants) >= 2:
                    witness.adjust_affinity(event.participants[1], ripple.relationship_to_victim, tick)

                if ripple.narrative:
                    text = ripple.narrative.format(
                        tile=event.tile_id,
                        witness=witness.display_name,
                        victim=self._victim_name(event),
                    )
                    reactions.append(LegendEvent(
                        event_id=str(uuid.uuid4()), tick=tick,
                        pack_id=witness.pack_id, tile_id=event.tile_id,
                        event_kind=f"witness-{event.event_kind}",
                        participants=[witness.agent_id],
                        outcome="neutral",
                        template_rendering=text,
                        importance=0.25,
                    ))

        # ── Description layer: check ALL agents in tile for rare mutations ──
        tile = self.world.get_tile(event.tile_id)
        if tile is not None:
            for agent in self.world.agents_in_tile(tile.tile_id):
                if not agent.is_alive():
                    continue
                for mutation in DESCRIPTION_MUTATIONS:
                    if mutation.required_tags and not (mutation.required_tags & agent.tags):
                        continue
                    if mutation.required_event_kinds and event.event_kind not in mutation.required_event_kinds:
                        continue
                    if not self._check_condition(agent, mutation.attribute_condition):
                        continue
                    # Cooldown: same mutation max once per 30 ticks
                    cd_key = f"_mut_cd_{mutation.name}"
                    if tick - agent.state_extra.get(cd_key, 0) < 30:
                        continue
                    if self.rng.random() > mutation.probability:
                        continue
                    # Fire the mutation
                    agent.state_extra[cd_key] = tick
                    agent.tags |= mutation.add_tags
                    agent.tags -= mutation.remove_tags
                    for attr, val in mutation.set_attributes.items():
                        agent.attributes[attr] = val
                    if mutation.new_goal:
                        agent.current_goal = mutation.new_goal
                    if mutation.new_life_stage:
                        agent.life_stage = mutation.new_life_stage

                    if mutation.narrative:
                        text = mutation.narrative.format(
                            tile=event.tile_id, agent=agent.display_name,
                        )
                        reactions.append(LegendEvent(
                            event_id=str(uuid.uuid4()), tick=tick,
                            pack_id=agent.pack_id, tile_id=event.tile_id,
                            event_kind=f"mutation-{mutation.name}",
                            participants=[agent.agent_id],
                            outcome="neutral",
                            template_rendering=text,
                            importance=0.65,
                        ))

        return reactions
