"""Dynamic dialogue / narrative generation at Tier 3.

Replaces template strings with LLM-written prose that knows each agent's
persona, goal, and recent memory. Much richer than {$a ${b}} substitution.

Triggered automatically by EnhancementRouter when event importance >= Tier 3
threshold, IF `settings.llm.dynamic_dialogue_enabled` is True.
"""

from __future__ import annotations

from living_world.core.agent import Agent
from living_world.core.event import LegendEvent
from living_world.core.world import World
from living_world.llm.base import LLMClient


SYSTEM_PROMPT = """You are a quiet, careful narrator for a living-world simulation.
Your output is inserted into a chronological chronicle and must be short, specific, and faithful to the characters.

RULES
1. Output ONE short narrative paragraph, 60-120 words.
2. English, literary register. Avoid modern slang unless the character uses it.
3. Show characters' voices — a scholar speaks like a scholar; an SCP anomaly does not speak at all.
4. Do NOT invent deaths, marriages, or major plot twists not stated in the base narrative.
5. Do NOT contradict the given outcome (success / failure / neutral).
6. Do NOT use meta-language ("In this scene...", "The narrator observes...").
7. Output the narrative ONLY. No headers, no commentary, no quotes around it.
"""


def _render_memory_hint(memory_lines: list[str], max_items: int = 3) -> str:
    if not memory_lines:
        return "(none)"
    picked = memory_lines[-max_items:]
    return "\n".join(f"  - {m.strip()[:180]}" for m in picked if m.strip())


def build_prompt(
    event: LegendEvent,
    participants: list[Agent],
    world: World,
    memory_snippets: dict[str, list[str]] | None = None,
) -> str:
    """Assemble the prompt for dialogue generation.

    memory_snippets: optional dict of {agent_id: [recent_memory_strings]}.
    """
    parts: list[str] = []

    # Characters block
    parts.append("CHARACTERS")
    for i, agent in enumerate(participants, start=1):
        name = agent.display_name
        persona = (agent.persona_card or "").strip()
        goal = (agent.current_goal or "").strip() or "(no stated goal)"
        parts.append(f"[{i}] {name}")
        parts.append(f"  Persona: {persona}")
        parts.append(f"  Current goal: {goal}")
        parts.append(f"  Status: {agent.life_stage.value}, age {agent.age}")
        if memory_snippets and memory_snippets.get(agent.agent_id):
            parts.append(f"  Recent memory for {name}:")
            parts.append(_render_memory_hint(memory_snippets[agent.agent_id]))

    # Location
    tile = world.get_tile(event.tile_id) if event.tile_id else None
    if tile:
        parts.append("")
        parts.append(f"LOCATION: {tile.display_name}")
        parts.append(f"  Type: {tile.tile_type}")
        if tile.description:
            parts.append(f"  Description: {tile.description.strip()}")

    # Event
    parts.append("")
    parts.append("EVENT")
    parts.append(f"  Kind: {event.event_kind}")
    parts.append(f"  Outcome: {event.outcome}")
    parts.append(f"  Day: {event.tick}")
    if event.template_rendering:
        parts.append(f"  Base narrative (factual core; elaborate on this):")
        parts.append(f"    {event.template_rendering.strip()}")
    if event.stat_changes:
        parts.append(f"  Stat changes: {event.stat_changes}")
    if event.relationship_changes:
        parts.append(f"  Relationship changes: {event.relationship_changes}")

    parts.append("")
    parts.append("Now write the narrative paragraph.")
    return "\n".join(parts)


class DialogueGenerator:
    """Takes a resolved LegendEvent and produces rich narrative via LLM."""

    def __init__(self, client: LLMClient) -> None:
        self.client = client

    def generate(
        self,
        event: LegendEvent,
        participants: list[Agent],
        world: World,
        memory_snippets: dict[str, list[str]] | None = None,
        max_tokens: int = 280,
        temperature: float = 0.85,
    ) -> str:
        prompt = SYSTEM_PROMPT + "\n\n" + build_prompt(event, participants, world, memory_snippets)
        resp = self.client.complete(prompt, max_tokens=max_tokens, temperature=temperature)
        text = (resp.text or "").strip()
        # Strip accidental quotes / headers
        for prefix in ("Narrative:", "Here is", '"'):
            if text.startswith(prefix):
                text = text[len(prefix):].strip().lstrip('"').strip()
        if text.endswith('"'):
            text = text[:-1]
        # Fallback to template if LLM gave nothing usable
        if len(text) < 20:
            return event.template_rendering
        return text
