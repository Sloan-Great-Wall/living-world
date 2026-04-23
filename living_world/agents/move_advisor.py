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
{plan_block}{memory_block}
CANDIDATE LOCATIONS
{candidates}

Pick ONE destination tile_id that best matches the character's persona, goal, plan, and memories.
Output ONLY the tile_id, nothing else. Example: "market-street".
Tile id:"""


class LLMMoveAdvisor:
    def __init__(self, client: LLMClient, memory_store=None) -> None:
        self.client = client
        self.memory_store = memory_store

    def _plan_block(self, agent: Agent) -> str:
        plan = agent.get_weekly_plan() if hasattr(agent, "get_weekly_plan") else {}
        if not plan:
            return ""
        bits: list[str] = []
        for key in ("goals_this_week", "seek", "avoid"):
            items = plan.get(key)
            if isinstance(items, list) and items:
                bits.append(f"  {key}: {', '.join(str(x) for x in items[:4])}")
        if not bits:
            return ""
        return "Weekly plan:\n" + "\n".join(bits) + "\n"

    def _memory_block(self, agent: Agent, world=None) -> str:
        if self.memory_store is None:
            return ""
        query = agent.current_goal or agent.display_name
        try:
            entries = (
                self.memory_store.recall(
                    agent.agent_id,
                    query,
                    top_k=2,
                    current_tick=world.current_tick if world else None,
                )
                or []
            )
        except Exception:
            return ""
        lines = [getattr(e, "doc", "")[:120].replace("\n", " ") for e in entries]
        lines = [line for line in lines if line]
        if not lines:
            return ""
        return "Relevant memories:\n" + "\n".join(f"  - {line}" for line in lines) + "\n"

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
        # Resolve tiles up front so the comprehension's type narrows cleanly
        # for pyright (avoids Optional access via a separate .get_tile() call).
        cand_tiles = [(tid, world.get_tile(tid)) for tid, _ in sorted_cands]
        cand_text = "\n".join(
            f"- {tid} ({tile.tile_type}: {(tile.description or '')[:80]})"
            for tid, tile in cand_tiles
            if tile is not None
        )
        prompt = PROMPT_TEMPLATE.format(
            name=agent.display_name,
            persona=(agent.persona_card or "").strip()[:280],
            goal=agent.current_goal or "(none)",
            current_tile=agent.current_tile or "(unknown)",
            plan_block=self._plan_block(agent),
            memory_block=self._memory_block(agent, world),
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
