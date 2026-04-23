"""Abstract LLM client — concrete impls: OllamaClient, (future) Phi4Client (vLLM), ...

Error model (AI-Native criterion B — errors must be type-dispatchable, not
string-parsed):

    LLMError                        ← base
      ├─ LLMUnreachable             ← daemon down / DNS fail / connection refused
      ├─ LLMTimeout                 ← request exceeded configured timeout
      ├─ LLMBadResponse             ← HTTP 4xx/5xx, malformed JSON, missing fields
      └─ LLMUnknownError            ← fallback

Callers DO NOT receive raised exceptions on the hot path — the sim must
continue running even if Ollama flaps. Instead, `LLMResponse.error`
carries a typed `LLMError | None`. Consumers check `resp.ok`, or
`isinstance(resp.error, LLMTimeout)` to branch. No more `[ollama-error: X]`
sentinel strings in `.text` (which looked like valid output to anything
downstream that didn't know the sentinel).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


class LLMError(Exception):
    """Base class for LLM-backend failures that should NOT crash the sim.

    Attached to `LLMResponse.error` rather than raised, so the tick loop
    keeps running during a flake. `.kind` is the machine-readable tag
    that structured logs + dashboards filter on.
    """

    kind: str = "llm_error"

    def __init__(self, message: str = "", *, cause: Exception | None = None) -> None:
        super().__init__(message or self.kind)
        self.cause = cause

    def to_dict(self) -> dict[str, str]:
        return {
            "kind": self.kind,
            "message": str(self),
            "cause_type": self.cause.__class__.__name__ if self.cause else "",
        }


class LLMUnreachable(LLMError):
    """Daemon not responding (connection refused, DNS fail, network down)."""

    kind = "llm_unreachable"


class LLMTimeout(LLMError):
    """Request exceeded the configured timeout."""

    kind = "llm_timeout"


class LLMBadResponse(LLMError):
    """HTTP error status, malformed JSON, or missing required fields."""

    kind = "llm_bad_response"


class LLMUnknownError(LLMError):
    """Fallback for exceptions we don't recognize. Logged + preserved so
    AI-driven debug can read `cause_type` and triage."""

    kind = "llm_unknown"


@dataclass
class LLMResponse:
    text: str = ""
    tokens_in: int = 0
    tokens_out: int = 0
    latency_ms: float = 0.0
    model: str = ""
    error: LLMError | None = field(default=None)

    @property
    def ok(self) -> bool:
        """True iff the call succeeded AND produced some text."""
        return self.error is None

    @property
    def error_kind(self) -> str:
        """Machine-readable tag, `""` when ok. Use this in logs + metrics."""
        return self.error.kind if self.error is not None else ""


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

        On backend failure, returns an LLMResponse with `error` set and
        `text=""` — does NOT raise. The tick loop must keep running.
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
            self.complete,
            prompt,
            max_tokens=max_tokens,
            temperature=temperature,
            json_mode=json_mode,
            system=system,
        )

    @property
    @abstractmethod
    def tier(self) -> int:
        """1 = rules (no LLM), 2 = small, 3 = large."""
        ...
