"""SubjectivePerception — agents see events through their own eyes.

What's the difference from just storing the event?

  Objective record (what happens in the world log):
    "[lab-floor-3] SCP-173 was left unobserved for two seconds.
     D-9045 was found moments later, cervical vertebrae fractured."

  Subjective record (what D-9012 actually remembers):
    "I saw 9045 die because I blinked. Could have been me."

  Subjective record (what Dr. Glass actually remembers):
    "Containment slip on my watch. Three seconds of looking down at
     the clipboard and I lost a subject. The report won't say it was
     my fault, but it was."

Same event → completely different memories per witness. This is what
Smallville called "perception" — the LLM rewrites the event from each
participant's POV before it gets stored in their memory stream.

Cost-aware: only fires for high-importance events (importance ≥ threshold)
and only for participants (not all witnesses). Failure → store the
objective rendering as fallback. Cap LLM calls per event to avoid blow-up.
"""

from __future__ import annotations

from living_world.core.agent import Agent
from living_world.core.event import LegendEvent
from living_world.llm.base import LLMClient


SYSTEM_PROMPT = """You ARE the character below. Rewrite what just happened
from YOUR first-person perspective, as a memory you would later recall.

RULES
1. Output ONE first-person sentence, <= 50 words.
2. Reflect YOUR persona, goals, beliefs, and standing in this scene.
   A bystander remembers it as fear; a perpetrator remembers it as
   guilt or relief; a victim's friend remembers it as loss.
3. Stick to facts that actually occurred — do not invent new events,
   deaths, or relationships.
4. Output the memory ONLY. No "I remember:", no name prefix, no quotes.
"""


def _build_prompt(agent: Agent, event: LegendEvent) -> str:
    """Dynamic part only — SYSTEM_PROMPT goes via client.complete(system=)
    for KV-cache reuse (P1)."""
    parts = ["YOU"]
    parts.append(f"  Name: {agent.display_name}")
    parts.append(f"  Persona: {(agent.persona_card or '').strip()[:200]}")
    if agent.current_goal:
        parts.append(f"  Goal: {agent.current_goal}")
    beliefs = agent.get_beliefs()
    if beliefs:
        parts.append(
            "  Beliefs: " + " | ".join(
                f"{k}: {v}" for k, v in list(beliefs.items())[:3]
            )
        )
    parts.append("")
    parts.append(f"WHAT OBJECTIVELY HAPPENED (day {event.tick})")
    parts.append(f"  Kind: {event.event_kind} ({event.outcome})")
    parts.append(f"  Others involved: {', '.join(p for p in event.participants if p != agent.agent_id) or '(none)'}")
    parts.append(f"  Objective record: {event.best_rendering()[:280]}")
    parts.append("")
    parts.append("Now write your first-person memory of this moment:")
    return "\n".join(parts)


def _clean(text: str, fallback: str) -> str:
    text = (text or "").strip().strip('"').strip("'")
    if not text or len(text) < 10 or len(text) > 400:
        return fallback
    bad_starts = ("I remember", "Memory:", "From my perspective", "Here is")
    if any(text.startswith(b) for b in bad_starts):
        return fallback
    return text


class SubjectivePerception:
    """Reframes a high-importance event from one agent's perspective."""

    def __init__(self, client: LLMClient) -> None:
        self.client = client

    def reframe(self, agent: Agent, event: LegendEvent) -> str:
        """Return a first-person rewrite, or the objective rendering on failure."""
        fallback = event.best_rendering()
        try:
            resp = self.client.complete(_build_prompt(agent, event),
                                         max_tokens=120, temperature=0.7,
                                         system=SYSTEM_PROMPT)
        except Exception:
            return fallback
        return _clean(resp.text, fallback)

    async def reframe_async(self, agent: Agent, event: LegendEvent) -> str:
        """Async variant — pair with asyncio.gather() to reframe an event
        from every participant's POV in parallel."""
        fallback = event.best_rendering()
        try:
            resp = await self.client.acomplete(_build_prompt(agent, event),
                                                max_tokens=120, temperature=0.7)
        except Exception:
            return fallback
        return _clean(resp.text, fallback)
