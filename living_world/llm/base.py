"""Abstract LLM client — concrete impls: OllamaClient, (future) Phi4Client (vLLM), ..."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class LLMResponse:
    text: str
    tokens_in: int = 0
    tokens_out: int = 0
    latency_ms: float = 0.0
    model: str = ""


class LLMClient(ABC):
    """Minimal contract that every tier client must satisfy."""

    @abstractmethod
    def complete(
        self,
        prompt: str,
        *,
        max_tokens: int = 512,
        temperature: float = 0.7,
        json_mode: bool = False,
        system: str = "",
    ) -> LLMResponse:
        """If json_mode=True the impl should constrain output to valid JSON
        (e.g. Ollama's `format=json` grammar).

        `system` (P1 KV-cache hint): if non-empty, treated as the system
        prompt and kept STABLE across calls so the model's KV state for
        this prefix can be reused. Move all variable / dynamic content
        into `prompt`; keep instructions + examples in `system`. Backends
        that don't support a separate system field should prepend it.
        """
        ...

    async def acomplete(
        self,
        prompt: str,
        *,
        max_tokens: int = 512,
        temperature: float = 0.7,
        json_mode: bool = False,
        system: str = "",
    ) -> LLMResponse:
        """Async variant. Default impl runs sync `complete` in a thread so
        any LLMClient gains async without per-impl plumbing. Real concurrency
        wins come when an impl overrides this with httpx.AsyncClient (see
        OllamaClient)."""
        import asyncio
        return await asyncio.to_thread(
            self.complete, prompt,
            max_tokens=max_tokens, temperature=temperature,
            json_mode=json_mode, system=system,
        )

    @property
    @abstractmethod
    def tier(self) -> int:
        """1 = rules (no LLM), 2 = small, 3 = large."""
        ...
