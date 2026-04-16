# Core Flow Loops

> Runtime flow diagrams. Reflects the implemented `tick_loop.py` and supporting modules.
> Last updated: 2026-04-16

---

## Flow 1: TickEngine.step() — One Virtual Day

The main simulation loop. Each call to `step()` advances the world by one tick (one virtual day).

```
TickEngine.step()
    │
    ├─── Movement Phase ─────────────────────────────────────────────
    │    MovementPolicy.tick()
    │      ├─ For each living agent: evaluate tag-affinity weights per tile
    │      ├─ Optional: LLMMoveAdvisor (historical figures only, 30% chance)
    │      │    └─ Tier 2 LLM suggests destination given persona + recent events
    │      └─ Update agent.current_tile, tile.resident_agents
    │
    ├─── Interaction Phase ──────────────────────────────────────────
    │    InteractionEngine.tick()
    │      ├─ Scan all tiles for predator-victim co-location
    │      ├─ Apply lethal rules (SCP-173, 049, 682, 106, 096, yaksha, ...)
    │      ├─ Apply companionship + flight rules
    │      └─ Each emergent event → _process_event()
    │
    ├─── Storyteller Phase ──────────────────────────────────────────
    │    For each tile:
    │      TileStoryteller.tick_daily(tick)
    │        ├─ Check tension curve vs. target (breathing room if too high)
    │        ├─ Personality factor (peaceful=0.35, balanced=0.7, chaotic=1.1)
    │        ├─ Weighted random pick from event pool, respecting cooldowns
    │        └─ Return 0-N EventProposals
    │      │
    │      For each proposal:
    │        EventResolver.realize(proposal, template, tick, consciousness)
    │          ├─ Find eligible participants in tile (tag filter)
    │          ├─ D&D dice roll: d20 + stat bonus + mod vs. DC
    │          ├─ ConsciousnessLayer.consider() [optional, importance-gated]
    │          │    └─ APPROVE → proceed | ADJUST → override outcome | VETO → skip
    │          ├─ Apply stat_changes + relationship_changes to participants
    │          ├─ Render template string with participant names
    │          └─ Compute importance score
    │        │
    │        → LegendEvent → _process_event()
    │
    ├─── _process_event() Pipeline ──────────────────────────────────
    │    EnhancementRouter.enhance(event)
    │      ├─ importance < 0.35 → Tier 1 (keep template)
    │      ├─ 0.35 <= imp < 0.65 → Tier 2 (Ollama enhanced_rendering)
    │      └─ imp >= 0.65 → Tier 3 (dynamic dialogue + debate if >= 0.75)
    │    │
    │    World.record_event(event)          — append to event log
    │    Repository.append_event(event)     — persist if backend configured
    │    HistoricalFigureRegistry.observe_event(event)  — promote notable agents
    │    AgentMemoryStore.remember(event)   — episodic memory for participants
    │    │
    │    ConsequenceEngine.apply(event)
    │      ├─ Stat layer: ripple attribute changes to witnesses
    │      └─ Description layer: check for rare identity mutations
    │      → reaction LegendEvents (also routed, recorded, and promoted)
    │
    ├─── Periodic Tasks ─────────────────────────────────────────────
    │    Every 7 ticks: demote inactive historical figures
    │    Every N ticks: reflect (compress memories for HFs)
    │    Every N ticks: snapshot full world state to repository
    │
    └─── Return TickStats
```

---

## Flow 2: Consequence Chain (Across Ticks)

Consequences do NOT recurse within a tick. They unfold naturally across ticks:

```
Tick 1:  SCP-682 breach event
           │
           ├─ Stat layer: witnesses gain fear +20, morale -10
           ├─ Description layer: D-class with fear >=85 → 30% chance "traumatized" tag
           └─ Witness-reaction events recorded
                │
Tick 2:  MovementPolicy sees high-fear agents
           │
           ├─ Traumatized D-class flees tile (flight behavior in interactions.py)
           ├─ Storyteller in original tile: tension high → fewer new events (breathing room)
           └─ Storyteller in destination tile: newcomer may trigger "encounter" events
                │
Tick 3:  New events fire with the refugee as participant
           │
           └─ Consequences ripple again...
```

This natural unfolding produces emergent narrative arcs without any artificial recursion depth management.

---

## Flow 3: Enhancement Router Decision Tree

```
LegendEvent arrives at EnhancementRouter
    │
    ├─ Check daily budget
    │   ├─ Tier 3 budget exhausted? → force downgrade to Tier 2
    │   └─ Tier 2 budget exhausted? → force downgrade to Tier 1
    │
    ├─ importance < tier2_threshold (0.35)?
    │   └─ Tier 1: template_rendering stays as-is
    │
    ├─ importance < tier3_threshold (0.65)?
    │   └─ Tier 2: Ollama generates enhanced_rendering
    │       └─ On failure: fall back to Tier 1 template
    │
    └─ importance >= tier3_threshold?
        ├─ Tier 3: dynamic dialogue (if enabled)
        │   └─ On failure: fall back to enhanced_rendering or template
        ├─ importance >= debate_threshold (0.75)?
        │   └─ DebatePhase.run(): multi-voice synthesis
        │       └─ On failure: fall back to previous rendering
        └─ Write spotlight_rendering
```

---

## Flow 4: Debate Phase (Multi-Agent LLM Round)

```
High-importance event (>= debate_threshold)
    │
    ▼
Step 1: Pick stakeholders
    ├─ Start with event participants
    ├─ Add tile co-residents + pack historical figures as candidates
    ├─ Orchestrator (Tier 3) LLM selects 3-5 from candidate roster
    └─ Fallback: top up with historical figures from same pack
    │
    ▼
Step 2: Generate takes (concurrent per stakeholder)
    ├─ Each stakeholder's persona + goal + event context → Worker (Tier 2) LLM
    └─ Output: 30-60 word first-person reaction per stakeholder
    │
    ▼
Step 3: Synthesize
    ├─ All voices + event context → Orchestrator (Tier 3) LLM
    └─ Output: 90-140 word literary narrative paragraph
    │
    ▼
spotlight_rendering set on the event
```

Workers never communicate directly. All routing goes through the orchestrator to avoid N-squared message complexity.

---

## Code Mapping

| Flow | Primary Module | Key Function |
|---|---|---|
| Main tick | `tick_loop.py` | `TickEngine.step()` |
| Movement | `statmachine/movement.py` | `MovementPolicy.tick()` |
| Interactions | `statmachine/interactions.py` | `InteractionEngine.tick()` |
| Storytelling | `storyteller.py` | `TileStoryteller.tick_daily()` |
| Resolution | `statmachine/resolver.py` | `EventResolver.realize()` |
| Importance | `statmachine/resolver.py` | `score_event_importance()` |
| Tier routing | `llm/router.py` | `EnhancementRouter.enhance()` |
| Consequences | `statmachine/consequences.py` | `ConsequenceEngine.apply()` |
| Consciousness | `statmachine/conscious.py` | `ConsciousnessLayer.consider()` |
| Debate | `statmachine/conscious.py` | `DebatePhase.run()` |
| Memory | `memory/memory_store.py` | `AgentMemoryStore.remember()` / `.reflect()` |
| Bootstrap | `factory.py` | `bootstrap_world()` / `make_engine()` |
