"""Conscious overlays on top of the subconscious rule machine.

Two components, both LLM-driven:
- ConsciousnessLayer: per-event verdict (APPROVE / ADJUST / VETO) that can
  override rule-proposed outcomes before they resolve.
- DebatePhase: at top-importance events, runs an orchestrator+workers round
  where 3-5 stakeholders each give first-person reactions, then synthesizes.

Subconscious (rules) always runs. Conscious layers activate probabilistically
with event importance. When conscious overrides, its answer wins.
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
    ) -> None:
        self.client = client
        self.rng = rng or random.Random()
        self.importance_threshold = importance_threshold
        self.activation_chance = activation_chance
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
            if a.current_goal:
                parts.append(f"    Current goal: {a.current_goal}")
            if a.tags:
                parts.append(f"    Tags: {', '.join(sorted(a.tags))}")
            # Recent events this agent was in
            recent = [e for e in world.events_since(max(1, world.current_tick - 3))
                      if a.agent_id in e.participants][-2:]
            if recent:
                parts.append(f"    Recent: {' | '.join(e.best_rendering()[:80] for e in recent)}")

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


# ══════════════════════════════════════════════════════════════
# Debate Phase — multi-agent LLM round for top-importance events
# ══════════════════════════════════════════════════════════════
# Flow:
#   1. Orchestrator identifies 3-5 relevant stakeholders by persona / stake.
#   2. Each stakeholder LLM-generates a short first-person reaction.
#   3. Orchestrator synthesizes a final narrative combining all voices.
# Triggered by EnhancementRouter when importance >= debate_threshold.

STAKEHOLDER_PICKER_PROMPT = """You are choosing which characters should weigh in on an event.
Pick 3 to 5 characters from the roster whose personas, goals, or tile proximity make them meaningfully affected.

Rules:
- Respond with ONLY agent_ids, one per line, no commentary, no quotes, no numbers.
- Include the direct event participants automatically.
- Prefer characters whose personas reveal a distinct angle (different stake, different faction).
"""


TAKE_PROMPT = """You ARE the following character. Write their reaction to the event below.

Rules:
1. Output 30-60 words, first person.
2. Stay strictly in character (persona, goal, speaking voice).
3. Reference your stake — what does this event mean for YOU?
4. No modern slang unless persona warrants.
5. Output ONLY the reaction. No name prefix, no quotes.
"""


SYNTHESIS_PROMPT = """You are the narrator. Combine the stakeholder reactions below into one coherent narrative paragraph (90-140 words).

Rules:
1. English, literary register.
2. Interweave voices — no bullet list, no headers.
3. End on a beat of tension or consequence — what shifts in the world now.
4. Output ONLY the paragraph.
"""


@dataclass
class Take:
    agent: Agent
    voice: str


class DebatePhase:
    """Runs a full debate round for a single high-importance event."""

    def __init__(
        self,
        orchestrator: LLMClient,
        worker: LLMClient,
        *,
        min_stakeholders: int = 3,
        max_stakeholders: int = 5,
    ) -> None:
        self.orchestrator = orchestrator
        self.worker = worker
        self.min_stakeholders = min_stakeholders
        self.max_stakeholders = max_stakeholders

    # ─── Step 1: pick stakeholders ───
    def _pick_stakeholders(self, event: LegendEvent, world: World) -> list[Agent]:
        # Always start with participants
        stakeholders: list[Agent] = []
        seen: set[str] = set()
        for aid in event.participants:
            a = world.get_agent(aid)
            if a and a.is_alive() and aid not in seen:
                stakeholders.append(a)
                seen.add(aid)

        # Build a small roster summary of historical figures and tile co-residents
        candidates: list[Agent] = []
        if event.tile_id:
            candidates.extend(world.agents_in_tile(event.tile_id))
        for a in world.historical_figures():
            if a.pack_id == event.pack_id:
                candidates.append(a)

        # Dedupe
        pool = []
        pool_ids: set[str] = set(seen)
        for a in candidates:
            if a.agent_id not in pool_ids and a.is_alive():
                pool.append(a)
                pool_ids.add(a.agent_id)

        # If orchestrator LLM available & pool big enough, ask it to pick
        if pool and self.orchestrator is not None and len(stakeholders) < self.max_stakeholders:
            roster_text = "\n".join(
                f"- {a.agent_id} ({a.display_name}) :: {a.persona_card[:160]}"
                for a in pool[:18]
            )
            prompt = (
                STAKEHOLDER_PICKER_PROMPT + "\n\n"
                f"EVENT: {event.event_kind} at {event.tile_id} (outcome: {event.outcome})\n"
                f"Base: {event.template_rendering}\n"
                f"Already included: {[s.display_name for s in stakeholders]}\n\n"
                f"ROSTER:\n{roster_text}\n\nAgent IDs:"
            )
            try:
                resp = self.orchestrator.complete(prompt, max_tokens=120, temperature=0.4)
                for line in (resp.text or "").splitlines():
                    aid = line.strip().strip("-*• ").split()[0] if line.strip() else ""
                    agent = world.get_agent(aid)
                    if agent and aid not in pool_ids and agent.is_alive():
                        stakeholders.append(agent)
                        pool_ids.add(aid)
                    if len(stakeholders) >= self.max_stakeholders:
                        break
            except Exception:
                pass

        # Fallback: top up with historical figures from same pack
        while len(stakeholders) < self.min_stakeholders and pool:
            agent = pool.pop(0)
            if agent.agent_id not in {s.agent_id for s in stakeholders}:
                stakeholders.append(agent)

        return stakeholders[: self.max_stakeholders]

    # ─── Step 2: each stakeholder gives their take ───
    def _get_take(self, agent: Agent, event: LegendEvent) -> Take:
        prompt = (
            TAKE_PROMPT + "\n\n"
            f"YOU ARE: {agent.display_name}\n"
            f"Persona: {agent.persona_card}\n"
            f"Your current goal: {agent.current_goal or '(none)'}\n\n"
            f"EVENT: {event.event_kind} (outcome: {event.outcome})\n"
            f"What happened: {event.template_rendering}\n\n"
            f"Your reaction:"
        )
        try:
            resp = self.worker.complete(prompt, max_tokens=140, temperature=0.9)
            voice = (resp.text or "").strip().strip('"')
        except Exception:
            voice = f"({agent.display_name} notes the event in silence.)"
        if len(voice) < 10:
            voice = f"({agent.display_name} gave no response that could be recorded.)"
        return Take(agent=agent, voice=voice)

    # ─── Step 3: synthesize ───
    def _synthesize(self, event: LegendEvent, takes: list[Take]) -> str:
        voices_text = "\n".join(
            f"[{t.agent.display_name}] {t.voice}" for t in takes
        )
        prompt = (
            SYNTHESIS_PROMPT + "\n\n"
            f"EVENT: {event.event_kind} at {event.tile_id} (outcome: {event.outcome})\n"
            f"Base: {event.template_rendering}\n\n"
            f"VOICES:\n{voices_text}\n\nNarrative:"
        )
        try:
            resp = self.orchestrator.complete(prompt, max_tokens=360, temperature=0.8)
            out = (resp.text or "").strip().strip('"')
        except Exception:
            out = event.template_rendering
        # Defensive: reject obvious prompt echoes from a misbehaving LLM
        suspect_markers = ("VOICES:", "Now write", "Base:", "EVENT:", "You are the narrator")
        if any(m in out for m in suspect_markers):
            out = event.template_rendering
        if len(out) < 40:
            out = event.template_rendering
        return out

    def run(self, event: LegendEvent, world: World) -> str:
        stakeholders = self._pick_stakeholders(event, world)
        if len(stakeholders) < 2:
            return event.template_rendering  # nothing to debate
        takes = [self._get_take(a, event) for a in stakeholders]
        return self._synthesize(event, takes)
