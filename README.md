# living-world

Stage A MVP -- no-player, non-VR, auto-running virtual world simulator.

Three worldviews run side-by-side: **SCP Foundation**, **Cthulhu Mythos**, **Liaozhai**. Each is a self-contained pack of characters, events, and locations.

Agents move in continuous 2D space, interact, form relationships, accumulate consequences, and die. LLMs (local via Ollama) enhance narrative at key moments. A Streamlit dashboard provides a live map and floating chronicle log.

---

## Quick start

```bash
git clone https://github.com/Sloan-Great-Wall/living-world.git
cd living-world
./lw                   # creates venv, installs deps, launches dashboard
```

First run auto-installs dependencies. After that, `./lw` opens the dashboard at <http://localhost:8501>.

Other commands:
```bash
./lw dashboard         # default -- launches the Streamlit UI
./lw run               # CLI simulation (no UI)
./lw digest            # CLI -- print chronicle to terminal
./lw list-packs        # show available world packs
./lw test              # pytest suite (24 tests)
./lw install           # reinstall deps
```

### Using LLMs (optional)

```bash
brew install ollama
ollama pull gemma3:4b   # 3GB, runs on any 16GB MacBook
```

Then in the Dashboard Settings panel (or `settings.yaml`):
- `tier2_provider: ollama`
- `tier3_provider: ollama`

All LLM features default ON: dynamic dialogue, debate, conscious override, LLM-driven movement. If Ollama is unreachable, everything degrades gracefully to pure-rule Tier 1.

The only LLM provider options are `"ollama"` and `"none"` (pure rules). There are no mock clients.

---

## Repo layout

```
living-world/
├── lw                          # one-command launcher (bash)
├── pyproject.toml              # hatchling + deps (ui/db/llm extras)
├── settings.yaml               # user-editable runtime config
├── docker-compose.yml          # postgres + pgvector + redis (optional)
├── sql/init.sql                # persistence schema
│
├── world_packs/                # content -- 3 self-contained worlds
│   ├── scp/
│   │   ├── pack.yaml           # storyteller config
│   │   ├── personas/*.yaml     # 21 character cards (English)
│   │   ├── events/*.yaml       # 36 event templates
│   │   ├── tiles/*.yaml        # 12 locations
│   │   └── locale/zh/          # Chinese display overlay
│   ├── liaozhai/               # 20 personas / 36 events / 9 tiles + locale/zh/
│   └── cthulhu/                # 20 personas / 33 events / 9 tiles + locale/zh/
│
├── living_world/
│   ├── cli.py                  # Typer CLI (run / digest / list-packs / dashboard)
│   ├── config.py               # pydantic Settings (all tunables)
│   ├── tick_loop.py            # TickEngine -- main simulation loop
│   ├── factory.py              # bootstrap_world + make_engine (shared CLI + dashboard)
│   ├── storyteller.py          # RimWorld-style per-tile event scheduler
│   ├── world_pack.py           # YAML loader -> WorldPack runtime objects
│   ├── persistence.py          # Repository protocol + Memory/Postgres implementations
│   ├── i18n.py                 # Translation layer (Ollama or noop)
│   ├── locale.py               # Locale overlay reader (zh display content)
│   │
│   ├── core/                   # data models
│   │   ├── agent.py            # Agent (x/y coords, attributes, relationships, inventory)
│   │   ├── event.py            # EventProposal + LegendEvent + importance tiers
│   │   ├── tile.py             # Tile (x/y center, radius)
│   │   └── world.py            # World state (in-memory)
│   │
│   ├── statmachine/
│   │   ├── resolver.py         # D&D dice-roll resolver + importance scoring
│   │   ├── consequences.py     # Two-layer change engine (stat ripples + description mutations)
│   │   ├── conscious.py        # ConsciousnessLayer + DebatePhase
│   │   ├── movement.py         # Tag-aware agent movement
│   │   ├── interactions.py     # Lethal encounters, companionship, flight
│   │   └── historical_figures.py  # Promotion/demotion registry
│   │
│   ├── llm/                    # Tier 2/3 routing + Ollama client
│   │   ├── base.py             # LLMClient protocol
│   │   ├── ollama.py           # OllamaClient (only real LLM backend)
│   │   ├── router.py           # EnhancementRouter
│   │   ├── dialogue.py         # Dynamic dialogue generator (Tier 3)
│   │   └── move_advisor.py     # LLM movement advisor for historical figures
│   │
│   ├── memory/                 # Episodic memory + reflection
│   │   ├── embedding.py        # OllamaEmbedder
│   │   └── memory_store.py     # AgentMemoryStore
│   │
│   └── dashboard/              # Streamlit UI
│       ├── app.py              # main view
│       ├── map_view.py         # SVG world-map renderer
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

## Architecture at a glance

```
User -> Dashboard (Streamlit)
          |
          v
      TickEngine -- runs one virtual day per step()
          |
          |-- MovementPolicy        (tag-aware + optional LLM advisor)
          |-- InteractionEngine     (lethal encounters, companionship, flight)
          |-- TileStoryteller x N   (per-tile event candidates, tension curve)
          |-- EventResolver         (D&D DC roll, conscious override option)
          |-- ConsequenceEngine     (stat ripples + rare description mutations)
          |-- EnhancementRouter     (importance -> tier 1/2/3 routing)
          |     |-- Tier 1: rule-based templates (zero cost)
          |     |-- Tier 2: Ollama local (enhanced narrative)
          |     '-- Tier 3: Ollama (dynamic dialogue + debate)
          |-- HistoricalFigureReg.  (promote notable agents)
          '-- MemoryStore           (episodic memory + periodic reflection)
               |
               v
       Repository (in-memory | Postgres+pgvector)
               |
               v
       Dashboard re-renders: SVG map + Chronicle card + Agent card
```

See [docs/architecture.md](docs/architecture.md) for the full design.

---

## Current stats

| Metric | Value |
|---|---|
| Packs | 3 (SCP + Cthulhu + Liaozhai) |
| Personas | 61 (all English, with zh locale overlays) |
| Event templates | 105 |
| Tiles | 30 |
| Lethal encounter rules | 7 |
| Consequence stat ripples | 11 |
| Description mutations | 6 |
| Tests | 24/24 green |

---

## Extending -- add a new world pack

```bash
mkdir -p world_packs/mypack/{personas,events,tiles}
```

**`world_packs/mypack/pack.yaml`**
```yaml
pack_id: mypack
display_name: My World
narrative_style: "whatever tone you want"
storyteller:
  personality: balanced      # balanced | peaceful | chaotic
  tension_target: 0.5
  max_events_per_day: 3
```

**`world_packs/mypack/personas/alice.yaml`**
```yaml
agent_id: alice
display_name: Alice
persona_card: >
  A brief English description of who Alice is.
attributes: {strength: 50, wit: 80}
tags: [mypack, scholar]
current_tile: my-library
age: 25
alignment: neutral_good
current_goal: "read every book"
```

**`world_packs/mypack/tiles/site_tiles.yaml`**
```yaml
tiles:
  - tile_id: my-library
    display_name: The Library
    primary_pack: mypack
    tile_type: scholar-study
    description: "Endless shelves, endless dust."
    allowed_packs: [mypack]
    tension_bias: 0.3
```

**`world_packs/mypack/events/daily.yaml`**
```yaml
events:
  - event_kind: book-read
    description: An agent reads something important.
    trigger_conditions:
      min_participants: 1
      max_participants: 1
      required_tags: [scholar]
    dice_roll: {stat: wit, dc: 10}
    cooldown_days: 1
    base_importance: 0.1
    outcomes:
      success:
        stat_changes: [{target: any, attribute: wit, delta: 1}]
        template: "[$tile] ${a} finished a volume on obscure mathematics."
      failure:
        template: "[$tile] ${a} fell asleep on the book."
      neutral:
        template: "[$tile] ${a} skimmed a few pages."
```

Optional Chinese overlay at `world_packs/mypack/locale/zh/personas/alice.yaml`:
```yaml
agent_id: alice
display_name: "爱丽丝"
persona_card: "简短中文描述。"
```

Then:
```bash
./lw run --packs mypack --days 10
./lw dashboard   # select 'mypack' in sidebar checkboxes
```

---

## Design documents

| Doc | Contents |
|---|---|
| [docs/product-direction.md](docs/product-direction.md) | Why this product, Direction A rationale |
| [docs/architecture.md](docs/architecture.md) | Full system architecture |
| [docs/stat-machine-design.md](docs/stat-machine-design.md) | Consequence engine + tier routing |
| [docs/tech-glossary.md](docs/tech-glossary.md) | Terminology reference |
| [docs/flow-loops.md](docs/flow-loops.md) | Runtime flow diagrams |
| [docs/mvp-roadmap.md](docs/mvp-roadmap.md) | Stage A/B/C/D roadmap |
| [docs/next-steps.md](docs/next-steps.md) | Remaining Stage A work |
| [docs/ui-redesign-spec.md](docs/ui-redesign-spec.md) | Canvas map spec (planned, not built) |

---

## Key design principles

1. **LLM is optional, not required.** Tier 1 (pure rules) runs the world indefinitely with zero tokens.
2. **World content is data, not code.** YAML drives everything -- add a pack without touching Python.
3. **English is source of truth.** Chinese (and future locales) are display overlays, not primary content.
4. **Consequences persist, chains unfold across ticks.** No recursion depth limit. Changes on agents naturally trigger reactions in subsequent ticks.
5. **Death is real.** Deceased agents persist in history but are removed from active simulation.
6. **UI is a view, not a source of truth.** All state lives in `World`; the dashboard re-renders from it.

---

## Known limitations

- SVG map -- no zoom/pan, no animation. Canvas replacement is designed but not built.
- Streamlit URL navigation breaks auto-play timer. Use native widgets for agent selection.
- `backdrop-filter` (glassmorphism) is Chrome/Safari only; Firefox falls back to opaque panels.
- Postgres persistence works but is not default-enabled in dashboard workflow.

---

## License

MIT for the code. Content packs follow their source licenses:
- SCP Foundation: CC BY-SA 3.0 (attribution required)
- Cthulhu Mythos (Lovecraft): public domain
- Liaozhai Zhiyi: public domain
