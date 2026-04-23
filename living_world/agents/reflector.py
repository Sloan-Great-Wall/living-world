"""MemoryReflector — LLM-driven Park 2023 reflection.

Reads an agent's recent raw memories and emits 1-3 *higher-level beliefs*
that get stored back as reflection-kind memory entries plus on
`agent.beliefs` for direct planner/self_update consumption.

This is the "synthesis layer" that turns episodic recall into
abstractions: many "I survived an SCP-173 sweep" memories collapse into
"I am unusually lucky", which then biases future risk-taking.

See KNOWN_ISSUES.md issue #14.
"""

from __future__ import annotations

import json
import re

from living_world.core.agent import Agent
from living_world.llm.base import LLMClient

SYSTEM_PROMPT = """You are the reflective inner voice of a character.
Read the recent memories below. Distill 1-3 higher-level *beliefs* this
character would now hold about themselves, others, or the world.

A belief is NOT a memory of an event; it's an abstraction *across*
events. "Dr. Bright laughed at me" is a memory. "I am tolerated, not
respected" is a belief.

Output a single JSON object — no prose, no fences:
{
  "beliefs": [
    {"topic": "<short noun, ≤32 chars>", "belief": "<1 sentence ≤180 chars>"}
  ]
}

Rules:
 - Stay in-character. First-person voice in the belief sentence.
 - Each topic must be a short, queryable string (e.g. "scp-173",
   "dr-glass", "myself", "the foundation").
 - Don't repeat existing beliefs verbatim — extend or revise them.
 - 1-3 beliefs total. If memories are too thin to abstract from,
   return {"beliefs": []}.
"""


def _build_prompt(agent: Agent, recent_memories: list[str]) -> str:
    # Dynamic part only — SYSTEM_PROMPT goes via system= for KV-cache (P1)
    parts = ["CHARACTER"]
    parts.append(f"  Name: {agent.display_name}")
    parts.append(f"  Persona: {(agent.persona_card or '').strip()[:200]}")
    if agent.current_goal:
        parts.append(f"  Current goal: {agent.current_goal}")
    existing = agent.get_beliefs() if hasattr(agent, "get_beliefs") else {}
    if existing:
        bits = " | ".join(f"{k}: {v}" for k, v in list(existing.items())[:5])
        parts.append(f"  Existing beliefs: {bits}")
    parts.append("")
    parts.append("RECENT MEMORIES")
    for m in recent_memories[:12]:
        s = m.strip().replace("\n", " ")[:200]
        if s:
            parts.append(f"  - {s}")
    parts.append("")
    parts.append("Your reflection JSON:")
    return "\n".join(parts)


def _parse(text: str) -> list[dict]:
    """Return a list of {topic, belief} dicts. [] on any failure."""
    t = (text or "").strip()
    if not t:
        return []
    # First try direct, then greedy-brace fallback
    try:
        data = json.loads(t)
    except Exception:
        m = re.search(r"\{[\s\S]*\}", t)
        if not m:
            return []
        try:
            data = json.loads(m.group(0))
        except Exception:
            return []
    if not isinstance(data, dict):
        return []
    raw = data.get("beliefs")
    if not isinstance(raw, list):
        return []
    out = []
    for entry in raw[:3]:
        if not isinstance(entry, dict):
            continue
        topic = entry.get("topic")
        belief = entry.get("belief")
        if not isinstance(topic, str) or not isinstance(belief, str):
            continue
        topic = topic.strip()[:32]
        belief = belief.strip()[:200]
        if topic and belief:
            out.append({"topic": topic, "belief": belief})
    return out


class MemoryReflector:
    """LLM module that turns raw memories into beliefs."""

    def __init__(self, client: LLMClient) -> None:
        self.client = client
        self.stats = {"calls": 0, "llm_error": 0, "empty": 0, "ok": 0, "beliefs_emitted": 0}

    def reflect(
        self,
        agent: Agent,
        recent_memories: list[str],
    ) -> list[dict]:
        """Return parsed [{topic, belief}, ...] — empty list on failure.

        Side effect: also writes beliefs onto the agent via
        `agent.set_belief(topic, belief)` so they're immediately available
        to planner/self_update prompts even before the next memory recall.
        """
        if len(recent_memories) < 3:
            return []
        self.stats["calls"] += 1
        try:
            resp = self.client.complete(
                _build_prompt(agent, recent_memories),
                max_tokens=240,
                temperature=0.55,
                json_mode=True,
                system=SYSTEM_PROMPT,
            )
        except Exception:
            self.stats["llm_error"] += 1
            return []
        beliefs = _parse(resp.text or "")
        if not beliefs:
            self.stats["empty"] += 1
            return []
        self.stats["ok"] += 1
        self.stats["beliefs_emitted"] += len(beliefs)
        # Write straight onto the agent for instant downstream use.
        if hasattr(agent, "set_belief"):
            for b in beliefs:
                agent.set_belief(b["topic"], b["belief"])
        return beliefs
