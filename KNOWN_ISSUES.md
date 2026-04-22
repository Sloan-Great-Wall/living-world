# Known Issues & Planned Tasks

Tracked here so they don't get lost between sessions. Design docs live in
`$GDRIVE/Living-World/design/` (per README) — this file is for *concrete
bugs and small tasks* surfaced from real runs.

---

## 🐞 Open issues

### #19 — `EmergentEventProposer` puts SCP designations into `participants`
**Surfaced**: 2026-04-22, 30-tick validation run (post-gravity-fix).

**Symptom**: 38 out of 90 emergent proposals (42%) rejected because the
LLM wrote things like:
```json
{"event_kind": "conflict",
 "participants": ["d-9045", "scp-035"], ...}
```
"scp-035" is an *anomaly*, not an agent. The validator correctly rejects
unknown agent_ids, killing the otherwise-coherent proposal. This
appeared after we added the SCP-173/106/087/035/914 templates — the
richer SCP context successfully invites the LLM to imagine D-class /
SCP encounters but the schema can't represent the SCP as a participant.

**Frequency**: 42% of emergent calls in the 30-tick scp+liaozhai+
cthulhu run. Much higher than the gravity bug's 1-5%.

**Fix options** (cheapest first):

1. **Prompt clarification (5 min)** — in `EmergentEventProposer.SYSTEM_PROMPT`
   in `living_world/agents/emergent.py`, add right after the
   `participants` field description:
   > `participants` must be agent_ids from the list above. SCP designations
   > (SCP-173, SCP-106, SCP-035…), entities, anomalies, deities, and other
   > non-agent forces are NOT valid participants — refer to them inside
   > `narrative` and `belief_updates[].topic` instead.
   
   And add an in-context example showing a correct SCP-vs-agent
   encounter (one agent participant + SCP referenced in narrative).

2. **Pseudo-agent option** — model SCP-173, Cthulhu, etc. as actual
   `Agent` records (with `pack_id="scp"`, `tags={"anomaly"}`) so the
   LLM's mental model is reality. Bigger refactor (~1 day) but unlocks
   "the anomaly has feelings/affinity" scenarios.

3. **Validator forgiveness** — drop unknown participants silently and
   accept if at least one valid agent remains. Cheap but lossy: the
   resulting event would be missing the very entity that drives it.

**Recommendation**: option 1 first (cheap, high ROI). Track failure
rate for a few runs. If it doesn't drop below 10%, escalate to option 2.

**Test**: re-run a 12-tick sim after the prompt fix; assert
`emergent.stats.validate_fail / calls < 0.10`.

**Effort**: 5 min for option 1; 1 day for option 2.

---

### #1 — `EmergentEventProposer.injuries` accepts non-agent strings
**Surfaced**: 2026-04-22, 8-tick validation run with `llama3.2:3b + format=json`.

**Symptom**: 1/24 emergent proposals rejected by the validator. The LLM
returned:
```json
{"event_kind": "conflict",
 "participants": ["henry-armitage", "nathaniel-peaslee"],
 "injuries": ["nathaniel-peaslee", "gravity"], ...}
```
"gravity" is not an agent. The `injuries` field expects a list of agent
IDs, but the LLM sometimes interprets it as "things that injured them"
(causes) rather than "agents who got injured" (subjects).

**Frequency**: 1/24 emergent calls (~4%). Low impact (rejected cleanly,
no crash) but wastes one LLM call and prevents an otherwise-valid event.

**Fix options** (pick one):

1. **Prompt clarification (cheapest)** — in `EmergentEventProposer.SYSTEM_PROMPT`
   in `living_world/agents/emergent.py`, change the `injuries` field
   description to explicitly say:
   > `"injuries"`: list of objects `{"agent_id": str, "severity": "minor"|"grave"}` —
   > only agents from the participants list above. Do NOT include causes
   > or environmental factors.
   
   Then add 1 in-context example showing a correct injury entry.

2. **Validator tolerance** — in `_clamp_proposal` in the same file, when
   parsing `injuries`, drop unknown strings silently instead of nulling
   the whole proposal. We already drop unknowns in affinity_changes;
   apply the same pattern. The proposal would then be accepted with the
   one bad entry filtered out instead of fully rejected.

3. **Both (recommended)** — fix the prompt to reduce frequency, AND make
   the validator forgiving so the remaining cases don't kill the event.

**Test**: re-run `/tmp/lw_8tick_diag.py` (or equivalent) and confirm
`emergent.stats.validate_fail` drops to 0 across at least 30 proposals.

**Effort**: ~15 minutes.

---

## 🧹 Code-tightening tasks (from 2026-04-22 audit)

### #2 — `tick_loop.py` is becoming a god class (459 LOC)
**Why it matters**: every new LLM module so far has added ~30 LOC to
`step()`. The method is now ~150 LOC of inline phase orchestration.
Future contributors won't know which phase to extend without reading
the whole file.

**Refactor**: extract phases into an explicit pipeline:
```
PHASES = [DecayPhase, NeedsPhase, ReplanPhase, MovementPhase,
          InteractionsPhase, StorytellerPhase, ConsequencesPhase,
          ChroniclerPhase, ReflectionPhase, SnapshotPhase]
```
Each is a small class with `run(engine, t) -> TickStats` returning its
own contribution. `TickEngine.step()` becomes a 10-line loop.

**Effort**: ~3 hours. Mechanical, safe, no behavioral change.

---

### #3 — `dashboard/app.py` (800 LOC) + `controls.py` (796 LOC) mix UI and business logic
**Why it matters**: 26% of the project's LOC is in the dashboard, much
of it duplicating logic that should live in `living_world/` core. If we
ever swap Streamlit for something else (see feature #9), we'd rewrite
1600 LOC instead of 200.

**Refactor**: extract three layers
- `dashboard/views/` — pure render (Streamlit-specific)
- `dashboard/state/` — session-state management + caching
- Move all event/agent query helpers up into `living_world/queries.py`
  so any UI can use them.

**Effort**: ~1 day.

---

### #4 — `agents/__init__.py` is empty; no facade
**Why it matters**: every consumer imports
`from living_world.agents.self_update import AgentSelfUpdate`. If we
rename or split a module, we break every import.

**Fix**: populate `__init__.py` with re-exports of the public classes
(Narrator, AgentPlanner, AgentSelfUpdate, EmergentEventProposer,
Chronicler, DialogueGenerator, ConsciousnessLayer, SubjectivePerception,
LLMMoveAdvisor). 20 lines, all-future-proofing.

**Effort**: ~10 minutes.

---

### #5 — No in-repo `docs/` — design docs externalized to GDrive
**Why it matters**: README points new readers at
`$GDRIVE/Living-World/design/` which is private. There's zero on-ramp
for someone who clones the repo cold. No ADRs explain *why* tier 1/2/3,
*why* conscience, *why* the chronicler is descriptive-only.

**Fix**: create `docs/` with at minimum
- `architecture.md` — the 3-tier diagram + phase pipeline
- `adr/0001-tier-separation.md`
- `adr/0002-conscience-as-system-2.md`
- `adr/0003-chronicler-is-non-interventionist.md`
- `adr/0004-emergent-events-promote-and-prune.md`

**Effort**: ~half day.

---

### #6 — Test coverage thin (8 test files vs 30+ source modules)
**Why it matters**: today's existing tests are mostly smoke + a few
unit tests. The recent JSON-mode + tier swap landed without any
new automated test. Next regression will be felt in the next live run,
not in CI.

**Fix**: prioritize tests for the modules with highest churn:
- `agents/self_update.py` — assert prompt structure + fallback path
- `agents/planner.py` — assert cold-start hook fires once
- `agents/emergent.py` — assert validator handles malformed `injuries`
- `tick_loop.py` — assert phase ordering + replan-stale invariant
- `llm/ollama.py` — assert `format=json` is wired into the request body

**Effort**: ~1 day. Pairs naturally with #2 (refactor exposes test seams).

---

## ✅ Resolved (2026-04-22)

### Memory recall keyword + access bookkeeping (long-standing silent bug)
4 LLM modules called `memory.recall(..., top_k=N)` but the signature
expected `k=N`. The `TypeError` was swallowed by every call site's
try/except, so RAG never actually fed memories into any prompt. Fixed:
- `recall()` now accepts both `top_k=` (canonical) and `k=` (alias)
- `recall(..., current_tick=t)` now bumps `last_accessed_tick` and
  `access_count` on every returned entry, feeding the decay scoring
- planner / dialogue / conscience / move_advisor all pass current_tick

### Emergent injuries gravity-bug (was #1)
Validator now silently drops malformed `injuries` entries (bare strings
like `"gravity"`, unknown agent IDs) instead of nulling the entire
proposal. Prompt also explicitly says "this names WHO got hurt, not
WHAT hurt them" with correct/wrong examples.

### Chronicle Markdown export
`living_world.queries.export_chronicle_markdown(world)` renders all
chapters grouped by pack as a Markdown document. CLI:
`./lw export-chronicle --days 15 --out chronicle.md`. Pure function so
any consumer (web dashboard, Marimo notebook, future API) can reuse.

### Test coverage for new modules (was #6 partial)
14 new unit tests in `tests/test_new_modules.py` covering reflector
(beliefs emit / garbage / short input), memory decay (cap / access
boost / recall bookkeeping), phases (canonical order / failure
isolation), queries (diversity / grouping), and the emergent injury
regression. 70 tests total now (was 56).

### Dashboard ↔ queries.py alignment (start of #3)
`controls._render_mechanics_overview` now sources its feature list
from `queries.feature_status(engine)` — single source of truth, no
duplication. Future dashboard panels should follow the same pattern.

### Memory decay + Park reflection (was #14, #15)
`MemoryEntry` gained `last_accessed_tick` + `access_count`. New
`AgentMemoryStore.decay(agent_id, t, max_per_agent=200)` scores
memories by `importance × recency × log(access)` and prunes the
dullest 20% when an agent's store exceeds the cap. Reflections get
a +0.15 importance bonus inside the score, so the abstractions
outlive the raw events that formed them. Hooked into the existing
`ReflectionPhase` (reflect first, decay second). MemoryReflector
LLM module was already wired in the prior session.

### `tick_loop.step()` phase pipeline (was #2)
150-LOC god-method refactored into a 13-Phase pipeline in
`living_world/phases.py`. `TickEngine.step()` is now ~12 LOC that
iterates `self.pipeline` and isolates phase-level failures so a bad
phase can't kill the rest of the tick. Phase order / set is
swappable per-engine — tests can do `engine.pipeline = [...]`.
Phases: decay → needs_satisfy → cold_start_plan → replan_stale →
movement → interactions → storyteller → emergent → weekly_maintenance
→ chronicler → weekly_plan → reflection → snapshot.

### Per-module model override
`settings.llm.ollama_module_models: dict` lets you swap *one* agent
module to a different Ollama model without forking the engine wiring.
Recognized keys: `chronicler, narrator, planner, self_update, emergent,
dialogue, conscience, move_advisor, perception, reflector`. Empty by
default — all modules inherit the tier2/tier3 model. Resolution lives
in `factory.module_client()`.

Example to give the chronicler richer prose later:
```yaml
llm:
  ollama_module_models:
    chronicler: qwen3:14b
```

---

## 🚀 Feature backlog (from 2026-04-22 audit, ranked by ROI)

### #7 — Cross-pack bridge (shared tiles + migration events)
**Status**: not started. Highest creative value.
**Design decision (2026-04-22)**: YES, all loaded packs can interact.
The mental model is "checkbox to load = checkbox to encounter". A
future pack list is open-ended; the cross-pack mechanism must be
generic, not hard-coded for the current 3.

Today three packs run as parallel timelines on disjoint tile sets. To
get true "multi-mythos crossover", introduce:
- a `liminal` tile_type that any pack can place agents in (shared by
  *all* loaded packs, not pairwise)
- migration events as a generic mechanism: `<pack>:portal-anomaly`,
  `<pack>:dream-passage`, etc. — each pack contributes its own flavor
  of "how an agent crosses out"
- a per-agent `pack_origin` attr separate from current location, so
  identity is preserved when crossing
- world-pack manifest declares `cross_pack_compat: true|false`
  (default true) — lets a pack opt out if its lore demands isolation

**Effort**: 2-3 days. Touches: `world.py`, `tile.py`, agent persona
schema, plus 1-2 new event templates per pack (NOT N×N pairwise — one
generic "exit" event per pack composes with any other pack's tiles).

---

### #8 — Player prompt injection
**Status**: not started.
**UX decision (2026-04-22)**: build BOTH UIs.
- **Default**: a single natural-language textbox. The user types an
  intent ("what if the cult ritual succeeds?") and an LLM converts it
  into an EventProposal. Conscience still gets to APPROVE/ADJUST/VETO.
  Reuses the existing emergent.propose prompt machinery (~80% overlap).
- **Advanced**: an expandable form with tile/event_kind/participants/
  importance fields for power users running reproducible experiments.

Today the sim is purely autonomous. Add a `world.inject_event(...)`
endpoint where a human (via dashboard or CLI) can drop in a custom
event proposal at the next tick.

**Effort**: ~2 days. Touches: `tick_loop` (new inbox phase — first
phase to run each tick), dashboard form + textbox, CLI flag.

---

### #9 — Long-run resumability + timeline diff
**Status**: half-started. Persistence exists (snapshots every 7 ticks),
but no deterministic resume + no timeline-comparison tooling.
**Technical decision (2026-04-22)**: pure functional seed-derive (NOT
`random.getstate()`).
- Replace global `self.rng` with a `derive_rng(seed, t, key)` helper
  where `key` identifies the decision site (e.g. `(agent_id, "move")`).
- Every random choice site reads its own deterministic stream, derived
  from a small immutable triple. No global mutable RNG state.
- Snapshots only need to record `(seed, tick)`; the entire RNG state
  is recovered by re-derivation. Cross-platform, cross-Python-version,
  debuggable: any "why did X choose Y at tick 30" question becomes
  reproducible from `derive_rng(42, 30, ("X", "move"))`.

Concrete:
- assert `engine.run(N)` from a snapshot + same seed = byte-identical
  state to a fresh run for N ticks
- add `lw diff snapshotA snapshotB` — show death deltas, chapter
  divergence, top-3 emergent kinds that differ
- enables "what-if" research: rewind, change one event, re-run

**Effort**: ~3 days. Cost concentrated in finding + converting every
`self.rng.*` call site (movement, resolver, interactions, storyteller).

---

### #10 — Memory decay + reflection
**Status**: half-started. `memory_store.py` records and recalls; no
forgetting, no synthesis.

Park 2023's key innovation we're missing:
- **decay**: importance score decays by recency × access frequency;
  low-score memories get pruned at reflect time
- **reflection**: every N ticks, the LLM reads the agent's top-K recent
  memories and produces one higher-level *belief* that gets re-stored
  as a memory of its own

Without this, agents never form abstractions. With it, "Strelnikov
keeps surviving" → "I am lucky" → drives bolder future choices.

**Effort**: ~2 days.

---

### #11 — CI + type checking (mypy + ruff)
**Status**: not started.

Add `.github/workflows/ci.yml` running pytest + ruff + mypy. Fail on
new errors only (so the existing codebase doesn't block first PR).

**Effort**: ~half day. **READY** — no design questions.

---

### #12 — Multi-seed batch runs + diversity comparison
**Status**: not started.

`lw batch --seeds 10 --ticks 50` runs 10 sims and produces a report:
- which event_kinds appear in N/10 runs (universal vs rare)
- which chapter titles repeat (cliché detection)
- agent-survival distribution (variance proxy)

This is *the* tool for tuning the sim — without it we're guessing.

**Effort**: ~2 days.

---

### #14 — [Park] Memory reflection — LLM-driven belief synthesis
**Status**: half-started. `memory_store.reflect()` exists but only
concatenates raw memories. Park 2023's mechanism uses an LLM to read
recent memories and emit one *higher-level belief* that becomes a new
memory entry, retrieved with a 1.3× boost.

**Why it matters**: without reflection, agents can recall events but
never form abstractions. With it: "I survived three SCP-173 sweeps" →
"I am unusually lucky" → biases future risk-taking.

**Implementation**:
- New `living_world/agents/reflector.py` — LLM module that reads N raw
  memories, returns 1-3 belief strings with importance scores
- `memory_store.reflect()` wraps the new LLM module; falls back to
  current concat behavior on LLM failure
- Beliefs go into `agent.set_belief(topic, belief)` in addition to the
  memory store, so they show up in planner/self_update prompts

**Effort**: ~1 day. **READY**.

---

### #15 — [Park] Memory decay + pruning
**Status**: not started. Memories accumulate forever today.

**Implementation**:
- Add `last_accessed_tick` to `MemoryEntry`
- New `memory_store.decay(t)` — at reflect time, score every memory by
  `importance × recency_factor × access_factor`; drop bottom 20% if
  store > 200 entries per agent
- Hook into the existing reflect cadence (every 7 ticks)

**Effort**: ~half day. **READY**.

---

### #16 — [AgentSociety] Social network metrics
**Status**: not started.

Today we have pairwise affinity scores but no graph view. Add:
- `living_world/metrics/social.py` — compute degree centrality, weakly
  connected components, clustering coefficient over the affinity graph
  thresholded at |aff| ≥ 30
- A `lw social <pack_id>` CLI that prints the top-5 most central agents,
  number of cliques, and isolated nodes
- Dashboard panel showing the same

**Why it matters**: lets us *see* who the social hub is, which agents
form factions, and whether killing one HF actually fragments the
network. Direct readout for chronicle quality assessment.

**Effort**: ~half day for the metric + CLI. Dashboard panel +half.
**READY** — pure pandas/numpy, no LLM.

---

### #17 — [Park, optional] Daily plan layer
**Status**: not started, **OPTIONAL** (can-learn).

Currently planner emits weekly intentions. Park decomposes this into
day → hour → action. Only worth doing once daily emergent gameplay
gets richer.

**Effort**: 1 day. Park has a clean spec.

---

### #18 — [AgentSociety, optional] Public goods / collective action events
**Status**: not started, **OPTIONAL** (can-learn).

Group decisions (vote, mutual defense, resource pooling) as a new
event_kind family. Only payoff once cross-pack bridge (#7) lands.

**Effort**: 1-2 days.

---

### #13 — Web-native dashboard (replace Streamlit)
**Status**: ⏳ STARTING (2026-04-22 evening).
**Game-UI design spec (2026-04-22)**:
- Full-screen map background (canvas / WGPU surface) with live agent
  movement, pan + zoom
- Top status bar: single horizontal strip, fully transparent over the
  map. Brand on the left; live stats inline (day, events, alive,
  deaths, packs, ollama health, models). Click a stat → detail
  popover. Right side: two icon buttons only — `Settings` and
  `Library` (the codex / persona / story browser)
- Bottom action card: floating panel with semi-transparent backdrop
  blur. All play controls + agent inspect tabs live here. Single
  card, no second-level navigation
- Aesthetic: Stellaris / EU IV / Civ VI inspiration — dark base,
  warm gold accent, parchment-like card surfaces

**False start (2026-04-22)**: A FastAPI + vanilla JS scaffold was
created and immediately rolled back per user direction to commit to
the Rust path now rather than build a throwaway prototype.

**Tech-stack decision (2026-04-22)**: full Rust stack.
- **Leptos** — fine-grained reactive UI compiled to WASM (Rust's
  Solid.js equivalent). Sim event types defined in `living_world`'s
  Rust port shared verbatim with the frontend — no JSON-stringify
  round-trips, no schema duplication.
- **Tauri** — Rust desktop shell (5MB vs Electron's 200MB). Same
  bundle ships as web app via Leptos's CSR/SSR mode.
- **WGPU canvas** — for the agent map. Native GPU rendering, 60fps
  with thousands of agents, future-proof for 3D.
- Optional: keep Streamlit running as the "Python-friendly" prototype
  while the Rust stack matures, deprecate when feature-complete.

Why this stack (vs SvelteKit / Next.js):
- **Performance**: native code + GPU, no JS GC pauses
- **Safety**: Rust borrow checker catches memory + concurrency bugs
  at compile time
- **Strict compilation**: type errors caught before deploy, no
  dynamic surprises
- **AI-era productivity**: LLMs write competent Rust; the engineering
  cost vs JS frameworks shrinks every year while runtime advantages
  compound

Streamlit re-renders the whole page on every interaction; for a live
sim this is jarring. The Leptos rewrite gives true real-time push for
event animation, chronicle scrolling, agent movement.

**Effort**: ~1-2 weeks for parity with current Streamlit features.
**NOT READY** — needs design pass first (Rust port surface area,
event protocol, decide if `living_world` itself stays Python or gets
re-cored in Rust too — likely the latter eventually).

---


