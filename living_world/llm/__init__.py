"""LLM clients — Tier 2 (small) and Tier 3 (large) + translation.

Stage A ships with a mock Tier 2 that just decorates templates, so routing
and budget logic can be tested without GPU. Swap in `Phi4Client` once a vLLM
endpoint is available.
"""

from living_world.llm.base import LLMClient, LLMResponse
from living_world.llm.mock import MockTier2Client, MockTier3Client
from living_world.llm.ollama import OllamaClient
from living_world.llm.router import EnhancementRouter, TierBudget

__all__ = [
    "LLMClient",
    "LLMResponse",
    "MockTier2Client",
    "MockTier3Client",
    "OllamaClient",
    "EnhancementRouter",
    "TierBudget",
]
