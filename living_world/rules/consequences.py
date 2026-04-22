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
# WITNESS RIPPLE — categorical emotion writes for non-participants
# ══════════════════════════════════════════════════════════════
#
# For PARTICIPANTS: see agents/self_update.py — LLM speaks as the
# participant and reports their inner shift. Rich, nuanced.
# For WITNESSES (here): a tiny rule-based emotion bump that decays
# naturally via rules/decay.py. Cheap, runs on every event, no LLM.
#
# Why this is small now (was ~50 lines of per-event tables):
#   - PARTICIPANTS get rich psychological treatment via agents/self_update.py
#     (LLM speaks AS them and reports inner shifts). No need for hardcoded
#     "fear+25" deltas anymore for participants.
#   - WITNESSES (third parties present in the tile) still need a quick
#     emotional reaction. Rule path here, since LLM cost would be
#     prohibitive (witnesses can be 5-10 per event).
#   - Writes go to agent.emotions (decays naturally via rules/decay.py),
#     NOT to attributes (those are participant-facing identity stats).
#   - Relationship deltas removed: they were "all witnesses hate the
#     attacker" — too coarse. Real relationship change is content-driven
#     via agents/dialogue.conversation_turn.
#
# Categories instead of per-event tables: drama / horror / shame / wonder.
# Each event_kind maps to a category; categories define emotion deltas.

_HUMAN_TAGS = {"d-class", "staff", "researcher", "field-agent", "elite",
                "psychologist", "antiquarian", "o5",
                "investigator", "academic", "scholar", "local",
                "reporter", "law-enforcement",
                "mortal", "official", "merchant"}

# (witness_emotion_deltas, narrative_template_for_chronicle)
_WITNESS_REACTIONS: dict[str, dict[str, float]] = {
    "horror": {"fear": 25, "joy": -10},
    "dread":  {"fear": 15},
    "wonder": {"joy": 10},
    "joy":    {"joy": 15, "fear": -5},
    "anger":  {"anger": 20, "joy": -5},
}

# event_kind → category. Anything not listed → no witness ripple.
_EVENT_CATEGORY: dict[str, str] = {
    # SCP lethal/dangerous
    "173-snap-neck":         "horror",
    "682-breach":            "horror",
    "049-treatment":         "horror",
    "106-pocket-dimension":  "horror",
    "096-rampage":           "horror",
    # SCP positive
    "999-uplift":            "joy",
    # Cthulhu mind-shake
    "descent":               "dread",
    "cult-ritual":           "dread",
    "possession":            "horror",
    # Liaozhai
    "yaksha-takes-soul":     "horror",
    "renlao-tryst":          "wonder",
}


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

    def apply(self, event: LegendEvent) -> list[LegendEvent]:
        """Process one event's consequences. Returns generated reaction events.

        Now lean: witnesses get a small EMOTION ripple (decays naturally),
        not a per-event attribute table. Per-event narrative reactions are
        emitted as compact 'witness-*' LegendEvents only for high-impact
        categories so the Chronicle still shows that someone was watching.
        """
        tick = event.tick
        reactions: list[LegendEvent] = []

        # ── Witness emotion ripple (rule, no LLM) ──
        category = _EVENT_CATEGORY.get(event.event_kind)
        if category is not None:
            deltas = _WITNESS_REACTIONS[category]
            tile = self.world.get_tile(event.tile_id)
            if tile is not None:
                participant_ids = set(event.participants)
                witnesses = [
                    a for a in self.world.agents_in_tile(tile.tile_id)
                    if a.is_alive() and a.agent_id not in participant_ids
                    and (a.tags & _HUMAN_TAGS)
                ][:4]
                for w in witnesses:
                    for emotion, delta in deltas.items():
                        w.adjust_emotion(emotion, delta)
                # One compact synthetic event captures "someone was watching",
                # so the Chronicle records collateral exposure. Only fired for
                # high-impact categories to keep the log readable.
                if witnesses and category in ("horror", "anger", "wonder"):
                    names = ", ".join(w.display_name for w in witnesses[:3])
                    reactions.append(LegendEvent(
                        event_id=str(uuid.uuid4()), tick=tick,
                        pack_id=witnesses[0].pack_id, tile_id=event.tile_id,
                        event_kind=f"witness-{event.event_kind}",
                        participants=[w.agent_id for w in witnesses],
                        outcome="neutral",
                        template_rendering=f"[{event.tile_id}] {names} were present and saw it.",
                        importance=0.2,
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
