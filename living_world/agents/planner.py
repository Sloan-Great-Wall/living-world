"""AgentPlanner — once-a-week LLM-generated intentions for historical figures.

The planner asks a small LLM to look at an agent's persona, current goal,
recent memories, and recent events, and produce a short structured plan:

    {
        "goals_this_week": [...],   # 1-3 things this character wants to achieve
        "seek":            [...],   # tile types / event kinds / people to find
        "avoid":           [...],   # what they'd rather stay away from
    }

This plan is stored on `agent.state_extra["weekly_plan"]` and consumed by:
  - MovementPolicy (goal-keyword bonus + LLM advisor prompt)
  - TileStoryteller (event weight bonus when plan aligns)

Budget: ~1 LLM call per HF per 7 ticks. Failures fall back to empty dict
so the rest of the system keeps working.
"""

from __future__ import annotations

import json
import re

from living_world.core.agent import Agent
from living_world.core.world import World
from living_world.llm.base import LLMClient


SYSTEM_PROMPT = """You are the planning layer for a character in a world simulation.
You look at one character's situation and write a short plan for the next week.

RULES
1. Output a single JSON object. No prose, no headers, no code fences.
2. Three keys: "goals_this_week" (list of 1-3 short strings),
   "seek" (list of 0-3 short strings — places/things/people to find),
   "avoid" (list of 0-3 short strings — what they would rather stay away from).
3. Each string is under 60 characters, concrete, faithful to the character.
4. Do NOT invent deaths, marriages, or major plot twists.
5. Base the plan on the character's persona + current goal + recent memories.
"""


def _build_prompt(
    agent: Agent,
    world: World,
    memory_snippets: list[str] | None,
) -> str:
    # Dynamic part only — SYSTEM_PROMPT goes via system= for KV-cache (P1)
    parts: list[str] = ["CHARACTER"]
    parts.append(f"Name: {agent.display_name}")
    parts.append(f"Pack: {agent.pack_id}")
    parts.append(f"Persona: {(agent.persona_card or '').strip()[:300]}")
    parts.append(f"Current goal: {agent.current_goal or '(none)'}")
    parts.append(f"Currently at: {agent.current_tile or '(unknown)'}")
    if agent.tags:
        parts.append(f"Tags: {', '.join(sorted(agent.tags))}")

    beliefs = agent.get_beliefs()
    if beliefs:
        bits = [f"{k}: {v}" for k, v in list(beliefs.items())[:4]]
        parts.append(f"Beliefs: {' | '.join(bits)}")

    if memory_snippets:
        parts.append("")
        parts.append("RECENT MEMORIES")
        for m in memory_snippets[:5]:
            s = m.strip().replace("\n", " ")[:150]
            if s:
                parts.append(f"  - {s}")

    # Recent events this agent participated in
    recent = [
        e for e in world.events_since(max(1, world.current_tick - 7))
        if agent.agent_id in e.participants
    ][-4:]
    if recent:
        parts.append("")
        parts.append("RECENT EVENTS")
        for e in recent:
            parts.append(f"  - day {e.tick:03d}: {e.best_rendering()[:100]}")

    parts.append("")
    parts.append("Now output the plan JSON:")
    return "\n".join(parts)


def _parse_plan(text: str) -> dict:
    """Extract and validate the JSON plan. Returns {} on any failure."""
    if not text:
        return {}
    t = text.strip()
    # Strip accidental code fences
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
        return {}
    if not isinstance(data, dict):
        return {}
    out: dict = {}
    for key in ("goals_this_week", "seek", "avoid"):
        val = data.get(key)
        if isinstance(val, list):
            cleaned = [str(x)[:80] for x in val if isinstance(x, (str, int, float)) and str(x).strip()]
            if cleaned:
                out[key] = cleaned[:3]
    return out


class AgentPlanner:
    """Turns an agent's situation into a structured weekly plan via LLM."""

    def __init__(self, client: LLMClient) -> None:
        self.client = client
        # Diagnostic counters — track *why* plans don't appear.
        self.stats = {"calls": 0, "llm_error": 0, "parse_empty": 0,
                       "ok": 0, "last_raw_sample": ""}

    def plan_for_agent(
        self,
        agent: Agent,
        world: World,
        memory_store=None,
    ) -> dict:
        """Generate a plan dict. Returns {} on any failure (never raises)."""
        self.stats["calls"] += 1
        memory_snippets: list[str] | None = None
        if memory_store is not None:
            try:
                query = agent.current_goal or agent.persona_card[:60] or agent.display_name
                entries = memory_store.recall(
                    agent.agent_id, query, top_k=5,
                    current_tick=world.current_tick,
                ) or []
                memory_snippets = [getattr(e, "doc", "") for e in entries if getattr(e, "doc", None)]
            except Exception:
                memory_snippets = None

        prompt = _build_prompt(agent, world, memory_snippets)
        try:
            resp = self.client.complete(prompt, max_tokens=220, temperature=0.6,
                                         json_mode=True, system=SYSTEM_PROMPT)
        except Exception:
            self.stats["llm_error"] += 1
            return {}
        plan = _parse_plan(resp.text or "")
        if not plan:
            self.stats["parse_empty"] += 1
            # Keep one sample of what the LLM actually said so we can debug
            self.stats["last_raw_sample"] = (resp.text or "")[:300]
        else:
            self.stats["ok"] += 1
        return plan
