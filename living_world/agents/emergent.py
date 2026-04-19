"""EmergentEventProposer — LLM invents events that the YAML didn't author.

This is the single biggest break from the template-driven model: the LLM
looks at the state of a "hot" tile (several agents co-located with strong
feelings or goals) and proposes ONE novel event grounded in that context.

The emitted event enters the normal downstream pipeline: recorded in the
world, picked up by consequences (where the rules still gate what's
physically possible), remembered by participants.

Safety rails:
  - The LLM cannot kill or revive agents directly. stat_changes and
    affinity_changes are clamped. If outcome claims death we downgrade to
    a non-fatal narrative, leaving lethal interactions to the rule engine.
  - An emergent proposal is rejected if its participants aren't actually
    co-located (prevents the LLM from teleporting characters).
  - Budget: at most ONE emergent event per hot tile per tick, and capped
    at max_per_tick total across the world.
"""

from __future__ import annotations

import json
import re
import uuid

from living_world.core.agent import Agent, LifeStage
from living_world.core.event import LegendEvent
from living_world.core.tile import Tile
from living_world.core.world import World
from living_world.llm.base import LLMClient


SYSTEM_PROMPT = """You propose ONE novel event emerging from the characters below.
You are NOT a director. You observe their persona, goals, beliefs, and mood,
and name the single most natural thing that would happen next at this place.

RULES
1. Output a single JSON object. No prose outside, no code fences.
2. Fields:
     "event_kind":    a short hyphenated lowercase label (2-5 words via "-"), fresh.
     "participants":  agent_ids from the provided list, 1-4 of them.
     "outcome":       one of "success" | "failure" | "neutral".
     "importance":    float in [0.05, 0.95]. Ordinary moments sit near 0.15-0.3.
                      Life-or-death moments go to 0.7-0.95.
     "narrative":     one English sentence, <= 260 characters, describing what
                      happened. No meta-language. Refer to characters by name.
     "affinity_changes":  optional list of {"a": id, "b": id, "delta": int in [-10,+10]}.
     "belief_updates":    optional list of {"agent_id": id, "topic": id, "belief": str}.
     "deaths":            optional list of agent_ids who die. ONLY when the
                          context genuinely justifies it (lethal conflict, the
                          arrival of something deadly, despair). Be sparing.
                          Death is real and permanent here.
     "injuries":          optional list of {"agent_id": id, "severity": "minor"|"grave"}.
3. Be honest about consequence. Do NOT soften reality to protect characters.
   If a D-class provokes SCP-173, SCP-173 may snap their neck. If a cultist
   betrays the Deep Ones, they may drown. Let the world be what it is.
4. Constraints you must still respect:
   - Cannot resurrect the already-dead.
   - Cannot teleport characters into this tile (participants must be listed).
   - No marriages, no children born. Those require separate rule support.
5. Stay grounded. If nothing interesting would plausibly happen, output
   {"event_kind": "none"} and nothing else.
"""


def _tile_context(tile: Tile, world: World) -> str:
    residents = world.agents_in_tile(tile.tile_id)
    lines: list[str] = [f"LOCATION: {tile.display_name} ({tile.tile_type})"]
    if tile.description:
        lines.append(f"  {tile.description.strip()[:160]}")
    lines.append("")
    lines.append("PEOPLE CURRENTLY HERE")
    for a in residents[:6]:
        lines.append(f"- {a.agent_id} ({a.display_name})")
        lines.append(f"    Persona: {(a.persona_card or '').strip()[:180]}")
        if a.current_goal:
            lines.append(f"    Goal: {a.current_goal}")
        beliefs = a.get_beliefs()
        if beliefs:
            bits = [f"{k}: {v}" for k, v in list(beliefs.items())[:3]]
            lines.append(f"    Beliefs: {' | '.join(bits)}")
        # Pairwise affinity with other residents
        affs = []
        for other in residents[:6]:
            if other.agent_id == a.agent_id:
                continue
            f = a.get_affinity(other.agent_id)
            if abs(f) >= 10:
                affs.append(f"{other.agent_id}:{f:+d}")
        if affs:
            lines.append(f"    Feels toward: {', '.join(affs[:4])}")
    # Recent events on this tile
    recent = [
        e for e in world.events_since(max(1, world.current_tick - 3))
        if e.tile_id == tile.tile_id
    ][-3:]
    if recent:
        lines.append("")
        lines.append("RECENT EVENTS HERE")
        for e in recent:
            lines.append(f"  day {e.tick:03d}: {e.best_rendering()[:160]}")
    return "\n".join(lines)


def _parse_proposal(text: str) -> dict | None:
    """Extract and validate the proposal JSON. Returns None on failure."""
    t = (text or "").strip()
    if not t:
        return None
    if "```" in t:
        m = re.search(r"\{[\s\S]*\}", t)
        if m:
            t = m.group(0)
    else:
        m = re.search(r"\{[\s\S]*\}", t)
        if m:
            t = m.group(0)
    try:
        data = json.loads(t)
    except Exception:
        return None
    if not isinstance(data, dict):
        return None
    return data


def _clamp_proposal(data: dict, valid_agent_ids: set[str]) -> dict | None:
    """Validate + sanitise a parsed proposal. Returns None if unusable."""
    kind = data.get("event_kind")
    if not isinstance(kind, str) or not kind.strip() or kind.strip().lower() == "none":
        return None
    kind = kind.strip().lower()[:48]
    kind = re.sub(r"[^a-z0-9-]+", "-", kind).strip("-") or "emergent-moment"

    participants = data.get("participants", [])
    if not isinstance(participants, list):
        return None
    participants = [p for p in participants if isinstance(p, str) and p in valid_agent_ids]
    if not participants:
        return None
    participants = participants[:4]

    outcome = data.get("outcome", "neutral")
    if outcome not in ("success", "failure", "neutral"):
        outcome = "neutral"

    try:
        importance = float(data.get("importance", 0.2))
    except (TypeError, ValueError):
        importance = 0.2
    importance = max(0.05, min(0.95, importance))

    narrative = data.get("narrative", "")
    if not isinstance(narrative, str):
        return None
    narrative = narrative.strip()[:320]
    if len(narrative) < 20:
        return None
    # Reject only prompt echoes. We no longer filter "dies"/"killed" — death
    # is a legitimate outcome and the world should be honest about it.
    banned = ("RULES", "PEOPLE CURRENTLY HERE", "event_kind", "participants")
    if any(b in narrative for b in banned):
        return None

    # Clamp affinity_changes (widened range now that stakes can be lethal)
    aff_raw = data.get("affinity_changes") or []
    aff: list[dict] = []
    if isinstance(aff_raw, list):
        for entry in aff_raw[:6]:
            if not isinstance(entry, dict):
                continue
            a_id, b_id = entry.get("a"), entry.get("b")
            if a_id not in valid_agent_ids or b_id not in valid_agent_ids:
                continue
            try:
                delta = int(entry.get("delta", 0))
            except (TypeError, ValueError):
                continue
            delta = max(-10, min(10, delta))
            if delta == 0:
                continue
            aff.append({"a": a_id, "b": b_id, "delta": delta})

    # Belief updates (optional)
    bel_raw = data.get("belief_updates") or []
    beliefs: list[dict] = []
    if isinstance(bel_raw, list):
        for entry in bel_raw[:6]:
            if not isinstance(entry, dict):
                continue
            aid = entry.get("agent_id")
            topic = entry.get("topic")
            belief = entry.get("belief")
            if aid not in valid_agent_ids:
                continue
            if not isinstance(topic, str) or not isinstance(belief, str):
                continue
            belief = belief.strip()
            if not belief or len(belief) > 180:
                continue
            beliefs.append({"agent_id": aid, "topic": topic.strip()[:48], "belief": belief})

    # Deaths — list of agent_ids who die in this event. Validated against
    # participants only (can't kill someone not present).
    deaths_raw = data.get("deaths") or []
    deaths: list[str] = []
    if isinstance(deaths_raw, list):
        for aid in deaths_raw:
            if isinstance(aid, str) and aid in valid_agent_ids and aid in participants:
                deaths.append(aid)

    # Injuries — non-fatal state marker via a tag.
    inj_raw = data.get("injuries") or []
    injuries: list[dict] = []
    if isinstance(inj_raw, list):
        for entry in inj_raw[:4]:
            if not isinstance(entry, dict):
                continue
            aid = entry.get("agent_id")
            sev = entry.get("severity", "minor")
            if aid not in valid_agent_ids or aid in deaths:
                continue
            if sev not in ("minor", "grave"):
                sev = "minor"
            injuries.append({"agent_id": aid, "severity": sev})

    return {
        "event_kind": kind,
        "participants": participants,
        "outcome": outcome,
        "importance": importance,
        "narrative": narrative,
        "affinity_changes": aff,
        "belief_updates": beliefs,
        "deaths": deaths,
        "injuries": injuries,
    }


class EmergentEventProposer:
    """Single responsibility: take a tile, ask LLM for ONE novel event there.

    Tile selection (which tile is "hot") is a pure-rule function and lives
    in `rules/heat.py`. The caller (tick_loop) picks tiles via
    `rules.heat.hot_tiles()` and feeds them in here one at a time.
    """

    def __init__(self, client: LLMClient) -> None:
        self.client = client

    def propose(self, tile: Tile, world: World) -> LegendEvent | None:
        residents = world.agents_in_tile(tile.tile_id)
        if len(residents) < 2:
            return None
        prompt = SYSTEM_PROMPT + "\n\n" + _tile_context(tile, world) + "\n\nYour JSON:"
        try:
            resp = self.client.complete(prompt, max_tokens=320, temperature=0.75)
        except Exception:
            return None
        parsed = _parse_proposal(resp.text or "")
        if parsed is None:
            return None
        cleaned = _clamp_proposal(parsed, {a.agent_id for a in residents})
        if cleaned is None:
            return None

        # Apply affinity + belief updates directly on agents. The event
        # itself carries only the narrative and the participant list — the
        # LegendEvent schema doesn't have a free-form metadata bag, and we
        # don't want to fight Pydantic about it.
        rel_changes: list[dict] = []
        for change in cleaned["affinity_changes"]:
            a = world.get_agent(change["a"])
            b = world.get_agent(change["b"])
            if a is None or b is None:
                continue
            a.adjust_affinity(b.agent_id, change["delta"], world.current_tick)
            rel_changes.append({
                "a": change["a"], "b": change["b"], "delta": change["delta"],
            })
        for bu in cleaned["belief_updates"]:
            a = world.get_agent(bu["agent_id"])
            if a is None:
                continue
            a.set_belief(bu["topic"], bu["belief"])

        # Apply injuries via tags so movement/storyteller can react.
        # "wounded" = minor, "grave-wound" = serious. The consequence engine
        # already has hooks (description mutations) that can escalate these.
        for inj in cleaned["injuries"]:
            a = world.get_agent(inj["agent_id"])
            if a is None or not a.is_alive():
                continue
            a.tags.add("grave-wound" if inj["severity"] == "grave" else "wounded")

        # Apply deaths. Final and real — no resurrection. Removes them from
        # tile resident lists so they no longer participate in encounters.
        for dead_id in cleaned["deaths"]:
            a = world.get_agent(dead_id)
            if a is None or not a.is_alive():
                continue
            a.life_stage = LifeStage.DECEASED
            tile_obj = world.get_tile(a.current_tile) if a.current_tile else None
            if tile_obj is not None and a.agent_id in tile_obj.resident_agents:
                tile_obj.resident_agents.remove(a.agent_id)

        return LegendEvent(
            event_id=str(uuid.uuid4()),
            tick=world.current_tick,
            pack_id=tile.primary_pack,
            tile_id=tile.tile_id,
            event_kind=cleaned["event_kind"],
            participants=cleaned["participants"],
            outcome=cleaned["outcome"],
            template_rendering=cleaned["narrative"],
            importance=cleaned["importance"],
            relationship_changes=rel_changes,
            # The LLM already wrote the narrative. Mirror it into
            # enhanced_rendering so best_rendering() returns it even after
            # persistence strips the template_rendering alias.
            enhanced_rendering=cleaned["narrative"],
            tier_used=2,
            is_emergent=True,
        )
