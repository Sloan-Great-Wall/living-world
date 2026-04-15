"""Translation clients. Swap NLLB-200 for production; use Ollama for MVP."""

from __future__ import annotations

import hashlib
from abc import ABC, abstractmethod
from functools import lru_cache

import httpx


class Translator(ABC):
    @abstractmethod
    def translate(self, text: str, *, target: str = "zh") -> str:
        ...


class NoopTranslator(Translator):
    """Returns input unchanged. Used when locale matches source."""

    def translate(self, text: str, *, target: str = "zh") -> str:
        return text


class OllamaTranslator(Translator):
    """Reuses a small Ollama model (default gemma3:4b) for quick translation.

    NOT a dedicated translation model — quality is 'good enough for MVP'.
    For Stage B+, swap to NLLB-200 or dedicated translation service.
    """

    def __init__(
        self,
        model: str = "gemma3:4b",
        base_url: str = "http://localhost:11434",
        timeout: float = 30.0,
    ) -> None:
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def translate(self, text: str, *, target: str = "zh") -> str:
        if not text.strip():
            return text
        lang_name = {"zh": "Simplified Chinese", "en": "English", "ja": "Japanese"}.get(target, target)
        prompt = (
            f"Translate the following narrative into natural, literary {lang_name}. "
            f"Preserve tone. Output translation only, no commentary.\n\n{text}"
        )
        try:
            r = httpx.post(
                f"{self.base_url}/api/generate",
                json={"model": self.model, "prompt": prompt, "stream": False,
                      "options": {"temperature": 0.3, "num_predict": 512}},
                timeout=self.timeout,
            )
            r.raise_for_status()
            return r.json().get("response", "").strip() or text
        except Exception:
            return text  # fail soft: show original


# Tiny in-process LRU cache keyed by hash(text, target).
# For production, back this with Redis so translation cost amortizes across users.
def cached(translator: Translator, max_size: int = 2048) -> Translator:
    class _Cached(Translator):
        def __init__(self) -> None:
            self._lru = lru_cache(maxsize=max_size)(self._translate_impl)

        def _translate_impl(self, key: str, text: str, target: str) -> str:
            return translator.translate(text, target=target)

        def translate(self, text: str, *, target: str = "zh") -> str:
            key = hashlib.sha1(f"{target}::{text}".encode("utf-8")).hexdigest()
            return self._lru(key, text, target)

    return _Cached()
