# Docs — Living World Simulator

Project design documentation index.

## Document List (suggested reading order)

| # | Document | Contents | After reading you can answer |
|---|---|---|---|
| 1 | [product-direction.md](product-direction.md) | Product positioning, Direction A rationale, market decisions | What is this product, why these choices |
| 2 | [architecture.md](architecture.md) | System architecture, data flow, tech choices | How the system is structured end-to-end |
| 3 | [tech-glossary.md](tech-glossary.md) | Key terms (tick, agent, consequence, conscious, ...) | Shared vocabulary for the team |
| 4 | [stat-machine-design.md](stat-machine-design.md) | Two-layer consequence engine + tier routing | How the world self-runs, how costs stay low |
| 5 | [flow-loops.md](flow-loops.md) | Core flow diagrams | What happens at runtime each tick |
| 6 | [mvp-roadmap.md](mvp-roadmap.md) | Stage A/B/C/D full roadmap | From MVP to mature product |
| 7 | [next-steps.md](next-steps.md) | Remaining Stage A work streams | What to build next |
| 8 | [ui-redesign-spec.md](ui-redesign-spec.md) | Canvas world map design (planned, not yet built) | Where the UI is headed |

## Current Scope

- **Stage A MVP**: no-player, non-VR, auto-running virtual world simulator
- **Worldviews**: SCP + Cthulhu + Liaozhai -- three independent world packs, run alone or mixed
- **LLM backend**: Ollama (local) or "none" (pure rules). No mock clients.
- **Language**: English source-of-truth in `world_packs/*.yaml`, Chinese overlays in `world_packs/*/locale/zh/`, display locale controlled by `display.locale` setting
- **LLM features**: All default ON -- dynamic_dialogue, debate, conscious_override, llm_movement
- **Repo**: [github.com/Sloan-Great-Wall/living-world](https://github.com/Sloan-Great-Wall/living-world), main branch
- **Launch**: `./lw`
- **Tests**: 24 tests, all green

## Maintenance Principles

- After any substantive decision, update the relevant doc immediately -- docs = current truth
- Deprecated decisions are not deleted; mark as ~~deprecated~~ or archive to a new section to preserve the decision trail
- New topics: write the doc first, then write the code
