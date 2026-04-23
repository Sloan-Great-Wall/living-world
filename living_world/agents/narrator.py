"""Narrator — when an event matters, an LLM rewrites its narrative.

Two paths only:
  - importance < threshold  → keep the rule-template rendering (Tier 1, free).
  - importance ≥ threshold  → ask the LLM for a vivid one-sentence rewrite.

Emergent events already carry LLM-written narrative and are passed through
unchanged. Failures (LLM unreachable, prompt-leak in output) fall back
silently to the template — the world keeps running.

This module replaced the older `EnhancementRouter` after the Tier-2 path
was simplified out. The class name kept its old API (`.enhance(event)`)
so factory + tick_loop don't need to change their call sites.
"""

from __future__ import annotations

from dataclasses import dataclass

from living_world.core.event import LegendEvent
from living_world.llm.base import LLMClient


@dataclass
class NarratorBudget:
    """Daily token cap for the LLM-narrative path. Reset by tick_loop."""

    tokens_limit: int = 200_000
    tokens_used: int = 0

    def can_spend(self) -> bool:
        return self.tokens_used < self.tokens_limit

    def record(self, tokens: int) -> None:
        self.tokens_used += tokens

    def reset_daily(self) -> None:
        self.tokens_used = 0


@dataclass
class NarratorStats:
    """Counters for the dashboard. tier3 = LLM-narrative, tier1 = template-only."""

    tier1: int = 0
    tier3: int = 0


_BAD_PREFIXES = (
    "Okay,", "Sure,", "Here is", "Here's", "Let me", "Narrative:",
    "Let's break", "Breaking down", "Analysis:", "Explanation:",
    "[ollama-error",          # OllamaClient graceful-failure marker
)
_BAD_SUBSTRINGS = (
    "Rewrite the following",   # narrator's own prompt template echo
    "Output ONLY the narrative",
    "No analysis, no headers",
    "Original:",
    "World:",
)


def _clean(text: str, fallback: str) -> str:
    """Reject obvious meta-preamble or prompt echoes; otherwise pass through."""
    text = (text or "").strip()
    for p in _BAD_PREFIXES:
        if text.startswith(p):
            return fallback
    for sub in _BAD_SUBSTRINGS:
        if sub in text:
            return fallback
    if len(text) < 15 or len(text) > 800:
        return fallback
    return text


def _build_prompt(event: LegendEvent) -> str:
    return (
        "Rewrite the following event as a single vivid narrative sentence "
        "(30-60 words). Output ONLY the narrative. No analysis, no headers, "
        "no commentary.\n\n"
        f"World: {event.pack_id} | Event: {event.event_kind} | "
        f"Outcome: {event.outcome}\nOriginal: {event.template_rendering}"
    )


class Narrator:
    """LLM rewrites the narrative of high-importance rule-proposed events.

    Importance < TIER3_THRESHOLD → template kept as-is (Tier 1, no cost).
    Importance ≥ threshold       → LLM rewrite (Tier 3).
    Emergent events              → passed through (their text is already LLM-written).
    """

    TIER3_THRESHOLD = 0.65

    def __init__(
        self,
        tier3: LLMClient | None = None,
        budget: NarratorBudget | None = None,
    ) -> None:
        self.tier3 = tier3
        self.budget = budget or NarratorBudget()
        self.stats = NarratorStats()

    def enhance(self, event: LegendEvent) -> LegendEvent:
        """Maybe call the LLM to rewrite. Mutates + returns the event."""
        # Emergent events already carry LLM narrative — pass through.
        if event.is_emergent:
            if event.tier_used == 3:
                self.stats.tier3 += 1
            else:
                self.stats.tier1 += 1
            return event

        if (
            self.tier3 is not None
            and event.importance >= self.TIER3_THRESHOLD
            and self.budget.can_spend()
        ):
            try:
                resp = self.tier3.complete(_build_prompt(event), max_tokens=320)
                event.spotlight_rendering = _clean(resp.text, event.template_rendering)
                self.budget.record(resp.tokens_out)
                self.stats.tier3 += 1
                event.tier_used = 3
                return event
            except Exception as exc:
                print(f"[narrator] LLM call failed: {exc}")

        self.stats.tier1 += 1
        event.tier_used = 1
        return event
