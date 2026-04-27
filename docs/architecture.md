# Living World — Architecture

This document is the on-ramp for new readers. It explains the three-layer
T-shape, the tick pipeline, and the cross-layer contract.

For *why* each shape was chosen, see the ADRs in `docs/adr/`. For *what
has happened* on the timeline, see [`HISTORY.md`](HISTORY.md). For *what
is open*, see [`KNOWN_ISSUES.md`](../KNOWN_ISSUES.md).

---

## 1 · The three-layer T-shape

```
 ┌──────────────────────────── Tauri Desktop ───────────────────────────┐
 │                                                                       │
 │   TS  (Solid + Vite)        — UI + browser-side compute               │
 │   │                                                                   │
 │   ├ dashboard-tauri/        Solid components, signals, stores         │
 │   └ packages/sim-core/      Pure functions ported from Python         │
 │                             (dice / heat / queries / socialMetrics)   │
 │                                                                       │
 │       ↕  (today: localhost HTTP   tomorrow: Tauri invoke)            │
 │                                                                       │
 │   Rust (Tauri shell)        — IPC + lifecycle                         │
 │   │                                                                   │
 │   └ src-tauri/src/lib.rs    Sidecar spawn, port discovery,            │
 │                             /api/health probe, shutdown reaper        │
 │                                                                       │
 │       ↕  spawn / kill_on_drop                                         │
 │                                                                       │
 │   Python (sidecar)          — Sim engine + LLM orchestration          │
 │   │                                                                   │
 │   ├ living_world/core/      Agent / Event / World / Tile (pydantic)   │
 │   ├ living_world/phases.py  13-stage tick pipeline                    │
 │   ├ living_world/agents/    LLM modules (planner, narrator, …)        │
 │   ├ living_world/llm/       Tiered LLM client + typed errors          │
 │   ├ living_world/memory/    Park-style episodic memory + decay        │
 │   ├ living_world/rules/     Pure-rule heuristics (heat, resolver, …)  │
 │   └ living_world/web/       FastAPI sim API + Pydantic schemas        │
 │                                                                       │
 │       ↕  HTTP                                                         │
 │                                                                       │
 │   Ollama daemon (external)  — local LLM runtime                       │
 │     tier 2 model: llama3.2:3b                                         │
 │     tier 3 model: gemma3:4b                                           │
 │                                                                       │
 └───────────────────────────────────────────────────────────────────────┘
```

The shape is a **T**: Rust is the spine, Python and TS are the arms.
Each language is chosen for what it's irreplaceable at, not for any
single-language ideology:

- **Python** — has the LLM ecosystem (Ollama / huggingface / langchain
  family / Marimo) that no other language matches yet
- **TypeScript** — has the UI ecosystem (Solid / Vite / Tauri) and the
  AI-coding training data density
- **Rust** — has the strictest compiler diagnostics and the right idiom
  for desktop process lifecycle (Tauri's native language)

See [ADR 0001](adr/0001-three-layer-stack.md) for the rejected
alternatives (full-Python via Streamlit, full-TS via Leptos, etc.).

---

## 2 · The tick pipeline

Each "virtual day" is one `TickEngine.step()`. Inside, an explicit
13-phase pipeline drives the world forward. Phases are declared in
`living_world/phases.py`; each is a small class with a single
`run(engine, t, stats)` method.

```
   decay              · need + emotion drift
   needs_satisfy      · hungry agents eat, threatened ones rest
   cold_start_plan    · mark plan-less HFs stale (so ReplanPhase fills)
   replan_stale       · weekly LLM plan for stale agents
   movement           · rule + LLM advisor tile choice
   interactions       · lethal encounters, companionship, flight
   storyteller        · per-tile rule-based event proposals
   emergent           · LLM proposes novel events on hot tiles
   weekly_maintenance · template promote/prune from emergent hits
   chronicler         · 说书人 writes a chapter (every N ticks, observes only)
   weekly_plan        · scheduled weekly plan refresh (separate from cold-start)
   reflection         · Park-style memory reflection + decay pruning
   snapshot           · serialize + persist tick state
```

**Phase isolation**: a failing phase is caught by `step()` and recorded
via `tick_logger.phase_error`; the rest of the tick continues. This
prevents one flake (e.g. Ollama down) from killing the whole world.

**Phase swappability**: tests use `engine.pipeline = [...]` to isolate
behavior. The default order is canonical and asserted by
`test_default_pipeline_has_canonical_phase_order`.

For *why* the chronicler runs after events but never before them, see
[ADR 0004](adr/0004-chronicler-non-interventionist.md). For *why*
events route through tier 1 / 2 / 3 LLM cost classes, see
[ADR 0002](adr/0002-tier-llm-routing.md). For *why* a separate
"conscience" layer sits between the dice resolver and the event
record, see [ADR 0003](adr/0003-conscience-as-system-2.md).

---

## 3 · Cross-layer typed contract

Field renames at the Python layer red-line the dashboard at compile
time. The pipeline:

```
   living_world/web/schemas.py    (Pydantic — single source of truth)
            │
            ▼  scripts/dump_openapi.py
   api-schema/openapi.json        (committed, drift-detected)
            │
            ▼  npm run schema:gen   (openapi-typescript)
   dashboard-tauri/src/types/api.generated.ts
            │
            ▼  re-export façade
   dashboard-tauri/src/types/api.ts
            │
            ▼  used by every component
   import type { Agent, WorldEvent } from '../types/api'
```

`make schema-check` (part of `make check`) fails the build if the
committed `openapi.json` diverges from what live Pydantic models would
emit. Schemas only get out of sync if a developer forgets `make schema`
— and CI catches that.

See [ADR 0005](adr/0005-typed-cross-layer-contract.md) for the
rejected alternative (manually maintained TS types, which we tried
and abandoned in Phase 1).

---

## 4 · Data flow (one tick, end-to-end)

```
  user clicks "Tick +1"
   └► [TS / Solid] BottomCard.tick()
       └► api.tick(1)   resolves base via invoke('get_api_base')
            └► [HTTP] POST /api/tick {"n":1}
                 └► [Python / FastAPI] route handler
                     └► STATE.engine.run(1)
                         └► TickEngine.step()
                             └► for phase in self.pipeline:
                                  └► phase.run(engine, t, stats)
                                       └► [Ollama HTTP] async LLM calls
                                            └► returns LLMResponse{ok:true, text:…}
                                                          OR {ok:false, error:LLMTimeout}
                                  └► _process_event(...)
                                       └► narrator.enhance / repository.append /
                                          memory.remember / consequences.apply
                         └► returns tick stats
                 └► returns WorldSnapshot (Pydantic-validated)
            └► JSON response, camelCase
       └► [TS] worldStore signals update
            └► [Solid] all subscribed components re-render
                       (SocialPanel, TopBar, MapCanvas, …)
```

Every boundary on this chain is **typed**: Pydantic at the route
level, OpenAPI at the wire level, generated TS at the consumer level.
Errors are typed too — `LLMError` taxonomy on the Python side,
`Result<T, ApiError>` on the TS side.

---

## 5 · Where things live (file map)

```
living_world/                  · Python sim core
├ core/                        Agent, Event, Tile, World — Pydantic models
├ phases.py                    13-stage tick pipeline
├ tick_loop.py                 TickEngine (drives the pipeline)
├ factory.py                   Wiring: Settings → engine + LLM modules
├ agents/                      LLM-driven decision modules
│   ├ __init__.py              Public facade (re-exports the lot)
│   ├ planner.py               Weekly plan
│   ├ narrator.py              Tier-3 narrative rewrite
│   ├ chronicler.py            说书人
│   ├ emergent.py              Novel event proposer
│   ├ conscience.py            VETO/ADJUST layer
│   ├ dialogue.py              A→B reaction loop
│   ├ perception.py            Subjective event reframe
│   ├ self_update.py           Inner-state shift
│   ├ reflector.py             Memory → belief
│   ├ move_advisor.py          Tile choice override
│   └ event_curator.py         Promote / prune templates
├ llm/                         LLM client + typed errors
│   ├ base.py                  LLMClient ABC + LLMError taxonomy
│   └ ollama.py                OllamaClient (sync + async)
├ memory/                      Episodic memory + decay
├ rules/                       Pure-rule heuristics
│   ├ resolver.py              Dice + outcome + slot detection
│   ├ heat.py                  Tile heat scoring
│   ├ movement.py              Rule-layer tile choice
│   ├ interactions.py          Lethal / companionship / flight
│   ├ decay.py                 Need + emotion drift
│   └ storyteller.py           Per-tile event proposals
├ metrics/                     Affinity-graph metrics
├ web/                         FastAPI sim API
│   ├ schemas.py               Pydantic response models
│   └ server.py                Routes
├ queries.py                   Read-only world helpers
├ invariants.py                9 global invariants
├ tick_logger.py               Structured (text or JSON) tick log
├ persistence.py               Snapshot save / replay
└ cli.py                       `lw` typer commands

dashboard-tauri/               · TS frontend + Tauri shell
├ src/
│   ├ App.tsx                  Top-level layout
│   ├ api.ts                   REST client (resolves base via invoke)
│   ├ stores/worldStore.ts     Solid signals (truth for components)
│   ├ components/              TopBar, BottomCard, MapCanvas, panels
│   ├ types/api.generated.ts   ← auto-generated from Pydantic schemas
│   ├ types/api.ts             friendly aliases over generated
│   └ lib/result.ts            Result<T, ApiError>
└ src-tauri/                   Rust shell
    ├ src/lib.rs               Sidecar spawn, get_api_base invoke
    └ src/main.rs              Entry

packages/sim-core/             · TS port of pure-function modules
├ src/
│   ├ dice.ts                  scoreEventImportance + outcomeForRoll + …
│   ├ heat.ts                  scoreTileHeat + hotTiles
│   ├ queries.ts               recentEvents + diversitySummary + …
│   └ socialMetrics.ts         affinityGraph + computeSocialMetrics
└ test/                        parity tests against Python fixtures

api-schema/openapi.json        · single source of truth for the wire
docs/                          · architecture docs + ADRs + history
```

---

## 6 · Verification gates (`make check`)

A single command runs every contract:

```
make check
  ├ ruff check + format check        Python style
  ├ basedpyright (strict)            Python types
  ├ pytest -x -q                     ~114 unit + property + invariant + smoke
  ├ schema-check                     Pydantic ↔ openapi.json drift detector
  ├ packages/sim-core: tsc + vitest  ~38 parity tests
  ├ dashboard-tauri: tsc + build     UI typecheck + bundle
  └ bundle:check                     sim-core ≤ 50 KB budget gate
```

Exit 0 / non-zero. <60 s for the python+TS portion (live Ollama tests
add ~2 min when the daemon is up).
