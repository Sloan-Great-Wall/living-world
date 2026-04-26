# @living-world/sim-core

TypeScript port of pure-function modules from the Python sim. Each
module is parity-tested against fixtures dumped from the Python source.

| TS module               | Python source                                     | Phase |
|-------------------------|---------------------------------------------------|-------|
| `src/dice.ts`           | `living_world/rules/resolver.py` (pure parts)     | 1     |
| `src/socialMetrics.ts`  | `living_world/metrics/social.py`                  | 1     |
| `src/queries.ts`        | `living_world/queries.py`                         | 3     |
| `src/heat.ts`           | `living_world/rules/heat.py`                      | 3     |

The goal of this package is to migrate Python's pure functions to
TypeScript incrementally, with parity tests as the safety net. Each
module that lands here is one less round-trip the dashboard has to
make to the Python server, and one less file Python has to own
long-term.

## Running

```bash
npm install
npm run typecheck
npm test
```

## Regenerating fixtures

If you change either side's algorithm, regenerate the golden fixtures
from the Python implementation:

```bash
npm run regen-fixtures
```

This invokes `scripts/dump_fixtures.py` against the project's `.venv`.
The script imports the Python implementations directly, so the
fixtures always reflect current Python behavior. Then run `npm test`
to verify the TS side still matches.

## What is deliberately NOT ported

- **Stateful orchestrators** — `EventResolver`, `TickEngine`, the
  agent classes, anything that owns mutable `World`/`Agent` state.
  The point of this port is to migrate the *computational kernel*;
  state ownership stays in Python until we have a data-layer story.
- **Python's `random.Random`** — byte-parity across runtimes is
  brittle. `outcomeForRoll` takes the raw d20 as input, so parity
  tests assert the deterministic outcome-from-roll branch without
  needing matching RNG state.
- **LLM-touching modules** — narrator, dialogue, planner, etc. They
  belong in Python where the LLM ecosystem lives.

## What is ported (Phase 3)

### `queries.ts`
- `recentEvents` — last N events
- `eventsByPack` / `eventsByDay` — grouping
- `eventKindDistribution` — top-K most-frequent
- `diversitySummary` — headline stats for the dashboard top-bar
- `exportChronicleMarkdown` — chapter list → Markdown

The dashboard can now run any of these client-side from one
`/api/events` fetch instead of a per-aggregation HTTP call.

### `heat.ts`
- `scoreTileHeat` — heuristic for "where will drama land today?"
- `hotTiles` — top-K hot tiles, used to drive the emergent proposer

The dashboard could surface heat in real-time without round-tripping.

### `dice.ts`
- (existing) `scoreEventImportance`, `outcomeForRoll`,
  `environmentalModifiers`, `inventoryBonus`
- (Phase 3) `requiredSlots` — `?`-leak detector for templates

## Decision: should we keep porting?

The original gate for "expand the port" is now solidly met:

- [x] All modules type-check under `--strict --noUncheckedIndexedAccess`
- [x] All parity fixtures pass on first run (38/38 as of Phase 3)
- [x] CI runs the TS suite alongside Python via `make check`
- [x] Bundle size consumed by the Tauri dashboard ≪ 50 KB
      → still **3.70 KB minified** (Phase 3 ports are pure logic, no deps)
- [x] One real consumer wired (`SocialPanel.tsx`)

**Phase 3 confirms**: the Python → TS port is a sustainable
incremental simplification. Each module deletes ~20-50 LoC of Python
roundtrip code and adds slightly less TS, while making the dashboard
more capable client-side. The trajectory is **net code reduction**
when measured across the entire repo, not just sim-core.

Next candidates (in order of value/cost ratio):
- `living_world.metrics.social_summary` text formatter (trivial)
- `living_world.invariants` checks (medium — pure but many of them)
- Snippets of `living_world.world_pack` YAML→object (would need yaml parser)

Hold off on the LLM/agent layer indefinitely.
