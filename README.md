# living-world

Stage A MVP — no-player, non-VR, auto-running virtual world simulator.
Three worldviews run side-by-side: **SCP Foundation**, **Cthulhu Mythos**, **Liaozhai (聊斋志异)** — each a self-contained pack of characters, events, and locations.

Agents move between rooms, interact, form relationships, and die. LLMs (local via Ollama, or cloud) enhance narrative at key moments. The whole thing has a Streamlit dashboard with a live map and floating Chronicle log.

---

## Quick start

```bash
cd living-world
./lw                   # creates venv, installs deps, launches dashboard
```

First run auto-installs dependencies. After that, `./lw` just opens the dashboard at <http://localhost:8501>.

Other commands:
```bash
./lw dashboard         # default — launches the Streamlit UI
./lw run               # CLI simulation (no UI)
./lw digest            # CLI — print chronicle to terminal
./lw test              # pytest suite (17 tests)
./lw install           # reinstall deps
```

### Using real LLMs (optional)

```bash
brew install ollama
ollama pull gemma3:4b   # 3GB, runs on any 16GB MacBook
```
Then in the Dashboard → Settings:
- `tier2_provider: ollama`
- `tier3_provider: ollama`

Save & reload. Chronicle narratives will now be LLM-enhanced instead of template strings.

---

## Repo layout

```
living-world/
├── lw                         # one-command launcher (bash)
├── pyproject.toml             # hatchling + deps (ui/db/llm extras)
├── settings.yaml              # user-editable runtime config
├── docker-compose.yml         # postgres + pgvector + redis (optional)
├── sql/init.sql               # persistence schema
├── .streamlit/config.toml     # Streamlit theme + minimal toolbar
│
├── world_packs/               # content — 3 self-contained worlds
│   ├── scp/
│   │   ├── pack.yaml          # storyteller config
│   │   ├── personas/*.yaml    # 21 character cards
│   │   ├── events/*.yaml      # 36 event templates
│   │   └── tiles/*.yaml       # 12 locations
│   ├── liaozhai/              # 20 personas / 36 events / 9 tiles
│   └── cthulhu/               # 20 personas / 33 events / 9 tiles
│
├── living_world/
│   ├── cli.py                 # Typer CLI (run/digest/dashboard)
│   ├── config.py              # pydantic Settings (LLM, memory, routing...)
│   ├── tick_loop.py           # main simulation loop
│   │
│   ├── core/                  # data models
│   │   ├── agent.py           # Agent pydantic schema
│   │   ├── event.py           # LegendEvent + importance tiers
│   │   ├── tile.py            # Tile (location)
│   │   └── world.py           # World state (in-memory)
│   │
│   ├── world_pack/            # plugin loader — reads YAML into WorldPack
│   ├── storyteller/           # RimWorld-style per-tile event scheduler
│   ├── statmachine/
│   │   ├── resolver.py        # D&D dice-roll event resolver
│   │   ├── importance.py      # importance scoring → tier routing
│   │   ├── movement.py        # tag-aware agent movement between tiles
│   │   ├── historical_figures.py  # promotion/demotion registry
│   │   └── interactions.py    # lethal encounters, companionship, flight
│   │
│   ├── memory/                # pgvector-backed episodic memory + reflection
│   ├── persistence/           # Postgres/in-memory repository pattern
│   ├── llm/                   # Tier 2/3 routing + Ollama/mock clients
│   ├── i18n/                  # output translation layer (en → zh via Gemma)
│   │
│   └── dashboard/             # Streamlit UI
│       ├── app.py             # main view
│       ├── build.py           # engine/repo/memory factories
│       ├── map_view.py        # SVG world-map renderer
│       └── codex.py           # Story Library view (personas/stories/tiles)
│
└── tests/                     # pytest (17 tests, all green)
    ├── test_smoke.py
    ├── test_importance.py
    ├── test_memory.py
    ├── test_i18n.py
    └── test_persistence.py
```

---

## Architecture at a glance

```
User → Dashboard (Streamlit)
          │
          ▼
      TickEngine ─── runs one virtual day
          │
          ├─ MovementPolicy        (tag-aware: monks stay at temples, D-class flee SCPs)
          ├─ InteractionEngine     (emergent: SCP-173 unobserved + D-class in room = death)
          ├─ TileStoryteller × N   (per-tile event candidates w/ tension curve)
          ├─ EventResolver         (D&D DC roll → outcome → stat/relationship changes)
          ├─ HistoricalFigureReg.  (promote notable agents to finer simulation)
          ├─ EnhancementRouter     (importance score → Tier 1/2/3 routing)
          │     ├─ Tier 1: rule-based templates (zero cost)
          │     ├─ Tier 2: Phi-4 / Gemma 3 / Ollama (mid cost, local)
          │     └─ Tier 3: DeepSeek V3 / Gemma 4 / cloud (high quality)
          └─ MemoryStore           (pgvector — raw events + weekly reflections)
               │
               ▼
       Repository (in-memory | Postgres+pgvector)
               │
               ▼
       Dashboard re-renders: SVG map + Chronicle card + Agent card
```

**See [architecture.md](../docs/architecture.md) for the full design.**

---

## Current stats (2026-04-15)

| Metric | Value |
|---|---|
| Packs | 3 (SCP + Cthulhu + Liaozhai) |
| Personas | 61 (all English) |
| Event templates | 105 |
| Tiles | 30 |
| Emergent lethal rules | 7 |
| Tests | 17/17 green |
| 60-day mock run | ~570 events, ~9 deaths, ~20 HF promotions |

---

## Extending — add a new world pack

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

Then:
```bash
./lw run --packs mypack --days 10
./lw dashboard   # select 'mypack' in sidebar checkboxes
```

---

## Extending — add movement logic to a new tag

Edit `living_world/statmachine/movement.py`:

```python
TAG_TILE_AFFINITY = {
    # existing...
    "my-new-role": {"my-library": 3.0, "outside": 0.3},
}
```

Higher weight = more likely to move to that tile type.
Weight < 0.05 = effectively forbidden (physical logic).

---

## Extending — add a lethal encounter rule

Edit `living_world/statmachine/interactions.py`:

```python
LETHAL_SCP_RULES = {
    # existing SCP-173, 049, 682...
    "SCP-MY-ENTITY": {
        "victim_tags": {"d-class", "researcher"},
        "unless_any_tag": {"field-agent"},   # MTF protects
        "kind": "my-entity-incident",
        "template": "[$tile] ${victim} was caught off-guard by SCP-MY-ENTITY. ...",
        "kills": True,
        "lethal_chance": 0.5,
    },
}
```

The interaction engine scans every tile each tick; if a predator and victim are co-located and the rule matches, it rolls and may kill.

---

## Design documents

Higher-level design lives in the repo root's `docs/` folder (gitignored for privacy):

| Doc | Contents |
|---|---|
| `docs/product-direction.md` | Stage A/B/C/D roadmap; why three worlds |
| `docs/architecture.md` | Layer-by-layer system design |
| `docs/stat-machine-design.md` | Tier 1/2/3 routing & importance scoring |
| `docs/tech-glossary.md` | Terminology reference |
| `docs/next-steps.md` | Non-blocking work streams |

---

## Key design principles

1. **LLM is optional, not required.** Tier 1 (pure rules) can run the world indefinitely with zero tokens.
2. **World content is data, not code.** YAML drives everything — add a pack without touching Python.
3. **Movement follows physical logic.** Tag-to-tile affinity tables enforce rules like "monks stay in temples, D-class cannot enter restricted zones."
4. **Death is real.** Deceased agents persist in history but are removed from active simulation.
5. **State is cheap, UI is presentation.** Session state drives everything; the Streamlit dashboard is a thin view layer.

---

## Known limitations

- Map agent clicks don't work — Streamlit URL navigation breaks auto-play. Use the `Inspect agent` dropdown in the Chronicle card instead.
- `backdrop-filter` (glassmorphism) is Chrome/Safari only; Firefox falls back to opaque panels.
- No persistent world state across dashboard restarts yet (Postgres schema exists, repository works, but not hooked into dashboard workflow by default).

---

## License

MIT for the code. Content packs follow their source licenses:
- SCP Foundation → CC BY-SA 3.0 (attribution required)
- Cthulhu Mythos (Lovecraft) → public domain
- Liaozhai Zhiyi → public domain
