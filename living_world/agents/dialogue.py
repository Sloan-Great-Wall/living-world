"""DialogueGenerator — A→B conversation turn that mutates state.

This module is the ONE LLM touchpoint where the model's output mutates
game state (affinity + beliefs), not just narrative.

Flow:
    1. The listener's persona, beliefs, current affinity to the speaker,
       and recalled memories are assembled into a prompt.
    2. The LLM, speaking AS the listener, returns JSON:
         {"reply", "affinity_delta", "belief_update"}
    3. The caller applies affinity_delta via Agent.adjust_affinity and
       belief_update via Agent.set_belief.

Triggered by tick_loop when conversation_loop_enabled is True and a Tier-2+
event has exactly two participants. Cheap-fail on any LLM/parse error.
"""

from __future__ import annotations

import json
import re

from living_world.core.agent import Agent
from living_world.core.event import LegendEvent
from living_world.core.world import World
from living_world.llm.base import LLMClient

REACTION_SYSTEM_PROMPT = """You ARE the LISTENER character. The SPEAKER just did
something involving you. React in-character.

Output a SINGLE JSON object (no prose, no code fences, no comments) with keys:
  "reply":          a first-person line <= 30 words, the listener says out loud
                    or thinks. English, literary register.
  "affinity_delta": integer in [-3, +3] — how this moment changed how you
                    feel about the speaker. 0 means indifferent.
  "belief_update":  either null, OR a short string (<=120 chars) stating a
                    new belief about the speaker. Format: "concrete observation".
                    Only set this when something meaningful shifted; otherwise null.

Rules:
 - Stay in-character. Don't break the fourth wall.
 - Don't invent major plot turns (deaths, betrayals not already happening).
 - belief_update must be about the speaker, concrete, under 120 chars.
 - Output ONLY the JSON object. No explanation.
"""


def _build_reaction_prompt(
    speaker: Agent,
    listener: Agent,
    event: LegendEvent,
    world: World,
    *,
    listener_memories: list[str],
    listener_beliefs: dict[str, str],
    current_affinity: int,
) -> str:
    parts: list[str] = [REACTION_SYSTEM_PROMPT, ""]
    parts.append("SPEAKER")
    parts.append(f"  Name: {speaker.display_name}")
    parts.append(f"  Persona: {(speaker.persona_card or '').strip()[:220]}")
    if speaker.current_goal:
        parts.append(f"  Their goal: {speaker.current_goal}")

    parts.append("")
    parts.append("YOU (the LISTENER)")
    parts.append(f"  Name: {listener.display_name}")
    parts.append(f"  Persona: {(listener.persona_card or '').strip()[:220]}")
    if listener.alignment and listener.alignment != "neutral":
        parts.append(f"  Alignment: {listener.alignment}")
    if listener.current_goal:
        parts.append(f"  Your goal: {listener.current_goal}")
    parts.append(
        f"  Your current affinity toward {speaker.display_name}: "
        f"{current_affinity:+d} (scale -100..+100)"
    )
    if listener_beliefs:
        bits = [f"{k}: {v}" for k, v in list(listener_beliefs.items())[:4]]
        parts.append(f"  Your beliefs: {' | '.join(bits)}")
    if listener_memories:
        parts.append("  Memories that come to mind:")
        for m in listener_memories:
            parts.append(f"    - {m}")

    tile = world.get_tile(event.tile_id) if event.tile_id else None
    parts.append("")
    parts.append("WHAT JUST HAPPENED")
    if tile:
        parts.append(f"  Where: {tile.display_name}")
    parts.append(f"  Event: {event.event_kind} (outcome: {event.outcome})")
    if event.template_rendering:
        parts.append(f"  Summary: {event.template_rendering.strip()[:260]}")

    parts.append("")
    parts.append("Your reaction JSON:")
    return "\n".join(parts)


def _parse_reaction(text: str) -> dict | None:
    """Extract and validate the reaction JSON. Returns None on failure."""
    t = text.strip()
    # Strip code fences if present
    if "```" in t:
        m = re.search(r"\{[\s\S]*?\}", t)
        if m:
            t = m.group(0)
    else:
        m = re.search(r"\{[\s\S]*?\}", t)
        if m:
            t = m.group(0)
    try:
        data = json.loads(t)
    except Exception:
        return None
    if not isinstance(data, dict):
        return None

    # affinity_delta: integer clamped to [-3, +3]
    try:
        delta_raw = data.get("affinity_delta", 0)
        delta = int(delta_raw) if delta_raw is not None else 0
    except (TypeError, ValueError):
        delta = 0
    delta = max(-3, min(3, delta))

    # reply: short string
    reply = data.get("reply")
    if not isinstance(reply, str):
        reply = ""
    reply = reply.strip()[:200]

    # belief_update: None or short string
    belief = data.get("belief_update")
    if isinstance(belief, str):
        belief = belief.strip()[:200]
        if not belief or belief.lower() in ("null", "none", "n/a"):
            belief = None
    else:
        belief = None

    return {"affinity_delta": delta, "belief_update": belief, "reply": reply}


class DialogueGenerator:
    """Speaker→Listener LLM reaction loop. Mutates state via the returned dict."""

    def __init__(self, client: LLMClient) -> None:
        self.client = client

    def conversation_turn(
        self,
        speaker: Agent,
        listener: Agent,
        event: LegendEvent,
        world: World,
        memory_store=None,
    ) -> dict:
        """Return a reaction dict (always safe — never raises).

        Result shape:
            {"affinity_delta": int (-3..+3),
             "belief_update": str | None,
             "reply":         str}
        """
        neutral: dict = {"affinity_delta": 0, "belief_update": None, "reply": ""}

        listener_memories: list[str] = []
        if memory_store is not None:
            try:
                query = f"{speaker.display_name} {event.event_kind}"
                entries = (
                    memory_store.recall(
                        listener.agent_id,
                        query,
                        top_k=3,
                        current_tick=world.current_tick,
                    )
                    or []
                )
                listener_memories = [
                    getattr(e, "doc", "")[:140].replace("\n", " ")
                    for e in entries
                    if getattr(e, "doc", None)
                ]
            except Exception:
                listener_memories = []

        prompt = _build_reaction_prompt(
            speaker,
            listener,
            event,
            world,
            listener_memories=listener_memories,
            listener_beliefs=listener.get_beliefs(),
            current_affinity=listener.get_affinity(speaker.agent_id),
        )

        try:
            resp = self.client.complete(prompt, max_tokens=260, temperature=0.75, json_mode=True)
        except Exception:
            return neutral
        raw = (resp.text or "").strip()
        if not raw:
            return neutral

        parsed = _parse_reaction(raw)
        return parsed if parsed is not None else neutral
