# System Architecture Overview

> As of 2026-04-16. Reflects the implemented codebase, not aspirational plans.

---

## 0. One-liner

**A stat-machine-driven, LLM-enhanced, world-pack-organized living world simulator where agents move in continuous 2D space, accumulate consequences across ticks, and optionally gain LLM consciousness at high-importance moments.**

---

## 1. Design Principles

### Principle 1: LLM is a layer, not the foundation
The world runs on pure Python rules (Tier 1). LLM (Tier 2/3 via Ollama) makes events more vivid but is never required. Set all providers to `"none"` and the world still self-runs indefinitely.

### Principle 2: Stateless LLM + Scoped Memory
Agent personality persists through vector-DB-backed episodic memory retrieved at call time. The LLM itself is always a stateless function call.

### Principle 3: Tiered cost control
Importance scoring routes 95%+ of events to Tier 1 (zero cost). Only high-importance events reach Tier 2 (Ollama local) or Tier 3 (Ollama or future cloud API). Daily token budgets auto-downgrade when exceeded.

### Principle 4: World Pack decoupling
Content is data, not code. Each world pack is a self-contained directory of YAML files (personas, events, tiles, storyteller config). Add a pack without touching Python.

### Principle 5: English source of truth, locale overlays for display
All content and LLM prompts are English. Chinese (or other language) display is handled by optional locale overlays (`world_packs/*/locale/zh/`) and a runtime translation layer (`i18n.py`).

---

## 2. Module Layout

```
living-world/
├── lw                          # one-command launcher (bash)
├── pyproject.toml              # hatchling build + deps
├── settings.yaml               # user-editable runtime config
├── docker-compose.yml          # postgres + pgvector + redis (optional)
├── sql/init.sql                # persistence schema
│
├── world_packs/                # content — 3 self-contained worlds
│   ├── scp/                    # 21 personas, 36 events, 12 tiles
│   │   ├── pack.yaml
│   │   ├── personas/*.yaml
│   │   ├── events/*.yaml
│   │   ├── tiles/*.yaml
│   │   └── locale/zh/          # Chinese overlay (display_name, templates)
│   ├── liaozhai/               # 20 personas, 36 events, 9 tiles + locale/zh/
│   └── cthulhu/                # 20 personas, 33 events, 9 tiles + locale/zh/
│
├── living_world/
│   ├── cli.py                  # Typer CLI (run / digest / list-packs / dashboard)
│   ├── config.py               # pydantic Settings — all tunables
│   ├── tick_loop.py            # TickEngine — main simulation loop
│   ├── factory.py              # bootstrap_world + make_engine (shared by CLI + dashboard)
│   ├── storyteller.py          # RimWorld-style per-tile event scheduler
│   ├── world_pack.py           # YAML loader → WorldPack runtime objects
│   ├── persistence.py          # Repository protocol + MemoryRepository + PostgresRepository
│   ├── i18n.py                 # Translation layer (OllamaTranslator / NoopTranslator)
│   ├── locale.py               # LocaleOverlay + LocaleRegistry (zh overlay reader)
│   │
│   ├── core/                   # data models (pydantic)
│   │   ├── agent.py            # Agent (x/y coords, attributes, relationships, inventory)
│   │   ├── event.py            # EventProposal + LegendEvent + importance enums
│   │   ├── tile.py             # Tile (x/y center, radius, allowed_packs)
│   │   └── world.py            # World (in-memory state: agents + tiles + event log)
│   │
│   ├── statmachine/
│   │   ├── resolver.py         # D&D dice-roll resolver + importance scoring (merged)
│   │   ├── consequences.py     # Two-layer change engine (stat ripples + description mutations)
│   │   ├── conscious.py        # ConsciousnessLayer + DebatePhase (merged)
│   │   ├── movement.py         # Tag-aware agent movement between tiles
│   │   ├── interactions.py     # Lethal encounters, companionship, flight
│   │   └── historical_figures.py  # Promotion/demotion registry
│   │
│   ├── llm/
│   │   ├── base.py             # LLMClient protocol
│   │   ├── ollama.py           # OllamaClient (only real LLM backend)
│   │   ├── router.py           # EnhancementRouter (importance → tier routing)
│   │   ├── dialogue.py         # DialogueGenerator (Tier 3 dynamic narrative)
│   │   └── move_advisor.py     # LLMMoveAdvisor (historical figures decide via LLM)
│   │
│   ├── memory/
│   │   ├── embedding.py        # OllamaEmbedder
│   │   └── memory_store.py     # AgentMemoryStore (episodic + reflection)
│   │
│   └── dashboard/              # Streamlit UI
│       ├── app.py              # main view
│       ├── map_view.py         # SVG world-map renderer (Canvas planned, not built)
│       ├── codex.py            # Story Library view
│       └── styles.css
│
└── tests/                      # 24 tests, all green
    ├── test_smoke.py
    ├── test_consequences.py
    ├── test_importance.py
    ├── test_memory.py
    ├── test_i18n.py
    ├── test_locale.py
    └── test_persistence.py
```

---

## 3. Data Flow: One Tick

```
TickEngine.step()
    │
    ├─ MovementPolicy.tick()
    │   (tag-aware + optional LLM advisor for historical figures)
    │
    ├─ InteractionEngine.tick()
    │   (lethal encounters, companionship, flight → LegendEvents)
    │   └─ each event → _process_event()
    │
    ├─ For each tile: TileStoryteller.tick_daily()
    │   → EventProposals
    │   → EventResolver.realize()
    │       ├─ Subconscious: D&D dice roll
    │       └─ Conscious: LLM may APPROVE / ADJUST / VETO (if importance high enough)
    │   → LegendEvent
    │   └─ _process_event()
    │
    ├─ _process_event() pipeline:
    │   ├─ EnhancementRouter.enhance()     (importance → tier 1/2/3 routing)
    │   ├─ World.record_event()
    │   ├─ Repository.append_event()       (persistence)
    │   ├─ HistoricalFigureRegistry.observe_event()  (promote notable agents)
    │   ├─ AgentMemoryStore.remember()     (episodic memory)
    │   └─ ConsequenceEngine.apply()       (two-layer: stat ripples + description mutations)
    │       └─ reaction events also routed + recorded
    │
    ├─ Periodic: demote inactive HFs (every 7 ticks)
    ├─ Periodic: reflect (compress memories for HFs, every N ticks)
    └─ Periodic: snapshot world state to repository (every N ticks)
```

---

## 4. Key Subsystems

### 4.1 Consequence Engine (NEW — `statmachine/consequences.py`)

The rewritten consequence system has **two layers**:

| Layer | Frequency | What changes | Example |
|---|---|---|---|
| **Stat layer** | Every qualifying event | Numeric attributes, relationships, inventory | D-class witnesses SCP-173 kill → fear +25, morale -15 |
| **Description layer** | Rare, conditional | Tags, persona_card, life_stage, goals | Investigator sanity <= 10 → 20% chance: loses "investigator" tag, gains "corrupted" |

**No chain depth limit.** Within a single tick, consequences are applied once per event. The next tick's movement, storyteller, and interactions naturally react to changed attributes. The chain unfolds across ticks, not recursively within one.

### 4.2 Consciousness + Debate (merged — `statmachine/conscious.py`)

Two LLM-driven overlays on top of the rule machine:

- **ConsciousnessLayer**: Per-event verdict (APPROVE / ADJUST / VETO). Activates probabilistically based on importance. Can override a dice-roll outcome.
- **DebatePhase**: For top-importance events, an orchestrator LLM picks 3-5 stakeholders, each generates a first-person reaction via a worker LLM, then the orchestrator synthesizes a final narrative. Triggered by EnhancementRouter when importance >= debate_threshold.

### 4.3 Language Isolation (`locale.py` + `i18n.py`)

```
English YAML (source of truth)          Chinese overlay (display only)
  world_packs/scp/personas/049.yaml       world_packs/scp/locale/zh/personas/049.yaml
  world_packs/scp/events/daily.yaml       world_packs/scp/locale/zh/events/daily.yaml

LLM pipeline: always English
Display pipeline: settings.yaml display.locale → "en" or "zh"
  "en" → show English as-is
  "zh" → LocaleOverlay for static content + OllamaTranslator for generated text
```

### 4.4 Continuous-Space Map

Both `Agent` and `Tile` have `x`/`y` float coordinates. Tiles define a center + radius. Agents are placed within tiles. The `world_pack.py` loader auto-layouts tiles in a grid if no coordinates are set, and offsets pack tile groups vertically when multiple packs load.

Currently rendered as SVG in the dashboard. A Canvas-based world map component is designed ([ui-redesign-spec.md](ui-redesign-spec.md)) but **not yet implemented**.

### 4.5 Importance Scoring + Tier Routing

Importance scoring lives in `resolver.py` (merged from former `importance.py`). The `EnhancementRouter` in `llm/router.py` uses thresholds to route events:

- **Tier 1** (importance < 0.35): Template rendering only. Zero LLM cost.
- **Tier 2** (0.35 <= importance < 0.65): Ollama-enhanced narrative.
- **Tier 3** (importance >= 0.65): Dynamic dialogue + possible debate phase.

Thresholds are configurable in `settings.yaml` under `importance`.

---

## 5. LLM Backend

**Only two provider options**: `"ollama"` or `"none"`.

- `"ollama"` — connects to a local Ollama instance. Default model: `gemma3:4b`.
- `"none"` — no LLM calls. World runs on pure rules (Tier 1 only).

Mock clients have been removed entirely. All LLM features (dynamic_dialogue, debate, conscious_override, llm_movement) default to ON in settings.yaml but gracefully degrade if Ollama is unreachable.

---

## 6. Persistence

`persistence.py` provides a `Repository` protocol with two implementations:

- **MemoryRepository** (default): In-memory, no external deps. For tests and single-session runs.
- **PostgresRepository**: psycopg3-backed, requires `pip install -e '.[db]'`. Full CRUD for agents, tiles, events, relationships.

---

## 7. Why This Architecture Works

1. **Cost**: Tier 1 handles 95%+ of events at zero cost. Token budgets cap daily spend.
2. **Extensibility**: World packs are pure YAML. Add a new IP without touching Python.
3. **Resilience**: If LLM is down, the world keeps running on rules. Consequences persist on agents, next tick reacts naturally.
4. **Simplicity**: Flattened module structure (no deep subpackage nesting). `storyteller.py`, `world_pack.py`, `i18n.py`, `persistence.py`, `factory.py` are all top-level modules.
