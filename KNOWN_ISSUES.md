# Known Issues & Planned Tasks

Tracks **open** bugs and **active** backlog. Resolved items + design
retrospectives live in [`docs/HISTORY.md`](docs/HISTORY.md).

---

## 🐞 Open issues

### #21 — Production app packaging (PyInstaller bundle hang)
**Status**: infrastructure in place; runtime bundle hangs silently.

**What's done** (2026-04-26):
- `scripts/lw_sidecar_entry.py` standalone entry that imports
  `living_world.web.server.app` and runs uvicorn against it
- `scripts/build_sidecar.py` invokes PyInstaller with the right
  `--collect-submodules` + hidden-import set; outputs to
  `dashboard-tauri/src-tauri/binaries/lw-sidecar-<triple>{.exe}`
- `make build-sidecar` / `make build-app` Makefile targets
- `tauri.conf.json` declares `bundle.externalBin` pointing at the
  binary
- Rust `resolve_sidecar_command()` prefers the bundled binary in
  production, falls back to `.venv/bin/python` in dev

**Blocker**: the bundled binary spawns a process that consumes ~24 MB
RAM and stays alive, but never executes the entry script. NO output
even with `PYTHONUNBUFFERED=1` / `PYTHONVERBOSE=1` / `PYTHONFAULTHANDLER=1`
/ explicit prints / file-based diagnostics. Reproduced with a minimal
FastAPI+uvicorn standalone bundle, so it's NOT specific to our app.

Suspected cause: interaction between PyInstaller 6.20 + Python 3.13.5
+ uvicorn 0.34+ + macOS aarch64. Minimal hello-world bundle works;
adding `uvicorn.run(app, ...)` reliably hangs. A trivial bundle that
imports uvicorn + FastAPI but doesn't call `run()` works fine.

**Investigation paths (not yet tried)**:
1. Pin Python to 3.12 in the sidecar build (separate venv)
2. Try `uvicorn.Config(...)` + `uvicorn.Server(...).serve()` instead
   of the higher-level `uvicorn.run`
3. Try Python 3.14 or 3.13.0 vs 3.13.5
4. Check uvicorn issue tracker for "PyInstaller hangs" reports
5. Bypass uvicorn entirely — use hypercorn or call asgi.run on
   Starlette directly

**Also pending** for full production:
- Code signing / notarization (macOS Apple Developer cert)
- POSIX process group / Windows job object so sidecar is reaped if
  Tauri is SIGKILL'd (today: orphans, holds the port)
- Ollama detection: friendly first-run prompt if `ollama` not on PATH
- Cross-platform: Linux + Windows builds (PyInstaller doesn't cross-
  compile cleanly; need each host)

**Workaround for now**: `npm run tauri dev` works perfectly via the
`.venv` fallback — that path landed in commit 92768bd (Phase 3.5)
and is unaffected. The dev experience IS one-click; production
distribution waits.

**Effort estimate**: half a day to diagnose the uvicorn+PyInstaller
hang once we pick a paths from the list above; 1-2 days to ship a
notarized macOS .app on top of a working bundle.

---

## 🚀 Feature backlog (ranked by ROI)

### #7 — Cross-pack bridge (shared tiles + migration events)
**Status**: foundation done (loaded packs share a `liminal` tile when
≥2 packs are loaded). Not yet exercised — no migration event templates
authored.

**Remaining**: 1-2 generic event templates per pack
(`<pack>:portal-anomaly`, `<pack>:dream-passage`) so agents can cross
packs idiomatically.

**Effort**: 1-2 days for the templates + a couple of cross-pack
narrative samples.

---

### #8 — Player prompt injection
**Status**: not started. UX decision (2026-04-22): build BOTH UIs.
- **Default**: a single natural-language textbox. The LLM converts
  intent ("what if the cult ritual succeeds?") into an
  `EventProposal`. Conscience still gets to APPROVE/ADJUST/VETO.
  Reuses the existing `emergent.propose` prompt machinery (~80%
  overlap).
- **Advanced**: an expandable form for power users running
  reproducible experiments.

**Implementation**: `world.inject_event(...)` endpoint where a human
(via dashboard or CLI) drops a custom proposal at the next tick. New
inbox phase first in the pipeline each tick.

**Effort**: ~2 days.

---

### #9 — Long-run resumability + timeline diff
**Status**: half-started. Persistence exists (snapshots every 7
ticks); no deterministic resume; no timeline-comparison tooling.

**Technical decision (2026-04-22)**: pure functional seed-derive
(NOT `random.getstate()`).
- Replace global `self.rng` with `derive_rng(seed, t, key)` where
  `key` identifies the decision site (e.g. `(agent_id, "move")`).
- Snapshots only need `(seed, tick)`; full RNG state recovers via
  re-derivation. Cross-platform, cross-Python, debuggable.

**Concrete deliverables**:
- assert `engine.run(N)` from a snapshot + same seed = byte-identical
  state to a fresh run for N ticks
- `lw diff snapshotA snapshotB` — death deltas, chapter divergence,
  top-3 emergent kinds that differ
- enables "what-if" research: rewind, change one event, re-run

**Effort**: ~3 days (cost is in finding + converting every
`self.rng.*` call site).

---

### #12 — Multi-seed batch runs + diversity comparison
**Status**: half-started — `reports/diversity.py` is a Marimo notebook
that runs N seeds and reports diversity. Not wired into `make check`
or CI. No CLI surface.

**Remaining**: `lw batch --seeds 10 --ticks 50` CLI that reuses the
notebook's logic and writes a JSON report. Wire into nightly CI on a
schedule.

**Effort**: ~half day.

---

### #17 — [Park, optional] Daily plan layer
**Status**: optional. Currently planner emits weekly intentions; Park
decomposes this into day → hour → action. Only worth doing once daily
emergent gameplay gets richer.

**Effort**: 1 day.

---

### #18 — [AgentSociety, optional] Public goods / collective action events
**Status**: optional. Group decisions (vote, mutual defense, resource
pooling) as a new `event_kind` family. Only payoff once cross-pack
bridge (#7) lands.

**Effort**: 1-2 days.

---

## ⚡ Performance recipe

To get the simulator running at the lowest tick latency:

```bash
# 1. Start Ollama with concurrency
OLLAMA_NUM_PARALLEL=4 OLLAMA_MAX_LOADED_MODELS=3 ollama serve

# 2. Use the agent-layer parallelism path (default after async commit)
lw smoke --ticks 8

# Optional further wins:
# - export OLLAMA_KEEP_ALIVE=30m   (avoid model reload between calls)
# - run two ollama instances on different ports for tier2 vs tier3
```

Measured impact (6-tick smoke, M3 Mac, 3 packs, all LLM features on):
- Baseline serial: ~12 min/tick
- + `OLLAMA_NUM_PARALLEL=4`: ~6-8 min/tick (~40% faster)
- + async self_update / perception: ~2-3 min/tick (~3-5× faster)
- + prompt KV-cache reuse via `system=`: ~1-2 min/tick
