"""Ollama client — real local LLM on MacBook (M1/M2/M3) or any host.

Ollama handles quantization + unified-memory automatically. Models like
`gemma3:4b`, `phi3.5:latest`, `llama3.2:3b` run comfortably on 16GB MacBooks.

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

    @property
    def tier(self) -> int:
        return self._declared_tier

    def available(self) -> bool:
        try:
            r = httpx.get(f"{self.base_url}/api/tags", timeout=3.0)
            return r.status_code == 200
        except Exception:
            return False

    def complete(self, prompt: str, *, max_tokens: int = 256, temperature: float = 0.7) -> LLMResponse:
        t0 = time.time()
        body: dict[str, Any] = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "num_predict": max_tokens,
                "temperature": temperature,
            },
        }
        try:
            r = httpx.post(f"{self.base_url}/api/generate", json=body, timeout=self.timeout)
            r.raise_for_status()
            data = r.json()
        except Exception as exc:
            # graceful fallback so a dropped Ollama doesn't crash the sim
            return LLMResponse(
                text=f"[ollama-error: {exc.__class__.__name__}] {prompt[:120]}",
                model=self.model,
                latency_ms=(time.time() - t0) * 1000,
            )
        text = data.get("response", "").strip()
        return LLMResponse(
            text=text,
            tokens_in=int(data.get("prompt_eval_count", 0) or 0),
            tokens_out=int(data.get("eval_count", 0) or 0),
            latency_ms=(time.time() - t0) * 1000,
            model=self.model,
        )
