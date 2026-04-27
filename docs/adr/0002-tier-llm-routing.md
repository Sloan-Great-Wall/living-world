# ADR 0002 · Tier 1 / 2 / 3 LLM routing

| Status | Accepted (retroactive — codified 2026-04-26) |
|---|---|
| Deciders | sloan + Claude |
| Supersedes | — |

## Context

A naive simulator runs every event through the LLM: every dice roll,
every move, every line of dialogue. That is correct in spirit ("the
LLM is the imagination"), but at ~12 minutes/tick on consumer hardware
it makes the sim unusable.

We need a routing rule that decides, *for each event*, whether the LLM
gets to weigh in or whether deterministic rules suffice.

## Decision

Three tiers, gated by `event.importance`:

```
Tier 1 — pure rules (no LLM)
  · template_rendering from YAML pack
  · score_event_importance, dice resolution, consequences
  · cost: ~zero

Tier 2 — small LLM (currently llama3.2:3b via Ollama)
  · subjective perception, dialogue reactions, planner, move advisor,
    self_update, emergent proposer (the "many small calls" lane)
  · cost: ~50-200 ms per call on M-series Mac

Tier 3 — large LLM (currently gemma3:4b via Ollama)
  · narrator (vivid rewrite of high-importance events)
  · chronicler (chapter-level synthesis every N ticks)
  · cost: ~1-3 s per call
```

Routing rule (in `living_world/agents/narrator.py`):
- `event.importance < TIER3_THRESHOLD (0.65)` → keep template (Tier 1)
- `≥ threshold AND budget allows` → Tier 3 LLM rewrite

`importance` itself is computed by deterministic rules
(`score_event_importance`) — so an event self-classifies into a tier
without an LLM round-trip.

Tier 2 modules each have their own activation gates (e.g.
`perception_threshold`, `self_update_threshold`) so they only fire on
events that justify the cost.

## Alternatives considered

### A · Single-tier (LLM for everything)
- **Pro**: simplest mental model
- **Con**: 12-min ticks, infeasible
- **Verdict**: rejected on day one

### B · Two-tier (rules + one LLM)
- **Pro**: fewer model swaps, simpler config
- **Con**: a 4 B narrator wastes budget on tier-2 work; a 1 B planner
  writes badly. The "small + large" split is a real wing of the
  tradeoff curve, not an artifact
- **Verdict**: rejected. The cost ratio between tier-2 and tier-3
  modules is ~10×; lumping them wastes one or the other.

### C · Importance-graded continuous routing (no discrete tiers)
- **Pro**: more granular, in principle better calibration
- **Con**: every callsite would need its own threshold logic; harder
  to budget; harder to explain to AI tools
- **Verdict**: rejected. Three discrete tiers is the right floor of
  complexity for a single-person project.

## Consequences

**Positive**:
- 12 min/tick → 2-3 min/tick measurable improvement
- Each LLM module can be swapped independently
  (`ollama_module_models[chronicler] = qwen3:14b`)
- Clear cost story: "tier 1 is free, tier 2 is fast, tier 3 is
  spotlight"

**Negative**:
- Three model files to keep loaded — RAM pressure on small machines
  (the v4 hang on 32 GB MBP was traced to gemma4:e4b 12.6 GB +
  llama3.2:3b 3 GB + KV ×4 exceeding budget; we swapped tier 3 to
  gemma3:4b 3.3 GB and added `OLLAMA_NUM_PARALLEL=2`)
- A new LLM module has to choose a tier explicitly — no default

**Tier 2 / Tier 3 specific learnings**:
- Tier 3 narrator with cheap models writes like a college essay; needs
  prompt clamping (the `_BAD_PREFIXES` / `_BAD_SUBSTRINGS` filters in
  `narrator.py`) to reject "Okay, here is the…" preambles
- Tier 2 modules benefit dramatically from `format=json` grammar +
  `system=` field for KV cache reuse

## Validation criteria

Revisit if:
1. A future LLM is fast enough that Tier 1 stops being meaningfully
   cheaper (single tier becomes viable)
2. Per-module model overrides start carrying ≥3 distinct models in
   production (the "tier" abstraction is leaking)
3. Anyone needs more than three tiers (e.g. tier 0 = stub for tests
   already exists informally; tier 4 = remote vLLM for production
   would warrant extending the model)
