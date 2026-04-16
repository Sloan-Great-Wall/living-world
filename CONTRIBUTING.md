# Contributing to living-world

This document helps a new developer get from zero to productive in an afternoon.

---

## 1. Get running

```bash
git clone https://github.com/Sloan-Great-Wall/living-world.git
cd living-world
./lw test                  # creates venv, installs deps, runs 24 tests
./lw                       # launches dashboard at http://localhost:8501
```

If `./lw` first-run is slow, it is installing deps once. After that it is instant.

### Optional -- real LLMs

```bash
brew install ollama
ollama pull gemma3:4b
```

Ollama is the only LLM provider. In dashboard Settings (or `settings.yaml`), set `tier2_provider` and `tier3_provider` to `"ollama"`. Set to `"none"` for pure-rule mode. There are no mock clients.

---

## 2. Read these first (in order)

| Doc | Why |
|---|---|
| [README.md](README.md) | Quick tour + commands |
| [docs/architecture.md](docs/architecture.md) | Full system design, module layout, data flow |
| [docs/stat-machine-design.md](docs/stat-machine-design.md) | Consequence engine + tier routing |
| [docs/tech-glossary.md](docs/tech-glossary.md) | Terminology -- what "storyteller" / "tier" / "conscious" mean |
| [docs/flow-loops.md](docs/flow-loops.md) | Runtime flow diagrams |
| [tests/test_smoke.py](tests/test_smoke.py) | Read to understand engine usage patterns |

---

## 3. Mental model

The engine tick loop does this every virtual day:

```python
# living_world/tick_loop.py -- TickEngine.step()
moves     = self.movement.tick()              # agents relocate
emergent  = self.interactions.tick()          # lethal encounters, bonding, flight
for tile_id, st in self.storytellers.items():
    proposals = st.tick_daily(tick)            # candidate events for this tile
    for prop in proposals:
        event = self.resolver.realize(prop, template, tick, consciousness=self.consciousness)
        self._process_event(event, stats)     # enhance + record + persist + promote + memory + consequences
```

Key components wired in `factory.py`:
- `MovementPolicy` -- tag-affinity movement + optional LLM advisor
- `InteractionEngine` -- lethal encounters, companionship, flight
- `TileStoryteller` -- per-tile event scheduler (tension curve + cooldowns)
- `EventResolver` -- D&D dice roll + importance scoring + conscious override
- `ConsequenceEngine` -- stat ripples (every event) + description mutations (rare)
- `EnhancementRouter` -- importance-based tier 1/2/3 routing
- `ConsciousnessLayer` -- LLM verdict on rule-proposed events
- `DebatePhase` -- multi-voice LLM synthesis for top events

---

## 4. Where to add things

| Adding... | Edit... |
|---|---|
| A new character | `world_packs/<pack>/personas/<id>.yaml` |
| Chinese display name | `world_packs/<pack>/locale/zh/personas/<id>.yaml` |
| A new event type | `world_packs/<pack>/events/<file>.yaml` |
| A new location | `world_packs/<pack>/tiles/site_tiles.yaml` |
| A new worldview | New `world_packs/<mypack>/` directory (see README for template) |
| Movement rule | `living_world/statmachine/movement.py` -- `TAG_TILE_AFFINITY` |
| Lethal/companionship rule | `living_world/statmachine/interactions.py` |
| Consequence stat ripple | `living_world/statmachine/consequences.py` -- `STAT_RIPPLES` |
| Consequence mutation | `living_world/statmachine/consequences.py` -- `DESCRIPTION_MUTATIONS` |
| Importance scoring tweak | `living_world/statmachine/resolver.py` -- `score_event_importance()` |
| Tier-routing policy | `living_world/llm/router.py` |
| Dashboard UI | `living_world/dashboard/app.py` (+ `map_view.py`, `codex.py`) |
| Settings key | `living_world/config.py` -- add field to relevant Settings group |

---

## 5. Running tests

```bash
./lw test                           # all 24 tests
./lw test tests/test_smoke.py -v    # single file verbose
```

New tests go in `tests/test_<feature>.py`. Use pytest; no fixtures framework beyond vanilla. Keep tests under 100ms so the suite stays under 1s.

Test files:
- `test_smoke.py` -- engine integration (tick loop, event generation, tier routing)
- `test_consequences.py` -- stat ripples and description mutations
- `test_importance.py` -- importance scoring calibration
- `test_memory.py` -- episodic memory + reflection
- `test_i18n.py` -- translation layer
- `test_locale.py` -- locale overlay loading
- `test_persistence.py` -- repository protocol implementations

---

## 6. Design principles -- don't break these

1. **Tier 1 must work without any LLM.** If you add a feature, the no-LLM path must still produce sensible legend events. Set providers to `"none"` and verify.

2. **Packs are the unit of content.** Don't hardcode pack-specific logic in the engine. If you need special behavior per pack, make it configurable in `pack.yaml` or driven by tags/attributes.

3. **English is source of truth.** All YAML content and LLM prompts are English. Chinese and other languages are display overlays only (locale system). Never put Chinese in the primary YAML files.

4. **Consequences persist on agents, chains unfold across ticks.** No recursive consequence application within a tick. If you need a chain reaction, let the next tick pick it up naturally.

5. **Movement respects tag affinity.** Don't make agents teleport randomly -- check `movement.py` affinity table.

6. **Death is sticky.** Once `life_stage == DECEASED`, the agent is out. Don't resurrect without an explicit event.

7. **UI is a view, not state.** All state lives in `World` / `st.session_state`. The dashboard re-renders from state each tick.

---

## 7. Common pitfalls

### Streamlit session_state vs URL params
`<a href="?agent=X">` navigation breaks auto-play -- it forces a full page reload. Use native widgets (`st.selectbox`, `st.button`) for selection.

### YAML apostrophes
Single-quoted YAML strings need `''` (doubled) for literal apostrophes:
```yaml
# wrong
display_name: 'Huang Xiu\'er'
# right
display_name: 'Huang Xiu''er'
# also right
display_name: "Huang Xiu'er"
```

### Tags must be English
The engine (movement, interactions, consequences) looks up tags by ASCII name. CJK tags are invisible to the stat machine. Keep tags English only.

### Material Icons font
The dashboard loads Material Symbols via `@import url(...)`. If you globally override `font-family: Inter !important` on `*`, icons break. Always exclude `.material-icons`, `.material-symbols-*` from font resets.

### LLM provider = "ollama" or "none" only
There are no mock clients. If you need to test without Ollama, set providers to `"none"`. Tests use the no-LLM path by default.

---

## 8. Module structure notes

Several modules were recently flattened from subpackages to single files:
- `storyteller.py` (was `storyteller/`)
- `world_pack.py` (was `world_pack/`)
- `i18n.py` (was `i18n/`)
- `persistence.py` (was `persistence/` with 3 files)
- `factory.py` (was inside `dashboard/`)

And some modules were merged:
- `resolver.py` now includes importance scoring (was separate `importance.py`)
- `conscious.py` contains both ConsciousnessLayer and DebatePhase (were separate modules)

---

## 9. Roadmap (high level)

Current: **Stage A** (no-player auto-sim). Status: engine + content + UI working.

Coming:
- **Canvas world map** -- designed (see `docs/ui-redesign-spec.md`), not yet built
- **Stage B** -- single-player text adventure with DnD feel
- **Stage C** -- AR mobile with real-world LBS
- **Stage D** -- collection/bonding/PvP game layer

See `docs/mvp-roadmap.md` for the full plan.

---

## 10. Before opening a PR

- [ ] `./lw test` passes (24 tests)
- [ ] `./lw run --packs scp,liaozhai,cthulhu --days 30` runs without errors
- [ ] If you added YAML content, validate: `python -c "import yaml; [yaml.safe_load(open(f)) for f in <new files>]"`
- [ ] If you added Chinese locale content, put it in `locale/zh/` overlay, not the primary YAML
- [ ] Dashboard loads at least to the welcome page (`./lw dashboard` + browser)
- [ ] Documented any new `settings.yaml` keys in the relevant Settings class docstring
- [ ] Added test coverage for new logic (at least one happy-path test)

---

## 11. Getting help

- Open a GitHub issue at [github.com/Sloan-Great-Wall/living-world](https://github.com/Sloan-Great-Wall/living-world) with the `question` label
- For design discussions, read `docs/architecture.md` first so we share vocabulary
