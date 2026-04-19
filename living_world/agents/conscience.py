"""ConsciousnessLayer — LLM verdict on rule-proposed events.

For every rule-proposed event above a probability threshold, this layer asks
the LLM (speaking on behalf of the participants' personas + beliefs +
recalled memories) whether the action should APPROVE / ADJUST outcome / VETO.

Subconscious (rules) always runs; the conscious layer activates
probabilistically with event importance. When it overrides, it wins.
"""

from __future__ import annotations

import json
import random
import re
from dataclasses import dataclass

from living_world.core.agent import Agent
from living_world.core.event import EventProposal, LegendEvent
from living_world.core.world import World
from living_world.llm.base import LLMClient
from living_world.world_pack import EventTemplate


SYSTEM_PROMPT = """You decide whether characters actually carry out a proposed action.
You know their persona, current goal, and recent history. The rules machine has
suggested something might happen. Your job is ONE of three verdicts:

  APPROVE     — yes, this fits. Proceed with original outcome.
  ADJUST      — yes but the outcome differs. Provide: success | failure | neutral.
  VETO        — character would not do this. Skip entirely.

Output a single JSON object — no other text. Examples:

  {"verdict": "APPROVE"}
  {"verdict": "ADJUST", "outcome": "failure", "reason": "too frightened"}
  {"verdict": "VETO", "reason": "she would never betray her goal"}

Keep reasons to <15 words. Be decisive — most proposals should APPROVE.
"""


@dataclass
class ConsciousVerdict:
    verdict: str           # "APPROVE" | "ADJUST" | "VETO"
    outcome: str | None    # only set when ADJUST
    reason: str = ""

    @property
    def approves(self) -> bool:
        return self.verdict == "APPROVE"

    @property
    def vetoes(self) -> bool:
        return self.verdict == "VETO"

    @property
    def adjusts(self) -> bool:
        return self.verdict == "ADJUST" and self.outcome in ("success", "failure", "neutral")


class ConsciousnessLayer:
    """Asks an LLM whether the rule-proposed event should proceed as-is."""

    def __init__(
        self,
        client: LLMClient,
        rng: random.Random | None = None,
        *,
        importance_threshold: float = 0.5,
        activation_chance: float = 0.5,
        memory=None,  # optional AgentMemoryStore — enables memory-informed verdicts
    ) -> None:
        self.client = client
        self.rng = rng or random.Random()
        self.importance_threshold = importance_threshold
        self.activation_chance = activation_chance
        self.memory = memory
        # stats
        self.activations = 0
        self.approvals = 0
        self.adjustments = 0
        self.vetoes = 0

    def should_activate(self, template: EventTemplate) -> bool:
        """Decide whether to invoke the LLM for this proposal.
        Higher-importance templates activate more often.
        """
        base_imp = float(template.base_importance or 0.1)
        if base_imp < self.importance_threshold:
            return False
        # Linearly scale activation probability with importance above threshold
        room = max(0.0, 1.0 - self.importance_threshold)
        boost = min(1.0, (base_imp - self.importance_threshold) / max(0.05, room))
        effective = self.activation_chance * (0.5 + 0.5 * boost)
        return self.rng.random() < effective

    def _build_prompt(
        self,
        proposal: EventProposal,
        template: EventTemplate,
        participants: list[Agent],
        world: World,
    ) -> str:
        parts = [SYSTEM_PROMPT, "", "PROPOSED EVENT"]
        parts.append(f"  Kind: {template.event_kind}")
        parts.append(f"  Description: {template.description}")
        tile = world.get_tile(proposal.tile_id)
        if tile:
            parts.append(f"  Location: {tile.display_name} ({tile.tile_type})")
        parts.append(f"  Importance: {template.base_importance:.2f}")

        parts.append("")
        parts.append("CHARACTERS INVOLVED")
        for a in participants:
            parts.append(f"  - {a.display_name} ({a.agent_id})")
            parts.append(f"    Persona: {(a.persona_card or '').strip()[:200]}")
            if a.alignment and a.alignment != "neutral":
                parts.append(f"    Alignment: {a.alignment}")
            if a.current_goal:
                parts.append(f"    Current goal: {a.current_goal}")
            if a.tags:
                parts.append(f"    Tags: {', '.join(sorted(a.tags))}")
            if a.inventory:
                items = ", ".join(i.name for i in a.inventory[:4])
                parts.append(f"    Carrying: {items}")
            beliefs = a.get_beliefs()
            if beliefs:
                bits = [f"{k}: {v}" for k, v in list(beliefs.items())[:3]]
                parts.append(f"    Beliefs: {' | '.join(bits)}")
            # Recent events this agent was in
            recent = [e for e in world.events_since(max(1, world.current_tick - 3))
                      if a.agent_id in e.participants][-2:]
            if recent:
                parts.append(f"    Recent: {' | '.join(e.best_rendering()[:80] for e in recent)}")
            # Memory recall — relevant memories for this event
            if self.memory is not None:
                try:
                    query = f"{template.event_kind} {proposal.tile_id}"
                    entries = self.memory.recall(a.agent_id, query, top_k=3) or []
                except Exception:
                    entries = []
                if entries:
                    snippets = [e.doc[:110].replace("\n", " ")
                                for e in entries if getattr(e, "doc", None)]
                    if snippets:
                        parts.append(f"    Relevant memories: {' || '.join(snippets)}")

        parts.append("")
        parts.append("Your verdict JSON:")
        return "\n".join(parts)

    def _parse_verdict(self, text: str) -> ConsciousVerdict | None:
        text = (text or "").strip()
        if not text:
            return None
        # Strip common prefixes/wrapping
        if "```" in text:
            # pull first {} block out of fenced code
            m = re.search(r"\{[\s\S]*?\}", text)
            if m:
                text = m.group(0)
        else:
            # take first {...} found
            m = re.search(r"\{[\s\S]*?\}", text)
            if m:
                text = m.group(0)
        try:
            data = json.loads(text)
        except Exception:
            return None
        verdict = str(data.get("verdict", "")).upper().strip()
        if verdict not in ("APPROVE", "ADJUST", "VETO"):
            return None
        outcome = data.get("outcome")
        if outcome is not None:
            outcome = str(outcome).lower().strip()
        reason = str(data.get("reason", ""))[:80]
        return ConsciousVerdict(verdict=verdict, outcome=outcome, reason=reason)

    def consider(
        self,
        proposal: EventProposal,
        template: EventTemplate,
        participants: list[Agent],
        world: World,
    ) -> ConsciousVerdict | None:
        """Main entry. Returns None if LLM unreachable or parse failed — caller
        should treat None as "subconscious proceeds unchanged"."""
        if not participants:
            return None
        self.activations += 1
        prompt = self._build_prompt(proposal, template, participants, world)
        try:
            resp = self.client.complete(prompt, max_tokens=80, temperature=0.3)
        except Exception as exc:
            print(f"[consciousness] LLM call failed: {exc}")
            return None
        verdict = self._parse_verdict(resp.text)
        if verdict is None:
            return None
        if verdict.approves:
            self.approvals += 1
        elif verdict.adjusts:
            self.adjustments += 1
        elif verdict.vetoes:
            self.vetoes += 1
        return verdict

    def summary(self) -> dict[str, int]:
        return {
            "activations": self.activations,
            "approvals": self.approvals,
            "adjustments": self.adjustments,
            "vetoes": self.vetoes,
        }

