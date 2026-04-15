"""Debate Phase — multi-agent LLM round for top-importance events.

Design from docs/stat-machine-design.md §Debate Phase.

Flow:
  1. Orchestrator identifies 3-5 relevant stakeholders by persona / stake.
  2. Each stakeholder LLM-generates a short first-person reaction.
  3. Orchestrator synthesizes a final narrative combining all voices.

Triggered by EnhancementRouter when event.importance >= debate_threshold AND
`settings.llm.debate_enabled` is True.
"""

from __future__ import annotations

from dataclasses import dataclass

from living_world.core.agent import Agent
from living_world.core.event import LegendEvent
from living_world.core.world import World
from living_world.llm.base import LLMClient


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
        if len(out) < 40:
            out = event.template_rendering
        return out

    def run(self, event: LegendEvent, world: World) -> str:
        stakeholders = self._pick_stakeholders(event, world)
        if len(stakeholders) < 2:
            return event.template_rendering  # nothing to debate
        takes = [self._get_take(a, event) for a in stakeholders]
        return self._synthesize(event, takes)
