# Known Issues & Planned Tasks

Tracks **open** bugs and **active** backlog. Resolved items + design
retrospectives live in [`docs/HISTORY.md`](docs/HISTORY.md).

---

## 🐞 Open issues

### #21 — Production app packaging (PyInstaller sidecar + signed .app/.exe)
**Status**: dev-mode sidecar landed (`npm run tauri dev` auto-spawns
Python). Production path still missing.

**What's needed**:
- PyInstaller produces a single binary from `living_world.web.server`
- Tauri `bundle.externalBin` points at the platform-specific binary
  (`-aarch64-apple-darwin` etc.)
- Child process placed in its own POSIX process group (or Windows
  job object) so the kernel reaps the sidecar if Tauri is SIGKILL'd
  (today: orphans, holds :8765 until manually `kill`'d)
- `tauri build` produces a runnable `.app` / `.exe` / `.AppImage`
  with no Python install required on the user's machine
- Ollama detection: friendly first-run prompt if `ollama` not on PATH

**Effort**: 1-2 days for dev-quality build; another 1-2 days for
code-signing + notarization (macOS).

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
