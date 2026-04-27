# ADR 0003 · Conscience as a separate system-2 layer

| Status | Accepted (retroactive — codified 2026-04-26) |
|---|---|
| Deciders | sloan + Claude |
| Supersedes | — |

## Context

A pure dice resolver can produce *technically correct* events that
read as wrong: an SCP-173 vs D-class encounter where the D-class wins
on a high roll, an emergent "tea ceremony" between mortal enemies
because the cooldown allowed it.

The question: where does the "but would they actually do this?" check
live?

## Decision

A separate **conscience** layer (`living_world/agents/conscience.py`)
sits between the resolver's outcome and the event record. It can:

- **APPROVE** — pass through, no change
- **ADJUST** — accept the event but flip / soften the outcome
- **VETO** — drop the event entirely

Activation rules:
- Conscience only fires on events above a configurable importance
  threshold (otherwise the LLM call is wasteful)
- Conscience reads the same world snapshot the resolver did, plus the
  resolver's outcome, and asks the LLM to judge

Mental model: **system-1 is the dice resolver** (fast, deterministic,
sometimes wrong); **system-2 is the conscience** (slow, deliberate,
rarely fires). The simulator preserves both because real-world
behavior has both.

## Alternatives considered

### A · Bake "would they do this" into the resolver
- **Pro**: one fewer module
- **Con**: the resolver becomes a god class; the rule layer starts
  needing LLM access; rule + LLM coupling spreads
- **Verdict**: rejected. Keep the dice pure.

### B · Conscience as a phase that mutates events post-hoc
- **Pro**: cleaner pipeline shape
- **Con**: the consequences phase has already fired by then; rolling
  back stat changes is messy
- **Verdict**: rejected. Conscience must run BEFORE consequences.
  Today it lives inside `EventResolver.realize` (called by
  StorytellerPhase), which is the right point.

### C · No conscience layer, accept noisy events
- **Pro**: simplest
- **Con**: real users (and future testers) called out specific
  resolution outcomes as "that wouldn't happen". Filtering them in
  the chronicler post-hoc loses the unhappening too late.
- **Verdict**: rejected. The cost of a conscience LLM call on a
  ~5%/tick activation rate is acceptable.

## Consequences

**Positive**:
- High-importance events feel curated; low-importance events run free
- Activation can be tuned without touching the resolver
- Provides a future seat for "morality vector" experiments (different
  conscience prompts per pack: SCP foundation pragmatism vs Cthulhu
  cosmic indifference vs Liaozhai karmic justice)

**Negative**:
- Adds latency to high-importance events (single Tier-2 LLM call)
- Conscience verdicts can be wrong; we trust the LLM here without a
  ground-truth check. Mitigation: VETO is logged so we can review
  whether vetoes actually improved things

**Discipline**:
- Conscience NEVER advances the world state; it only accepts /
  adjusts / rejects what the resolver proposed
- Conscience NEVER reads or writes memory or beliefs directly. Those
  belong to the per-agent `self_update` and `reflector` modules
- Conscience output is tracked separately in `event.stat_changes` so
  the UI can show "⟡" annotation on adjusted events

## Validation criteria

Revisit if:
1. Conscience VETO rate exceeds 30% on any pack (suggests resolver
   is mis-calibrated; fix the resolver, not the conscience)
2. Conscience VETO rate stays below 1% for 30+ ticks (suggests it's
   not earning its cost; consider higher activation threshold or
   removing entirely)
3. Per-pack morality variation becomes a feature request — would be
   cleaner as different conscience prompts, possibly with a cross-
   pack "world-court" variant
