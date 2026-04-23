"""LLM primitives — client protocol + Ollama implementation.

This package now holds only the LLM transport layer. Everything that uses
an LLM "as an agent" (Narrator, Conscience, Planner, etc.) lives in
`living_world/agents/`.
"""

from living_world.llm.base import LLMClient, LLMResponse
from living_world.llm.ollama import OllamaClient

__all__ = [
    "LLMClient",
    "LLMResponse",
    "OllamaClient",
]
