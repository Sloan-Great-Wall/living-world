"""Chronicler — the 说书人. Reads what emerged, tells us what mattered.

Deliberate non-goal: this module MUST NOT plan future events, steer the
storyteller, nor influence any agent's state. It only observes.

Every N ticks, it takes the last window of recorded events, ranks them by
importance + historical-figure involvement, and asks the LLM to write a
short chapter that names the highlights. Chapters are appended to
world._chapters and surfaced in the dashboard.

The output is strictly descriptive. It's the difference between a
screenwriter (who decides Act 2 climax) and a chronicler (who notes what
happened and what it meant).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from living_world.core.event import LegendEvent
from living_world.core.world import World
from living_world.llm.base import LLMClient


SYSTEM_PROMPT = """You are a chronicler of a world simulation.
Your job is to RECORD what has emerged, not invent what will come.

RULES
1. Read the events below. Pick the 2-4 that matter most (importance, stakes,
   agency of named characters).
2. Write a single prose chapter, 120-200 words, English, literary register.
3. Name the characters. Summarise what shifted — power, trust, fear, loss.
4. Do NOT predict the future. Do NOT moralise. Do NOT invent events.
5. Output a JSON object with exactly:
     "title":   a 3-7 word chapter title
     "body":    the prose chapter
   Output the JSON ONLY. No prose outside the JSON, no code fences.
"""


@dataclass
class Chapter:
    tick: int
    pack_id: str
    title: str
    body: str
    event_ids: list[str] = field(default_factory=list)


def _rank_events(events: list[LegendEvent], limit: int = 8) -> list[LegendEvent]:
    """Rank by importance desc; break ties by tier_used and participant count."""
    def score(e: LegendEvent) -> tuple:
        return (e.importance, e.tier_used, len(e.participants))
    return sorted(events, key=score, reverse=True)[:limit]


def _build_prompt(pack_id: str, events: list[LegendEvent]) -> str:
    # Dynamic part only — SYSTEM_PROMPT goes via system= for KV-cache (P1)
    parts: list[str] = [f"PACK: {pack_id}"]
    parts.append(f"EVENTS ({len(events)})")
    for e in events:
        parts.append(
            f"  - day {e.tick:03d} | imp {e.importance:.2f} | "
            f"{e.event_kind} ({e.outcome}) | "
            f"people: {', '.join(e.participants[:4])}"
        )
        parts.append(f"    {e.best_rendering().strip()[:260]}")
    parts.append("")
    parts.append("Output the JSON chapter now:")
    return "\n".join(parts)


def _parse(text: str) -> tuple[str, str] | None:
    """Extract (title, body). Returns None on any parse failure."""
    import json
    import re
    t = (text or "").strip()
    if "```" in t:
        m = re.search(r"\{[\s\S]*\}", t)
        if m:
            t = m.group(0)
    try:
        data = json.loads(t)
    except Exception:
        # Fallback: look for first {...}
        m = re.search(r"\{[\s\S]*?\}", text or "")
        if not m:
            return None
        try:
            data = json.loads(m.group(0))
        except Exception:
            return None
    if not isinstance(data, dict):
        return None
    title = data.get("title")
    body = data.get("body")
    if not isinstance(title, str) or not isinstance(body, str):
        return None
    title = title.strip()[:80]
    body = body.strip()
    if len(body) < 60 or len(body) > 2000:
        return None
    if not title:
        return None
    return title, body


class Chronicler:
    """Observes emergent events and writes periodic chapters. Non-interventionist."""

    def __init__(self, client: LLMClient) -> None:
        self.client = client
        # Diagnostic counters
        self.stats = {"calls": 0, "window_too_small": 0, "llm_error": 0,
                       "parse_fail": 0, "ok": 0, "last_raw_sample": ""}

    def write_chapter(
        self,
        world: World,
        pack_id: str,
        since_tick: int,
        min_events: int = 4,
        min_importance: float = 0.25,
    ) -> Chapter | None:
        """Return a Chapter or None (if nothing interesting enough happened)."""
        self.stats["calls"] += 1
        window = [
            e for e in world.events_since(since_tick)
            if e.pack_id == pack_id and e.importance >= min_importance
        ]
        if len(window) < min_events:
            self.stats["window_too_small"] += 1
            return None
        ranked = _rank_events(window)
        prompt = _build_prompt(pack_id, ranked)
        try:
            resp = self.client.complete(prompt, max_tokens=420, temperature=0.55,
                                         json_mode=True, system=SYSTEM_PROMPT)
        except Exception:
            self.stats["llm_error"] += 1
            return None
        parsed = _parse(resp.text or "")
        if parsed is None:
            self.stats["parse_fail"] += 1
            self.stats["last_raw_sample"] = (resp.text or "")[:300]
            return None
        title, body = parsed
        self.stats["ok"] += 1
        return Chapter(
            tick=world.current_tick,
            pack_id=pack_id,
            title=title,
            body=body,
            event_ids=[e.event_id for e in ranked],
        )
