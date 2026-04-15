"""LLM clients — Ollama (local) or None (pure rules).

`EnhancementRouter` drives tier routing. If a tier's client is None, events
at that tier fall back to pure template rendering (subconscious rules).
"""

from living_world.llm.base import LLMClient, LLMResponse
from living_world.llm.ollama import OllamaClient
from living_world.llm.router import EnhancementRouter, TierBudget

__all__ = [
    "LLMClient",
    "LLMResponse",
    "OllamaClient",
    "EnhancementRouter",
    "TierBudget",
]
