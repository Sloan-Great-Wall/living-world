"""Ollama client — real local LLM on MacBook (M1/M2/M3) or any host.

Provides BOTH sync (`complete`) and async (`acomplete`) entry points.
The async path lets the engine `asyncio.gather` independent agent calls
within a tick — combined with `OLLAMA_NUM_PARALLEL=4` on the daemon,
this gives 3-5× speedup with zero quality cost.

For production GPU server deployment, swap to a vLLM-backed OpenAI endpoint.
"""

from __future__ import annotations

import time
from typing import Any

import httpx

from living_world.llm.base import LLMClient, LLMResponse


class OllamaClient(LLMClient):
    def __init__(
        self,
        model: str = "gemma3:4b",
        base_url: str = "http://localhost:11434",
        declared_tier: int = 2,
        timeout: float = 60.0,
    ) -> None:
        self.model = model
        self.base_url = base_url.rstrip("/")
        self._declared_tier = declared_tier
        self.timeout = timeout
        # Lazily-created reusable async client. Sharing one client keeps
        # the connection pool warm across the whole sim, which is where
        # the bulk of the concurrency win lives.
        self._async_client: httpx.AsyncClient | None = None

    @property
    def tier(self) -> int:
        return self._declared_tier

    def _build_body(
        self, prompt: str, *, max_tokens: int, temperature: float, json_mode: bool,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "num_predict": max_tokens,
                "temperature": temperature,
            },
        }
        if json_mode:
            body["format"] = "json"
        return body

    def _decode(self, data: dict, t0: float) -> LLMResponse:
        return LLMResponse(
            text=(data.get("response", "") or "").strip(),
            tokens_in=int(data.get("prompt_eval_count", 0) or 0),
            tokens_out=int(data.get("eval_count", 0) or 0),
            latency_ms=(time.time() - t0) * 1000,
            model=self.model,
        )

    def _err(self, exc: Exception, t0: float) -> LLMResponse:
        # Graceful fallback: do NOT echo prompt back (would leak into
        # event narratives, see narrator._BAD_SUBSTRINGS).
        return LLMResponse(
            text=f"[ollama-error: {exc.__class__.__name__}]",
            model=self.model,
            latency_ms=(time.time() - t0) * 1000,
        )

    def available(self) -> bool:
        try:
            r = httpx.get(f"{self.base_url}/api/tags", timeout=3.0)
            return r.status_code == 200
        except Exception:
            return False

    def complete(
        self, prompt: str, *,
        max_tokens: int = 256, temperature: float = 0.7, json_mode: bool = False,
    ) -> LLMResponse:
        t0 = time.time()
        body = self._build_body(prompt, max_tokens=max_tokens,
                                  temperature=temperature, json_mode=json_mode)
        try:
            r = httpx.post(f"{self.base_url}/api/generate",
                           json=body, timeout=self.timeout)
            r.raise_for_status()
            return self._decode(r.json(), t0)
        except Exception as exc:
            return self._err(exc, t0)

    async def acomplete(
        self, prompt: str, *,
        max_tokens: int = 256, temperature: float = 0.7, json_mode: bool = False,
    ) -> LLMResponse:
        """Async variant — drop into asyncio.gather() to run many calls
        in parallel against a single Ollama daemon (which itself batches
        4 requests in parallel when started with OLLAMA_NUM_PARALLEL=4)."""
        t0 = time.time()
        body = self._build_body(prompt, max_tokens=max_tokens,
                                  temperature=temperature, json_mode=json_mode)
        if self._async_client is None:
            self._async_client = httpx.AsyncClient(timeout=self.timeout)
        try:
            r = await self._async_client.post(
                f"{self.base_url}/api/generate", json=body,
            )
            r.raise_for_status()
            return self._decode(r.json(), t0)
        except Exception as exc:
            return self._err(exc, t0)

    async def aclose(self) -> None:
        if self._async_client is not None:
            await self._async_client.aclose()
            self._async_client = None
