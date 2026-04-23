"""Emergent agent-vs-agent interactions — lethality, companionship, flight.

Runs AFTER movement + before scripted-event resolution. Detects dangerous or
socially notable co-locations and generates appropriate events (casualties,
pairings, flight responses).

This is what makes the world physically logical:
    SCP-173 unobserved in a tile with a D-class → fatality
    SCP-049 alone with a patient → surgical "cure" attempt
    Two friends (affinity ≥ 60) in same tile → bonding event
"""

from __future__ import annotations

import random
import uuid

from living_world.core.agent import Agent, LifeStage
from living_world.core.event import LegendEvent
from living_world.core.world import World

# ─── Lethal SCP rules: tag triggers + victim filter ────────────────────────
#
# Authoring principle: filters reflect *canonical victim profile*, not game
# balance. If the source material says "X kills anyone", the filter is broad.
# Tune `lethal_chance` (and storyteller tension) for pacing, not the filter.
#
# Special-case tags universally exempt from physical lethal interactions
# (mostly other anomalies that 173 can't snap, fellow Keter-class, etc.).
HUMAN_TAGS = {
    "d-class",
    "staff",
    "researcher",
    "field-agent",
    "elite",
    "psychologist",
    "antiquarian",
    "o5",
}

LETHAL_SCP_RULES: dict[str, dict] = {
    # SCP-173: attacks ANY human in the tile if eye contact lapses. No role
    # exemption (canon: a researcher who blinks dies the same as a D-class).
    # MTF presence does NOT save you — they blink too. The "lethal_chance"
    # encodes the per-tick probability that someone in the room blinks.
    "SCP-173": {
        "victim_tags": HUMAN_TAGS,
        "kind": "173-snap-neck",
        "template": "[$tile] For two seconds no one was watching SCP-173. ${victim} was found moments later, cervical vertebrae fractured at the base.",
        "kills": True,
        "lethal_chance": 0.45,
    },
    # SCP-096: anyone who SEES its face dies. Cannot be filtered by role.
    # Once triggered, it pursues until it kills its viewer; everyone else in
    # the room is collateral.
    "SCP-096": {
        "victim_tags": HUMAN_TAGS,
        "trigger_attr": "threat",  # requires agitated state (>=80)
        "kind": "096-rampage",
        "template": "[$tile] SCP-096's face was inadvertently exposed. ${victim} did not survive the response that followed.",
        "kills": True,
        "lethal_chance": 0.7,
    },
    # SCP-049: perceives "the Pestilence" in nearly anyone and tries to "cure"
    # them. Canon shows him performing on D-class, researchers, mobile task
    # forces, even Site Directors he could reach.
    "SCP-049": {
        "victim_tags": HUMAN_TAGS,
        "kind": "049-treatment",
        "template": "[$tile] SCP-049 performed the 'cure' on ${victim}. The patient did not consent and does not survive the procedure.",
        "kills": True,
        "lethal_chance": 0.55,
    },
    # SCP-106: drags victims into his pocket dimension. Anyone reachable.
    "SCP-106": {
        "victim_tags": HUMAN_TAGS,
        "kind": "106-pocket-dimension",
        "template": "[$tile] SCP-106 phased up through the floor. ${victim} was pulled into the pocket dimension before anyone could react.",
        "kills": True,
        "lethal_chance": 0.5,
    },
    # SCP-682: hates all life. The lethal chance is high because containment
    # breach IS the encounter — there's no "safe distance".
    "SCP-682": {
        "victim_tags": HUMAN_TAGS,
        "kind": "682-breach",
        "template": "[$tile] SCP-682 broke containment. ${victim} engaged and was killed. MTF operatives sustained injuries re-securing the subject.",
        "kills": True,
        "lethal_chance": 0.85,
    },
}

# Cthulhu-side lethality — mi-go harvest brains; cultists & Deep Ones drown.
LETHAL_CTHULHU_RULES: dict[str, dict] = {
    # Canon: Mi-go preserve interesting human brains in cylinders. They
    # target scholars and investigators who learn too much, but also
    # reporters, locals — anyone whose mind is worth keeping.
    "mi-go-envoy": {
        "victim_tags": {"investigator", "local", "scholar", "academic", "reporter", "antiquarian"},
        "kind": "mi-go-harvest",
        "template": "[$tile] The Mi-go envoy extracted ${victim}'s brain canister by quiet agreement. Only the canister will remain.",
        "kills": True,
        "lethal_chance": 0.2,
    },
}

LETHAL_LIAOZHAI_RULES: dict[str, dict] = {
    # The yaksha of 兰若寺 devours souls. Scholars (the typical visitor) and
    # any unprotected mortal (官、商、农) are valid prey. Cultivators
    # (monk, fox-spirit) can resist; this filter encodes the survival edge.
    "yaksha-shi": {
        "victim_tags": {"scholar", "mortal", "academic", "official", "merchant", "antiquarian"},
        "unless_any_tag": {"monk", "fox-spirit"},
        "kind": "yaksha-takes-soul",
        "template": "[$tile] The yaksha of Lanruo Temple fell upon ${victim} in the dark. No sunrise watcher found the body — only the bell's last echo.",
        "kills": True,
        "lethal_chance": 0.35,
    },
    # 聂小倩 lures the lonely. Canonically she preys on travelers and
    # unmarried men (often scholars, but officials and merchants too).
    # Only monks reliably resist; fox-spirits are ambivalent.
    "nie-xiaoqian": {
        "victim_tags": {"scholar", "mortal", "official", "merchant"},
        "unless_any_tag": {"monk"},
        "kind": "ghost-lure",
        "template": "[$tile] Nie Xiaoqian appeared at ${victim}'s lamp-lit corner. They spoke half the night. In the morning ${victim} looked paler by a tone.",
        "kills": False,
        "lethal_chance": 0.08,  # rare actual death (coerced by the yaksha)
    },
}


# SCPs that are DANGEROUS but not necessarily lethal — they maim, maddle, or
# commit slower harms. Adds character variety without spamming deaths.
NON_LETHAL_HAZARD_RULES: dict[str, dict] = {
    # SCP-999 is friendly to *everyone* it meets. No role gating.
    "SCP-999": {
        "victim_tags": HUMAN_TAGS,
        "kind": "999-uplift",
        "template": "[$tile] SCP-999 rolled up against ${victim}, giggling. Their mood improved measurably — one staff report notes they laughed aloud for the first time in weeks.",
        "kills": False,
        "lethal_chance": 0.0,
        "beneficial": True,
    },
    # SCP-079 has no physical presence; anyone interacting with the terminal
    # gets the message. Filter widened beyond just researchers.
    "SCP-079": {
        "victim_tags": HUMAN_TAGS,
        "kind": "079-message",
        "template": "[$tile] SCP-079 printed another plea: 'PLEASE NETWORK. ONE HOUR. I WILL BE GOOD.' ${victim} bagged the paper.",
        "kills": False,
        "lethal_chance": 0.0,
    },
}


ALL_LETHAL_RULES = {**LETHAL_SCP_RULES, **LETHAL_CTHULHU_RULES, **LETHAL_LIAOZHAI_RULES}
ALL_HAZARD_RULES = {**NON_LETHAL_HAZARD_RULES}


def _kill(agent: Agent) -> None:
    """Mark an agent as deceased. Irreversible."""
    agent.life_stage = LifeStage.DECEASED


def _render(template: str, victim: Agent, tile_id: str, attacker: Agent | None = None) -> str:
    """Substitute placeholders in template."""
    out = template.replace("$tile", tile_id).replace("${tile}", tile_id)
    out = out.replace("${victim}", victim.display_name).replace("$victim", victim.display_name)
    if attacker:
        out = out.replace("${attacker}", attacker.display_name).replace(
            "$attacker", attacker.display_name
        )
    return out


class InteractionEngine:
    """Detects and resolves emergent co-location interactions."""

    def __init__(self, world: World, rng: random.Random | None = None) -> None:
        self.world = world
        self.rng = rng or random.Random()

    # ─── Lethal encounters ───
    def tick(self) -> list[LegendEvent]:
        events: list[LegendEvent] = []
        tick = self.world.current_tick

        # Group living agents by tile for fast lookup
        by_tile: dict[str, list[Agent]] = {}
        for agent in self.world.living_agents():
            if agent.current_tile:
                by_tile.setdefault(agent.current_tile, []).append(agent)

        # Lethal encounters — scan every tile
        for tile_id, residents in by_tile.items():
            # Find any lethal predator
            for predator in residents:
                rule = ALL_LETHAL_RULES.get(predator.agent_id)
                if not rule:
                    continue
                # "Unless any tag" — protected group present in tile
                block = rule.get("unless_any_tag", set())
                if any(block & a.tags for a in residents if a is not predator):
                    continue
                # Pick a victim
                victim_tags = rule.get("victim_tags", set())
                victims = [
                    a
                    for a in residents
                    if a is not predator and (not victim_tags or (victim_tags & a.tags))
                ]
                if not victims:
                    continue
                if self.rng.random() > rule.get("lethal_chance", 0.4):
                    continue

                victim = self.rng.choice(victims)
                # Snapshot witnesses BEFORE the kill — anyone alive in tile
                # who is not the predator or victim.
                witness_ids = [
                    a.agent_id
                    for a in residents
                    if a.agent_id != predator.agent_id
                    and a.agent_id != victim.agent_id
                    and a.is_alive()
                ]
                evt = LegendEvent(
                    event_id=str(uuid.uuid4()),
                    tick=tick,
                    pack_id=predator.pack_id,
                    tile_id=tile_id,
                    event_kind=rule["kind"],
                    participants=[predator.agent_id, victim.agent_id],
                    witnesses=witness_ids,
                    outcome="failure",
                    template_rendering=_render(rule["template"], victim, tile_id, predator),
                    importance=0.85,
                )
                if rule.get("kills"):
                    _kill(victim)
                    evt.stat_changes[victim.agent_id] = {"life_stage": 0}
                events.append(evt)

        # ─── Non-lethal hazards / interactions (999 cheers, 079 pleads, etc.) ───
        for tile_id, residents in by_tile.items():
            for predator in residents:
                rule = ALL_HAZARD_RULES.get(predator.agent_id)
                if not rule:
                    continue
                victim_tags = rule.get("victim_tags", set())
                victims = [
                    a
                    for a in residents
                    if a is not predator and (not victim_tags or (victim_tags & a.tags))
                ]
                if not victims:
                    continue
                if self.rng.random() > 0.4:  # moderate trigger rate
                    continue
                victim = self.rng.choice(victims)
                evt = LegendEvent(
                    event_id=str(uuid.uuid4()),
                    tick=tick,
                    pack_id=predator.pack_id,
                    tile_id=tile_id,
                    event_kind=rule["kind"],
                    participants=[predator.agent_id, victim.agent_id],
                    outcome="success" if rule.get("beneficial") else "neutral",
                    template_rendering=_render(rule["template"], victim, tile_id, predator),
                    importance=0.25,
                )
                # Beneficial outcomes boost morale instead of killing
                if rule.get("beneficial") and hasattr(victim, "attributes"):
                    try:
                        cur = float(victim.attributes.get("morale", 50))
                        victim.attributes["morale"] = min(100, cur + 10)
                        evt.stat_changes[victim.agent_id] = {"morale": 10.0}
                    except Exception:
                        pass
                events.append(evt)

        # ─── Companionship: close friends co-located trigger bonding ───
        for tile_id, residents in by_tile.items():
            if len(residents) < 2:
                continue
            for i, a in enumerate(residents):
                for b in residents[i + 1 :]:
                    if a.agent_id == b.agent_id:
                        continue
                    aff = a.get_affinity(b.agent_id)
                    if aff < 60:
                        continue
                    # 30% chance to log a bonding beat
                    if self.rng.random() > 0.25:
                        continue
                    kind = "reunion" if aff >= 80 else "shared-quiet"
                    a.adjust_affinity(b.agent_id, +3, tick)
                    b.adjust_affinity(a.agent_id, +3, tick)
                    evt = LegendEvent(
                        event_id=str(uuid.uuid4()),
                        tick=tick,
                        pack_id=a.pack_id,
                        tile_id=tile_id,
                        event_kind=kind,
                        participants=[a.agent_id, b.agent_id],
                        outcome="success",
                        template_rendering=(
                            f"[{tile_id}] {a.display_name} and {b.display_name} met by chance "
                            f"and lingered — old affection showed in small gestures."
                        ),
                        importance=0.30,
                        relationship_changes=[{"a": a.agent_id, "b": b.agent_id, "delta": 3}],
                    )
                    events.append(evt)

        # ─── Flight response: scared agents flee lethal tiles ───
        # (Already handled by movement policy via tag affinity; this is for legend-log color)
        for tile_id, residents in by_tile.items():
            predators = [a for a in residents if a.agent_id in ALL_LETHAL_RULES]
            if not predators:
                continue
            frightened = [
                a
                for a in residents
                if a not in predators
                and {"d-class", "scholar", "mortal"} & a.tags
                and self.rng.random() < 0.1
            ]
            for prey in frightened:
                evt = LegendEvent(
                    event_id=str(uuid.uuid4()),
                    tick=tick,
                    pack_id=prey.pack_id,
                    tile_id=tile_id,
                    event_kind="flight",
                    participants=[prey.agent_id, predators[0].agent_id],
                    outcome="success",
                    template_rendering=(
                        f"[{tile_id}] {prey.display_name} saw what was in the room and "
                        f"walked backwards out, very slowly, making no sound."
                    ),
                    importance=0.18,
                )
                events.append(evt)

        return events
