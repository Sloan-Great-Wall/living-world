# living-world

A no-player, auto-running virtual-world simulator. Three worldviews —
**SCP Foundation**, **Cthulhu Mythos**, **Liaozhai** — run side by side,
each a self-contained pack of characters, events, and locations.

Agents move in 2D space, interact, form relationships, accumulate
consequences, and die. Local LLMs (via Ollama) enhance narrative at
high-importance moments. A Tauri + Solid + TypeScript dashboard renders
a live map, social graph, and chronicle log.

> `$GDRIVE` in this file = `~/Library/CloudStorage/GoogleDrive-kincc9999@gmail.com/My Drive` (macOS Google Drive mount path).

---

## Architecture (one-paragraph version)

Three layers, each in its strongest language:

| Layer | Language | Job |
|---|---|---|
| **Sim core + LLM orchestration** | Python | tick engine · agents · Ollama |
| **Desktop shell + IPC** | Rust + Tauri | window + future WASM compute slot |
| **UI + client-side compute** | TypeScript + Solid | dashboard + sim-core mirrored functions |

Cross-layer contract is compile-time strict:
`Pydantic schemas → OpenAPI → openapi-typescript → tsc --noEmit`. Any
field rename red-lines the consumer at build time. See
[`docs/HISTORY.md`](docs/HISTORY.md) for how we got here, and
[`KNOWN_ISSUES.md`](KNOWN_ISSUES.md) for what's open.

---

## Quick start

```bash
git clone https://github.com/Sloan-Great-Wall/living-world.git
cd living-world
make install                 # uv pip install -e .[dev]  +  npm install
```

`make install` uses `uv` if present (10× faster than pip) and falls
back to pip otherwise. Both Python and npm workspaces install in one
shot.

### Run the simulation

There are three "complete simulation" entry points, in increasing
fidelity:

```bash
# 1. Fastest — rules-only, no LLM, ~3 seconds, asserts 9 invariants
make smoke

# 2. CLI smoke run with whatever LLM stack is configured (real Ollama
#    if up; rules-only otherwise). Streams events to terminal.
lw smoke --ticks 8 --packs scp,liaozhai,cthulhu

# 3. Full UI — Python sim + dashboard + live tick streaming
ollama serve              &  # terminal A — start LLM daemon
lw serve                  &  # terminal B — FastAPI sim API on :8000
npm run tauri dev --workspace=dashboard-tauri  # terminal C — desktop UI
```

Once the dashboard is up:
- Click **Bootstrap** with the packs you want loaded
- Hit **Tick** or **Play** to advance days
- Open **📚 Library** for the codex / chronicle / **Social** graph
  (Social tab runs entirely client-side via @living-world/sim-core)

### Verify the whole repo

```bash
make check
```

Runs all gates — ruff format + lint, basedpyright strict, pytest (84
+ live Ollama if available), schema drift check, vitest (38 parity
tests), dashboard typecheck + Vite build, bundle-size budget. Exit 0/1.
Anything red here is a regression.

---

## Using LLMs

```bash
brew install ollama
ollama pull llama3.2:3b   # tier 2, ~2 GB
ollama pull gemma3:4b     # tier 3, ~3.3 GB
```

Then in `settings.yaml`:

```yaml
llm:
  tier2_provider: ollama
  tier3_provider: ollama
```

Provider options are `"ollama"` and `"none"`. If Ollama is unreachable,
the sim degrades gracefully to Tier-1 rule-based play (typed
`LLMError` taxonomy preserves the failure kind for debugging).

---

## CLI reference

```
lw smoke              run + invariants check; primary regression command
lw run                CLI simulation (10 days, 3 packs by default)
lw digest             章回体 digest grouped by pack
lw export-chronicle   write chapters to Markdown
lw test               pytest + smoke combined
lw serve              FastAPI sim API for the Tauri dashboard
lw social             social-network metrics over the affinity graph
lw list-packs         show available packs
```

`make smoke` and `lw smoke` differ by scope: `make smoke` is rules-only
(deterministic, fast); `lw smoke` is whatever your `settings.yaml`
configures (real Ollama if up).

---

## Adding a world pack

World content is data, not code. Each pack is a self-contained folder
under `world_packs/` with `pack.yaml`, personas, events, tiles (all
YAML). Optional Chinese display overlays live under `locale/zh/`.

```bash
mkdir -p world_packs/mypack/{personas,events,tiles}
# write pack.yaml, persona/event/tile files
lw smoke --packs mypack --ticks 8
```

See `world_packs/scp/`, `world_packs/liaozhai/`, `world_packs/cthulhu/`
for reference packs.

---

## Repository layout

```
living_world/         Python sim core (engine, agents, LLM, web API)
tests/                Python tests (unit / property / invariant / smoke)
packages/sim-core/    @living-world/sim-core — pure-function TS port
                      (dice / heat / queries / socialMetrics)
dashboard-tauri/      Tauri + Solid + Vite desktop UI
api-schema/           OpenAPI schema (generated; cross-layer source of truth)
world_packs/          YAML content packs (scp · liaozhai · cthulhu)
scripts/              Maintenance scripts (e.g. dump_openapi.py)
docs/                 In-repo docs (HISTORY.md so far; architecture.md TBD)
reports/              Marimo notebooks for batch analysis
```

---

## Where to find more

- [`KNOWN_ISSUES.md`](KNOWN_ISSUES.md) — open bugs + active backlog
- [`docs/HISTORY.md`](docs/HISTORY.md) — phase log + design retrospectives
- [`packages/sim-core/README.md`](packages/sim-core/README.md) — port rationale + parity-test workflow
- External design vault: [`$GDRIVE/Living-World/design/`]($GDRIVE/Living-World/design/)

---

## License

MIT for the code. Content packs follow their source licenses:

- SCP Foundation — CC BY-SA 3.0 (attribution required)
- Cthulhu Mythos (Lovecraft) — public domain
- Liaozhai Zhiyi — public domain
