"""LLM-driven movement advisor.

Given an agent + candidate tiles, asks a small LLM which tile the agent wants
to go to given their persona, goal, and recent story. Intended as an optional
override to the tag-affinity table used by MovementPolicy.

Expensive (one LLM call per applied move). Default usage: only historical
figures, and only ~30% of their ticks. Toggled via settings.llm.llm_movement_*.
"""

from __future__ import annotations

from living_world.core.agent import Agent
from living_world.core.world import World
from living_world.llm.base import LLMClient


PROMPT_TEMPLATE = """You are deciding where a character wants to go next.

CHARACTER
Name: {name}
Persona: {persona}
Current goal: {goal}
Currently at: {current_tile}

CANDIDATE LOCATIONS
{candidates}

Pick ONE destination tile_id that best matches the character's persona and goal.
Output ONLY the tile_id, nothing else. Example: "market-street".
Tile id:"""


class LLMMoveAdvisor:
    def __init__(self, client: LLMClient) -> None:
        self.client = client

    def suggest(
        self,
        agent: Agent,
        world: World,
        candidates: list[tuple[str, float]],
    ) -> str | None:
        if not candidates:
            return None
        # Prompt with top 8 candidates by weight
        sorted_cands = sorted(candidates, key=lambda c: -c[1])[:8]
        cand_text = "\n".join(
            f"- {tid} ({world.get_tile(tid).tile_type}: "
            f"{(world.get_tile(tid).description or '')[:80]})"
            for tid, _ in sorted_cands if world.get_tile(tid) is not None
        )
        prompt = PROMPT_TEMPLATE.format(
            name=agent.display_name,
            persona=(agent.persona_card or "").strip()[:280],
            goal=agent.current_goal or "(none)",
            current_tile=agent.current_tile or "(unknown)",
            candidates=cand_text,
        )
        try:
            resp = self.client.complete(prompt, max_tokens=20, temperature=0.4)
        except Exception:
            return None
        picked = (resp.text or "").strip().strip('"').split("\n")[0].strip()
        # Validate it's one of the candidates
        valid = {tid for tid, _ in candidates}
        if picked in valid:
            return picked
        # Loose match — LLM might output with extra punctuation
        for tid in valid:
            if tid in picked:
                return tid
        return None
