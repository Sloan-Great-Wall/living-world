# Contributing to living-world

This document helps a new developer get from zero to productive in an afternoon.

---

## 1. Get running

```bash
git clone <repo>
cd scp-playroom/living-world
./lw test                  # creates venv, installs deps, runs test suite
./lw                       # launches dashboard at http://localhost:8501
```

If `./lw` first-run is slow, it's installing deps once. After that it's instant.

### Optional — real LLMs
```bash
brew install ollama
ollama pull gemma3:4b
```
In dashboard Settings, switch `tier2_provider` from `mock` to `ollama` and save.

---

## 2. Read these first (in order)

| Doc | Why |
|---|---|
| [README.md](README.md) | Quick tour + commands |
| `../docs/architecture.md` | Full system design — layers, data flow |
| `../docs/stat-machine-design.md` | Tier 1/2/3 routing, importance scoring |
| `../docs/tech-glossary.md` | Terminology — what "storyteller" / "tier" / "persona" mean here |
| [tests/test_smoke.py](tests/test_smoke.py) | Read to understand engine usage |

---

## 3. Mental model

The engine tick loop looks like this — every virtual day:

```python
# living_world/tick_loop.py — TickEngine.step()
moves     = self.movement.tick()            # agents relocate
emergent  = self.interactions.tick()        # lethal encounters, bonding, flight
for tile, storyteller in self.storytellers.items():
    proposals = storyteller.tick_daily(t)   # candidate events for this tile
    for p in proposals:
        event = self.resolver.realize(p)    # dice-roll → outcome
        self.router.enhance(event)          # importance → tier 1/2/3
        self.world.record_event(event)
        self.hf_registry.observe_event(event)  # promote notable agents
```

Everything else is support: YAML loading, memory/persistence, UI, etc.

---

## 4. Where to add things

| Adding... | Edit... |
|---|---|
| A new character | `world_packs/<pack>/personas/<id>.yaml` |
| A new event type | `world_packs/<pack>/events/<file>.yaml` |
| A new location | `world_packs/<pack>/tiles/site_tiles.yaml` |
| A new worldview | New `world_packs/<mypack>/` directory |
| Physical-logic movement rule | `living_world/statmachine/movement.py` → `TAG_TILE_AFFINITY` |
| Lethal/companionship rule | `living_world/statmachine/interactions.py` |
| Importance scoring tweak | `living_world/statmachine/importance.py` |
| Tier-routing policy | `living_world/llm/router.py` |
| New LLM backend | `living_world/llm/*.py` (implement `LLMClient`) |
| Dashboard UI | `living_world/dashboard/app.py` (+ `map_view.py`, `codex.py`) |

---

## 5. Running tests

```bash
./lw test                  # all 17 tests
./lw test tests/test_smoke.py -v     # single file verbose
```

New tests go in `tests/test_<feature>.py`. Use pytest; no fixtures framework beyond vanilla. Keep tests under 100ms so the suite stays under 1s.

---

## 6. Design principles — don't break these

1. **Tier 1 must work without any LLM.** If you add a feature, the no-LLM path must still produce sensible legend events. Mock clients exist (`llm/mock.py`) — use them in tests.

2. **Packs are the unit of content.** Don't hardcode pack-specific logic in the engine. If you need special behavior per pack, it should be configurable in `pack.yaml`.

3. **Movement respects tag affinity.** Don't make agents teleport randomly — if a monk ends up in a bar, check `movement.py` affinity table for that tag.

4. **Death is sticky.** Once `life_stage == DECEASED`, the agent is out. Don't resurrect without an explicit event that narratively justifies it.

5. **UI is a view, not a source of truth.** All state lives in `World` / `st.session_state`. The Streamlit dashboard re-renders from that state each tick — it never stores state itself.

---

## 7. Common pitfalls

### Streamlit session_state vs URL params
`<a href="?agent=X">` navigation **breaks auto-play** — it forces a full page reload which resets `streamlit-autorefresh`'s timer. Use native widgets (`st.selectbox`, `st.button`) for selection instead. We learned this the hard way.

### YAML apostrophes
Single-quoted YAML strings need `''` (doubled) for literal apostrophes, NOT `\'`:
```yaml
# wrong
display_name: 'Huang Xiu\'er'
# right
display_name: 'Huang Xiu''er'
```
Or just use double quotes: `display_name: "Huang Xiu'er"`.

### Chinese tags
If you add agents with CJK tags (e.g. `tags: [liaozhai, 侠义]`), the tier-routing code and movement rules look up tags by ASCII name. CJK tags are invisible to the engine. Keep tags English only.

### Material Icons font
The dashboard loads Material Symbols via `@import url(...)`. If you globally override `font-family: Inter !important` on `*`, icons turn into their literal class name text. Always exclude `.material-icons`, `.material-symbols-*`, `[data-testid*="icon"]` from font resets.

### `st.components.v1.html` in iframe
Links inside `components.html` iframes can't navigate the parent page cleanly. Use `st.markdown(html, unsafe_allow_html=True)` for inline HTML that needs to interact with the page (e.g. SVG with hover tooltips). Drawback: no fixed height/scroll — manage via CSS `max-height: ...; overflow-y: auto`.

---

## 8. Roadmap (high level)

Current: **Stage A** (no-player auto-sim). Status: ✅ content + engine + UI working.

Coming next:
- **Stage B** — single-player text adventure: pick an agent, inject player prompts, agent responds via LLM
- **Stage C** — multi-player shared world
- **Stage D** — AR / mobile (see `docs/lbs-infrastructure.md`)

See `docs/mvp-roadmap.md` for the full plan.

---

## 9. Before opening a PR

- [ ] `./lw test` passes (17 tests)
- [ ] `./lw run --packs scp,liaozhai,cthulhu --days 30` runs without errors
- [ ] If you added YAML content, `python -c "import yaml; [yaml.safe_load(open(f)) for f in <new files>]"` succeeds
- [ ] Dashboard loads at least to the welcome page (`./lw dashboard` + browser)
- [ ] Documented any new `settings.yaml` keys
- [ ] Added test coverage for new logic (at least one happy-path test)

---

## 10. Getting help

- Open a GitHub issue with the `question` label
- For design discussions that might change architecture, read `docs/architecture.md` first so we're on the same page
