# living-world

> `$GDRIVE` in this file = `~/Library/CloudStorage/GoogleDrive-kincc9999@gmail.com/My Drive` (macOS Google Drive mount path).

A no-player, auto-running virtual world simulator. Three worldviews — **SCP Foundation**, **Cthulhu Mythos**, **Liaozhai** — run side-by-side, each a self-contained pack of characters, events, and locations.

Agents move in continuous 2D space, interact, form relationships, accumulate consequences, and die. Local LLMs (via Ollama) enhance narrative at high-importance moments. A Streamlit dashboard renders a live map and chronicle log.

This repo contains the code, content packs, and tests. All design documents (architecture, roadmap, specs, ADRs) live in the shared vault at [`$GDRIVE/Living-World/design/`]($GDRIVE/Living-World/design/).

---

## Quick start

```bash
git clone https://github.com/Sloan-Great-Wall/living-world.git
cd living-world
./lw                   # creates venv, installs deps, launches dashboard
```

First run auto-installs dependencies. After that, `./lw` opens the dashboard at <http://localhost:8501>.

Other commands:

```bash
./lw dashboard         # default — launches the Streamlit UI
./lw run               # CLI simulation (no UI)
./lw digest            # CLI — print chronicle to terminal
./lw list-packs        # show available world packs
./lw test              # pytest suite
./lw install           # reinstall deps
```

---

## Using LLMs (optional)

```bash
brew install ollama
ollama pull gemma3:4b   # 3 GB, runs on any 16 GB MacBook
```

Then in the dashboard Settings panel (or `settings.yaml`):

- `tier2_provider: ollama`
- `tier3_provider: ollama`

Provider options are `"ollama"` and `"none"` (pure rules). If Ollama is unreachable, everything degrades gracefully to Tier 1 rule-based play.

---

## Adding a world pack

World content is data, not code. Each pack is a self-contained folder under `world_packs/` with `pack.yaml`, personas, events, and tiles (all YAML). Optional Chinese display overlays live under `locale/zh/`.

To add one:

```bash
mkdir -p world_packs/mypack/{personas,events,tiles}
# then write pack.yaml, persona/event/tile files
./lw run --packs mypack --days 10
./lw dashboard   # select 'mypack' in sidebar
```

See the existing `world_packs/scp/`, `world_packs/liaozhai/`, and `world_packs/cthulhu/` for complete reference packs.

---

## Where to find more

All design documentation lives in [`$GDRIVE/Living-World/design/`]($GDRIVE/Living-World/design/):

- `docs/product-direction.md` — positioning and direction rationale
- `docs/architecture.md` — full system architecture
- `docs/stat-machine-design.md` — consequence engine + tier routing
- `docs/flow-loops.md` — runtime flow diagrams
- `docs/tech-glossary.md` — terminology reference
- `docs/mvp-roadmap.md` — Stage A/B/C/D roadmap
- `docs/next-steps.md` — remaining Stage A work
- `docs/ui-redesign-spec.md` — Canvas map spec (planned)
- `docs/architecture-audit.md` / `docs/lbs-infrastructure.md` — deeper technical notes
- `adr/` — architecture decision records

Cross-project engineering principles live at [`$GDRIVE/Shared/`]($GDRIVE/Shared/).

---

## License

MIT for the code. Content packs follow their source licenses:

- SCP Foundation — CC BY-SA 3.0 (attribution required)
- Cthulhu Mythos (Lovecraft) — public domain
- Liaozhai Zhiyi — public domain
