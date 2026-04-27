# Living World — Historical Decisions & Resolved Issues

This file is the archive: completed phases, fixed bugs, and design
retrospectives. New entries land at the **top**. Active items (open
bugs, in-flight backlog) live in `KNOWN_ISSUES.md` instead.

---

## Small fixes batch · L-19 + L-04 (2026-04-26)

### L-19 — Emergent SCP-as-participant prompt fix
**What landed**: `EmergentEventProposer.SYSTEM_PROMPT` now explicitly
tells the LLM that SCP designations (SCP-173 / SCP-106 / SCP-035 /
etc.), anomalies, and deities are NOT valid `participants`. Includes
correct/wrong examples right in the schema description. The validator
already drops unknown agent_ids; this just stops them showing up in
the first place.

**Regression test**: `tests/test_new_modules.py
::test_emergent_drops_scp_designations_from_participants`. Asserts
the proposal survives after SCP-035 is dropped from participants AND
that the SCP reference still appears in the narrative.

**Expected impact**: 30-tick run had 42% of emergent proposals
rejected for this exact reason. With the prompt clarification, that
should drop substantially. Re-measure on the next live smoke.

### L-04 — `living_world/agents/__init__.py` public facade
**What landed**: 16 public classes + 2 helpers re-exported from the
agents package. Consumers can now write
`from living_world.agents import AgentSelfUpdate, Narrator` instead
of reaching into submodules. Future renames or splits only require
editing `__init__.py`, not every consumer.

**Regression test**: `test_agents_facade_exposes_public_surface`
asserts every name in the expected set is in `__all__` AND resolves
to a non-None object.

**Note**: existing `from living_world.agents.<sub> import …` style
imports still work — the facade is additive, not enforcing. We can
tighten with a lint rule later if drift becomes a problem.

---

## Phase 3 · sim-core 增量 port (2026-04-26)

**What landed**: TypeScript ports of `living_world.queries`,
`living_world.rules.heat`, plus `requiredSlots` from the resolver.
Pure functions only; parity tests against Python fixtures (38 vitest
tests, all passing first run). Bundle stayed at 3.70 KB.

**Decision rationale**: chosen over alternatives (Tauri sidecar,
Tauri-invoke replacing HTTP, event sourcing) because it was the only
Phase-3 candidate with **net-negative LoC trajectory** — each port
enables Python deletion once dashboards consume the TS version.

**Stop point**: porting halts at the LLM/agent layer. Sim engine
internals (orchestrators, mutation) stay in Python.

---

## Phase 2 · 跨层契约编译期化 (2026-04-26)

**Pipeline**: `living_world/web/schemas.py` (Pydantic) → `make schema` →
`api-schema/openapi.json` → `openapi-typescript` →
`dashboard-tauri/src/types/api.generated.ts`.

Any Python field rename now red-lines the dashboard at `tsc --noEmit`
time. `make schema-check` enforces drift detection in CI.

**Companion changes**:
- `uv` replaces `pip` in `make install` (15× faster resolve)
- TS-side `Result<T, E>` taxonomy in `dashboard-tauri/src/lib/result.ts`
  mirroring the Python `LLMError` discipline
- Server: every route declares `response_model=`; raw-dict returns
  banned

---

## Phase 1.5 · 极简化 (2026-04-26)

**Monorepo consolidation**:
- npm workspaces — single root `package.json`, single
  `package-lock.json`, single `node_modules/`
- `tsconfig.base.json` shared by both TS packages via `extends`
- Justfile deleted (Makefile is universal; parallel targets were noise)
- CI workflow simplified to one `make check` job

---

## Phase 1 · AI-Native foundation (2026-04-26)

**Typed errors replace string sentinels** (criterion B):
- New `LLMError` taxonomy — `LLMUnreachable / LLMTimeout /
  LLMBadResponse / LLMUnknownError`
- `LLMResponse.error: LLMError | None`; `text=""` on failure
- The `[ollama-error: X]` sentinel string was retired

**Structured logs** (criterion B):
- `TickLogger(json=True)` or `LW_LOG_JSON=1` env emits
  `{tick, event, …}` JSON lines
- `jq -c 'select(.event=="EVENT" and .outcome=="failure")'` works
- `phase_error` / `llm_error` records with structured kind

**Single-command verification** (criterion C):
- `make check` aggregates ruff + basedpyright + pytest + tsc + vitest
  + bundle:check; exit 0/1 in <60s
- `basedpyright` replaces `mypy` (Astral-adjacent, faster, stricter)

**Dead-stack cull**:
- Streamlit dashboard deleted (`living_world/dashboard/`)
- `[db]` extra removed (psycopg / pgvector / redis)
- `[llm]` extra removed (OpenAI SDK was unused)
- `sql/init.sql`, `.streamlit/`, `dashboard-tauri/bun.lock` deleted
- `lw dashboard` CLI subcommand removed

---

## Resolved (2026-04-22 batch)

### #1 — Emergent injuries gravity-bug
Validator now silently drops malformed `injuries` entries (bare
strings like `"gravity"`, unknown agent IDs) instead of nulling the
entire proposal. Prompt explicitly says "this names WHO got hurt, not
WHAT hurt them" with correct/wrong examples.

### #2 — `tick_loop.py` god class
150-LOC `step()` refactored into a 13-Phase pipeline in
`living_world/phases.py`. `TickEngine.step()` is now ~12 LOC iterating
`self.pipeline` with phase-level failure isolation. Phases:
decay → needs_satisfy → cold_start_plan → replan_stale → movement →
interactions → storyteller → emergent → weekly_maintenance →
chronicler → weekly_plan → reflection → snapshot.

### #3 — Dashboard / queries.py alignment
`feature_status(engine)` lives in `living_world/queries.py` as the
single source of truth. The Streamlit dashboard was eventually deleted
in Phase 1 (replaced by dashboard-tauri).

### #6 — Test coverage thin
Grew from 8 files / ~30 tests to a 4-layer pyramid: 84 pytest
(unit + property + invariant + smoke) + 38 vitest (parity). Smoke
runs deterministic without LLM. `tests/test_simulation_invariants.py`
asserts 9 global invariants on every short run.

### #10 / #14 — Memory reflection (Park-style)
`agents/reflector.py` is the LLM module that reads N raw memories and
emits 1-3 belief strings with importance scores. Beliefs go to
`agent.set_belief(topic, belief)` so they show up in subsequent
planner / self_update prompts.

### #15 — Memory decay + pruning
`MemoryEntry` gained `last_accessed_tick` + `access_count`.
`AgentMemoryStore.decay(agent_id, t, max_per_agent=200)` scores
memories by `importance × recency × log(access)` and drops the
dullest 20% when an agent's store exceeds the cap. Reflections get
+0.15 importance bonus inside the score.

### #11 — CI + type checking
`.github/workflows/test.yml` runs `make check` on push + PR with
matrix Python 3.11/3.12 + Node 20. Replaces the original
"mypy + ruff" plan with the stricter `basedpyright` + ruff combo.

### #13 — Web-native dashboard (replace Streamlit)
Tauri 2 + Solid + TypeScript + Vite stack landed (`dashboard-tauri/`).
Originally specced as full-Rust Leptos; we course-corrected to TS
because (a) the Solid + Vite ecosystem has more AI-coding training
data density, (b) Rust is reserved for the Tauri shell + future
WASM compute, not application logic. Streamlit deleted in Phase 1.

### #16 — Social network metrics
`living_world/metrics/social.py` exposes affinity-graph helpers
(connected components, degree centrality, clustering coefficient).
TypeScript port in `packages/sim-core/src/socialMetrics.ts` is
parity-tested. Dashboard's `SocialPanel.tsx` runs the metrics
client-side from a single `/api/social_graph` fetch.

### Memory recall keyword + access bookkeeping
4 LLM modules called `memory.recall(..., top_k=N)` but the signature
expected `k=N`. The `TypeError` was swallowed by every call site's
try/except, so RAG never actually fed memories into any prompt. Fixed:
- `recall()` accepts both `top_k=` (canonical) and `k=` (alias)
- `recall(..., current_tick=t)` bumps `last_accessed_tick` and
  `access_count` on every returned entry, feeding decay scoring
- planner / dialogue / conscience / move_advisor all pass current_tick

### Per-module model override
`settings.llm.ollama_module_models: dict` lets you swap *one* agent
module to a different Ollama model without forking engine wiring.
Recognized keys: `chronicler, narrator, planner, self_update,
emergent, dialogue, conscience, move_advisor, perception, reflector`.
Empty default — modules inherit tier2/tier3.

### Chronicle Markdown export
`living_world.queries.export_chronicle_markdown(world)` renders
chapters grouped by pack as Markdown. CLI:
`./lw export-chronicle --days 15 --out chronicle.md`.

---

## Notable false starts

### Web stack: Rust/Leptos → reverted to TS/Solid
A 2026-04-22 plan picked Leptos + WGPU canvas + Rust-cored sim. We
walked it back to Solid + plain TypeScript inside Tauri because the
LLM-assisted iteration loop is dramatically faster on the TS side
(more training data, simpler debugger, no Rust compile lag for UI
tweaks). Tauri's Rust shell is preserved as the "future WASM compute"
slot; for now `src-tauri/src/` carries only boilerplate.

### Dashboard FastAPI + vanilla JS scaffold (briefly)
Created and immediately rolled back per user direction to commit to
the modern UI stack now rather than ship a throwaway HTML prototype.

### Bun as JS runtime (briefly)
Used as the dashboard package manager during Phase 1; hit
`file:..` workspace-spec issues + occasional esbuild flakes on macOS.
Switched to npm for stability + ecosystem default. Bun may re-enter
when its monorepo story matures.
