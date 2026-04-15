"""Abstract LLM client — concrete impls: MockTier2Client, Phi4Client (vLLM), ..."""

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
    def complete(self, prompt: str, *, max_tokens: int = 512, temperature: float = 0.7) -> LLMResponse:
        ...

    @property
    @abstractmethod
    def tier(self) -> int:
        """1 = rules (no LLM), 2 = small, 3 = large."""
        ...
