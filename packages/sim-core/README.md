# @living-world/sim-core

TypeScript port of two pure-function modules from the Python sim:

| TS module               | Python source                                     |
|-------------------------|---------------------------------------------------|
| `src/dice.ts`           | `living_world/rules/resolver.py` (pure parts)     |
| `src/socialMetrics.ts`  | `living_world/metrics/social.py`                  |

This is a **trial port** — the goal is to validate two questions:

1. **Are these primitives portable cleanly?** — yes; both are pure
   data-in / data-out and have no World/Agent state coupling beyond the
   light DTOs declared in each module.
2. **Can we keep parity bit-exact under churn?** — yes; the parity test
   harness in `test/` loads JSON fixtures dumped by Python and asserts
   the TS port returns the same values.

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
fixtures always reflect the current Python behavior.

## What was deliberately NOT ported

- The `EventResolver` class itself — it owns state mutation against
  `World` and `Agent`. The point of this port is to prove the
  *computational kernel* travels; the orchestrator stays in Python
  until/unless we decide to migrate the data layer too.
- Python's `random.Random` — RNG byte-parity across runtimes is
  brittle. Instead, `outcomeForRoll` takes the raw d20 as input,
  so parity tests assert the deterministic outcome-from-roll branch
  without needing matching RNG state.

## Decision: should we keep porting?

Track the recommendation in the parent `KNOWN_ISSUES.md`. The success
criteria for "yes, expand the port":

- [x] Both modules type-check under `--strict --noUncheckedIndexedAccess`
- [x] All parity fixtures pass on first run
- [x] CI runs the TS suite alongside Python
- [x] Bundle size of `sim-core` consumed by the Tauri dashboard < 50 KB
      → measured **3.70 KB minified** (14× under budget). Run
      `npm run bundle:check` from `dashboard-tauri/`.
- [x] One real consumer in `dashboard-tauri/` switched to the TS impl
      → `SocialPanel.tsx` (Library → Social tab) computes
      `computeSocialMetrics` client-side from `/api/social_graph`.
      Server stays a thin data tap; metrics math runs in the browser.

All five criteria green. Recommendation: keep porting selectively — start
with `queries.ts` (recent_events / diversity_summary / event_kind_distribution).
Hold off on porting anything that owns mutable World state until we have
a story for the data layer.
