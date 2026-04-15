"""Tier routing — decide whether an event needs Tier 2/3 enhancement.

Budget-aware: if daily Tier 3 tokens exceeded, auto-downgrade to Tier 2.
See stat-machine-design.md §'升级判定' and §'监控与降级'.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from living_world.core.event import LegendEvent
from living_world.llm.base import LLMClient


@dataclass
class TierBudget:
    """Daily budget counters. Tokens are stand-in for yuan spent."""

    tier2_tokens_limit: int = 1_000_000
    tier3_tokens_limit: int = 200_000
    tier2_used: int = 0
    tier3_used: int = 0

    def can_use_tier3(self) -> bool:
        return self.tier3_used < self.tier3_tokens_limit

    def can_use_tier2(self) -> bool:
        return self.tier2_used < self.tier2_tokens_limit

    def record(self, tier: int, tokens: int) -> None:
        if tier == 2:
            self.tier2_used += tokens
        elif tier == 3:
            self.tier3_used += tokens

    def reset_daily(self) -> None:
        self.tier2_used = 0
        self.tier3_used = 0


@dataclass
class RouterStats:
    tier1: int = 0
    tier2: int = 0
    tier3: int = 0
    downgraded: int = 0


class EnhancementRouter:
    """Wraps Tier 2/3 clients with budget + fallback logic."""

    TIER2_THRESHOLD = 0.35
    TIER3_THRESHOLD = 0.65

    def __init__(
        self,
        tier2: LLMClient | None = None,
        tier3: LLMClient | None = None,
        budget: TierBudget | None = None,
        *,
        dialogue_generator=None,   # optional DialogueGenerator
        debate_phase=None,         # optional DebatePhase
        debate_threshold: float = 0.75,
        world=None,                # required for dialogue/debate (needs tile + participants)
    ) -> None:
        self.tier2 = tier2
        self.tier3 = tier3
        self.budget = budget or TierBudget()
        self.stats = RouterStats()
        self.dialogue_generator = dialogue_generator
        self.debate_phase = debate_phase
        self.debate_threshold = debate_threshold
        self.world = world

    def _build_prompt(self, event: LegendEvent) -> str:
        # Structured prompt so mock clients can parse out pack/kind/body.
        return (
            f"[PACK={event.pack_id}]"
            f"[KIND={event.event_kind}]"
            f"[OUTCOME={event.outcome}]"
            f"[IMP={event.importance:.2f}]"
            f"[BODY={event.template_rendering}]"
        )

    def enhance(self, event: LegendEvent) -> LegendEvent:
        """Maybe call Tier 2/3 to rewrite event renderings. Mutates + returns event."""
        # Below Tier 2 threshold — keep template only.
        if event.importance < self.TIER2_THRESHOLD or self.tier2 is None:
            self.stats.tier1 += 1
            event.tier_used = 1
            return event

        prompt = self._build_prompt(event)

        # Tier 3 pathway
        if event.importance >= self.TIER3_THRESHOLD and self.tier3 is not None:
            if self.budget.can_use_tier3():
                text: str | None = None

                # 3a. Debate Phase — highest tier, multi-agent round
                if (
                    self.debate_phase is not None
                    and self.world is not None
                    and event.importance >= self.debate_threshold
                ):
                    try:
                        text = self.debate_phase.run(event, self.world)
                    except Exception as exc:
                        print(f"[router] debate failed: {exc}")

                # 3b. Dynamic dialogue via LLM with persona + memory
                if text is None and self.dialogue_generator is not None and self.world is not None:
                    participants = [
                        a for a in (self.world.get_agent(pid) for pid in event.participants)
                        if a is not None
                    ]
                    try:
                        text = self.dialogue_generator.generate(event, participants, self.world)
                    except Exception as exc:
                        print(f"[router] dialogue failed: {exc}")

                # 3c. Plain Tier 3 rewrite — fallback
                if text is None:
                    resp = self.tier3.complete(prompt, max_tokens=512)
                    text = resp.text
                    self.budget.record(3, resp.tokens_out)

                event.spotlight_rendering = text
                self.stats.tier3 += 1
                event.tier_used = 3
                return event
            self.stats.downgraded += 1
            # fall through to Tier 2

        # Tier 2 pathway
        if self.budget.can_use_tier2():
            resp = self.tier2.complete(prompt, max_tokens=256)
            event.enhanced_rendering = resp.text
            self.budget.record(2, resp.tokens_out)
            self.stats.tier2 += 1
            event.tier_used = 2
        else:
            self.stats.tier1 += 1
            event.tier_used = 1
        return event
