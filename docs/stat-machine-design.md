# Stat Machine & Consequence Engine Design

> How the world self-runs: tiered event resolution + two-layer consequence system.
> Last updated: 2026-04-16. Reflects implemented code.

---

## Core Principle

**Most ticks should cost nothing.** The vast majority of agents do predictable things (move, idle, minor interactions) handled by pure Python rules at zero LLM cost. Only when an event truly matters does the system escalate to LLM tiers.

```
         Cost                     Importance
           |
  Tier 3:  |  Ollama (large model or cloud)
           |  Dynamic dialogue, debate, conscious override
           |  importance >= 0.65
           |
  Tier 2:  |  Ollama (small local model)
           |  Narrative enhancement
           |  0.35 <= importance < 0.65
           |
  Tier 1:  |  Pure Python rules
           |  Template rendering, zero cost
           |  importance < 0.35, handles 95%+ of events
           |
```

---

## Event Resolution Pipeline

Each tick, events flow through this pipeline:

```
TileStoryteller.tick_daily()
    → EventProposal (what might happen)
        → EventResolver.realize()
            ├─ Find eligible participants (tag match in tile)
            ├─ D&D dice roll (stat + DC + d20)
            ├─ ConsciousnessLayer.consider() [if importance high enough]
            │    └─ APPROVE / ADJUST (override outcome) / VETO (skip event)
            ├─ Apply stat_changes + relationship_changes
            └─ Render template string
        → LegendEvent (what actually happened)
            → EnhancementRouter.enhance()
                ├─ Tier 1: keep template_rendering as-is
                ├─ Tier 2: generate enhanced_rendering via Ollama
                └─ Tier 3: generate spotlight_rendering + possible debate
            → ConsequenceEngine.apply()
                ├─ Stat layer (witness ripples)
                └─ Description layer (rare mutations)
```

---

## Importance Scoring

Lives in `statmachine/resolver.py` (merged from the former standalone `importance.py`).

```python
def score_event_importance(event, participants, *, base_importance=0.1):
    score = base_importance
    if event.event_kind in SPOTLIGHT_EVENT_KINDS and base_importance >= 0.5:
        score = max(score, 0.7)
    if sum(1 for p in participants if p.is_historical_figure) >= 2:
        score += 0.08
    if len(event.relationship_changes) >= 2:
        score += 0.05
    if tile_has_active_player:
        score += 0.35
    if event.outcome == "failure" and base_importance >= 0.5:
        score += 0.1
    return clamp(score, 0.0, 1.0)
```

Primary signal: template's `base_importance` field. Content authors control tier routing by setting this in their YAML event definitions.

Configurable thresholds in `settings.yaml`:
- `importance.tier2_threshold`: 0.35 (default)
- `importance.tier3_threshold`: 0.65 (default)

---

## Consequence Engine (`statmachine/consequences.py`)

The fundamental change layer. Called once per event within a single tick.

### Layer 1: Stat Ripples (every qualifying event)

When an event fires, nearby witnesses get numeric attribute changes:

| Event Kind | Witness Tags | Changes | Example Narrative |
|---|---|---|---|
| `173-snap-neck` | d-class, staff, researcher | fear +25, morale -15 | "{witness} saw what SCP-173 did..." |
| `682-breach` | d-class, staff, researcher, field-agent | fear +20, morale -10 | "{witness} was in the corridor when 682 broke through." |
| `descent` | investigator, academic, local | sanity -8 | "{witness} watched {victim} lose composure." |
| `cult-ritual` | investigator, local | sanity -5, arcane_knowledge +2 | "{witness} overheard fragments of the rite." |
| `yaksha-takes-soul` | scholar, mortal | courage -15 | "{witness} whispered a sutra they didn't know they remembered." |
| `999-uplift` | d-class, staff, researcher | morale +8, fear -5 | "{witness} saw SCP-999 and couldn't help a half-smile." |

Stat ripples also update relationships (sympathy toward victim, hatred toward attacker).

### Layer 2: Description Mutations (rare, conditional)

Guarded changes to an agent's core identity. Only fire when ALL conditions are met AND a probability roll succeeds:

| Mutation | Required Tags | Attribute Condition | Probability | Effects |
|---|---|---|---|---|
| d-class-becomes-traumatized | d-class | fear >= 85, morale <= 15 | 30% | +traumatized tag, new goal |
| investigator-goes-dark | investigator | sanity <= 10 | 20% | -investigator +corrupted tag |
| fox-spirit-achieves-form | fox-spirit | cultivation >= 85 | 15% | +human-form tag |
| scp-containment-escalation | anomaly | threat >= 90 | 10% | containment_class = Keter |
| scholar-gains-resolve | scholar | moral_resolve >= 95 | 20% | +unyielding tag |
| cultist-ascends | cultist | arcane_knowledge >= 90 | 8% | +ascended tag, life_stage = elder |

Each mutation has a 30-tick cooldown per agent to prevent rapid re-triggering.

### No Chain Depth Limit

Within a single tick, consequences are applied once per event. There is no recursive application. Changes persist on agents, and the next tick naturally picks up altered attributes. This IS the chain reaction -- it unfolds across ticks, not within one.

```
Tick N:   SCP-173 kills D-class → witnesses gain fear +25
Tick N+1: High-fear D-class triggers "flight" movement → agent flees tile
Tick N+2: Storyteller in new tile proposes different events for the refugee
```

---

## Consciousness Layer (`statmachine/conscious.py`)

An LLM overlay on the subconscious rule machine. Two components:

### ConsciousnessLayer

- Activates probabilistically based on template importance vs. threshold
- Sends event context + participant personas to Tier 2 LLM
- Returns JSON verdict: `{"verdict": "APPROVE"}`, `{"verdict": "ADJUST", "outcome": "failure", "reason": "..."}`, or `{"verdict": "VETO", "reason": "..."}`
- APPROVE: proceed as-is. ADJUST: override the dice-roll outcome. VETO: skip the event entirely.
- If LLM is unreachable or response unparseable, subconscious proceeds unchanged.

Settings: `llm.conscious_override_enabled` (default: true), `llm.conscious_override_threshold` (0.50), `llm.conscious_override_chance` (0.50).

### DebatePhase

- Triggered by EnhancementRouter when importance >= `llm.debate_threshold` (default: 0.75)
- Step 1: Orchestrator (Tier 3) picks 3-5 stakeholders from participants + tile co-residents + pack's historical figures
- Step 2: Each stakeholder generates a 30-60 word first-person reaction via worker (Tier 2)
- Step 3: Orchestrator synthesizes a 90-140 word narrative paragraph combining all voices
- Workers never communicate directly -- all go through orchestrator to avoid N-squared message explosion

---

## Tier 2/3 Provider: Ollama Only

The only real LLM backend is `OllamaClient`. Provider options are `"ollama"` or `"none"`:

- **Dev tier** (MacBook): `gemma3:4b` via Ollama, 4-bit ~3GB, handles both Tier 2 and Tier 3
- **Prod tier** (GPU server): Swap models in settings.yaml (e.g., Phi-4 14B for Tier 2, Gemma 4 31B for Tier 3)
- **Cloud fallback**: Not yet implemented; architecture supports any OpenAI-compatible endpoint

Mock clients have been removed entirely. If Ollama is unreachable, events degrade to Tier 1 templates.

---

## Budget Controls

```yaml
budget:
  tier2_tokens_per_day: 1_000_000
  tier3_tokens_per_day: 200_000
```

When daily limits are hit, the router auto-downgrades: Tier 3 requests fall to Tier 2, Tier 2 requests fall to Tier 1. The world never stops running.
