"""Mock clients for offline testing.

Decorates the base template with 'Phi-4 would rewrite this...' so you can
verify the router picked the right tier without spending tokens.
"""

from __future__ import annotations

import random

from living_world.llm.base import LLMClient, LLMResponse


# Stock phrases per tone — stand-ins for real model output.
TIER2_FLAVOR: dict[str, list[str]] = {
    "scp": [
        "Incident Log [$kind]: $body — observed; pending supplementary analysis.",
        "Addendum to prior report: $body Monitoring continues per containment protocol.",
    ],
    "liaozhai": [
        "是夜, $body 风过松梢, 余音未歇。",
        "$body 观者莫解, 唯月色冷照。",
    ],
    "cthulhu": [
        "$body The silence that followed felt older than the room itself.",
        "$body A sensation, not a sound, moved through the listener.",
    ],
}


class MockTier2Client(LLMClient):
    """Pretend-Phi-4. Use for routing tests before GPU comes online."""

    def __init__(self, seed: int = 13) -> None:
        self.rng = random.Random(seed)

    @property
    def tier(self) -> int:
        return 2

    def complete(self, prompt: str, *, max_tokens: int = 512, temperature: float = 0.7) -> LLMResponse:
        # Detect "dialogue-style" long free-text prompts (from DialogueGenerator,
        # DebatePhase, or ConsciousnessLayer). Mock can't author real prose —
        # return a short stub instead of echoing the prompt.
        is_dialogue_prompt = len(prompt) > 400 and "[BODY=" not in prompt
        if is_dialogue_prompt:
            # Consciousness layer wants JSON — give a canned APPROVE so events proceed.
            if '"verdict"' in prompt or "APPROVE" in prompt:
                return LLMResponse(
                    text='{"verdict": "APPROVE"}',
                    tokens_in=len(prompt), tokens_out=20, model="mock-phi4",
                )
            # DialogueGenerator / DebatePhase — try to extract the base narrative
            stub = "(mock provider — switch tier2/tier3 to ollama for narrative)"
            for marker in ("Base narrative", "BASE NARRATIVE"):
                if marker in prompt:
                    idx = prompt.index(marker)
                    tail = prompt[idx:].split("\n", 2)
                    if len(tail) >= 2:
                        stub = tail[1].strip(" :")[:240] or stub
                        break
            return LLMResponse(
                text=stub, tokens_in=len(prompt), tokens_out=len(stub),
                model="mock-phi4",
            )

        # Legacy short structured prompt — [PACK=][KIND=][BODY=]
        pack = "scp"
        body = prompt.strip()
        kind = "unknown"
        if "[PACK=" in prompt:
            start = prompt.index("[PACK=") + 6
            end = prompt.index("]", start)
            pack = prompt[start:end]
        if "[KIND=" in prompt:
            start = prompt.index("[KIND=") + 6
            end = prompt.index("]", start)
            kind = prompt[start:end]
        if "[BODY=" in prompt:
            start = prompt.index("[BODY=") + 6
            end = prompt.rindex("]")
            body = prompt[start:end]

        template = self.rng.choice(TIER2_FLAVOR.get(pack, TIER2_FLAVOR["scp"]))
        text = template.replace("$body", body).replace("$kind", kind)
        return LLMResponse(text=text, tokens_in=len(prompt), tokens_out=len(text), model="mock-phi4")


class MockTier3Client(LLMClient):
    """Pretend-Gemma-4-31B. Currently just delegates to Tier 2 mock with a flourish."""

    def __init__(self, seed: int = 29) -> None:
        self.rng = random.Random(seed)
        self._tier2 = MockTier2Client(seed=seed + 1)

    @property
    def tier(self) -> int:
        return 3

    def complete(self, prompt: str, *, max_tokens: int = 512, temperature: float = 0.7) -> LLMResponse:
        base = self._tier2.complete(prompt, max_tokens=max_tokens, temperature=temperature)
        flourish = " (Spotlight: the world shifts in quiet, measurable ways.)"
        return LLMResponse(
            text=base.text + flourish,
            tokens_in=base.tokens_in,
            tokens_out=base.tokens_out + 20,
            model="mock-gemma4",
        )
