# ADR 0005 · Typed cross-layer contract via Pydantic → OpenAPI → TS

| Status | Accepted (Phase 2, 2026-04-26) |
|---|---|
| Deciders | sloan + Claude |
| Supersedes | hand-maintained `dashboard-tauri/src/types/api.ts` |

## Context

Phase 1 had the dashboard's TS types hand-typed in
`dashboard-tauri/src/types/api.ts`. Every Python schema change
required a manual TS edit. Drift was inevitable — the only question
was when it would surface as a runtime undefined.

Concretely: Pydantic `Agent.is_historical_figure: bool` ↔ TS
`Agent.isHf: boolean` was synced by hand. Three field renames in
Phase 1 each broke at least one TS consumer that the developer
forgot to update.

## Decision

The Pydantic schemas in `living_world/web/schemas.py` are the single
source of truth. The pipeline:

```
Pydantic models  ──►  api-schema/openapi.json  ──►  api.generated.ts
       ▲                                                  │
       │                                                  ▼
   developer edits                          re-export façade types/api.ts
                                                          │
                                                          ▼
                                          components import from façade
```

Tooling:
- `scripts/dump_openapi.py` runs the FastAPI app's OpenAPI schema
  generator and writes `api-schema/openapi.json` (committed)
- `npm run schema:gen --workspace=dashboard-tauri` invokes
  `openapi-typescript` to write `src/types/api.generated.ts`
- `dashboard-tauri/src/types/api.ts` re-exports friendly aliases
  (`Agent`, `WorldEvent`, …) over the generated namespace
- `make schema-check` (part of `make check`) regenerates and
  `git diff`s — fails CI if either file is stale

## Alternatives considered

### A · Hand-maintained TS types (Phase 1 status quo)
- **Verdict**: rejected. Already failed in practice.

### B · gRPC / protobuf
- **Pro**: industry-standard cross-language schema
- **Con**: HTTP/JSON is the native FastAPI idiom; switching costs
  a build-system overhaul + tooling AI is less familiar with
- **Verdict**: rejected. We get 95% of the benefit with OpenAPI
  + zero migration cost.

### C · tRPC (TS-on-both-ends with shared schema)
- **Pro**: type sharing is automatic
- **Con**: assumes both ends are TS; we're Python on the server
- **Verdict**: rejected. tRPC requires committing to TS server.

### D · Tauri invoke commands instead of HTTP (typed via `tauri-specta`)
- **Pro**: stronger compile-time type guarantees (Rust → TS via
  specta vs Python → TS via OpenAPI)
- **Con**: locks the sim to Tauri shell; loses the ability to call
  the API from a curl test, a Marimo notebook, a second frontend.
  **Phase 2 explicitly considered this and chose the HTTP path** to
  preserve Python's reach
- **Verdict**: rejected for now. Not because it's bad — because
  it's wrong-priced for current goals. Revisit once production
  packaging (L-21) is the only deployment target.

## Consequences

**Positive**:
- Phase 2 + audit deletions: `WorldSnapshot.diversity`,
  `EventKindCount`, `ChronicleMarkdown` were all flagged at compile
  time when removed — no runtime errors at all
- New Pydantic field shows up in TS autocomplete after one
  `make schema` run
- AI tools see explicit types on both sides; no "guess what shape
  this dict has" debugging loop

**Negative**:
- Two artefacts to keep committed (`api-schema/openapi.json` +
  `api.generated.ts`) — partly mitigated by `make schema-check`
  catching drift before merge
- Adds `openapi-typescript` to dev deps + a Python script

**Style rules** (enforced via the schemas.py docstring):
- Every wire field is camelCase (Pydantic `alias_generator` or direct
  field naming)
- Optional fields end with `| None`; prefer `None` default over
  `Field(default=None)` unless a description is needed
- Routes return Pydantic instances, never raw dicts. Untyped dicts
  become `Any` in OpenAPI and AI loses the ability to reason about
  them

## Validation criteria

Revisit if:
1. We adopt Tauri invoke commands as the primary IPC (then this
   pipeline becomes redundant — replace with `tauri-specta`)
2. A second frontend (web app, mobile) needs the same schema, or
   external integrations use the API — the OpenAPI doc gets reused
   directly, validating the choice
3. `openapi-typescript` falls behind OpenAPI 3.1 spec evolution —
   at that point evaluate alternatives in the JS ecosystem
