# Product Direction Decision Record

> Status: **Direction A selected** -- consumer-facing, gamified, LBS-anchored living-world AI agent network.
> Last updated: 2026-04-16

---

## 1. Decision Summary

### Direction A: Spatial Living World

> A real-world living NPC network -- every location hosts AI agents with memory, personality, relationships, and an offline life. Players interact through DnD-style text encounters.

Inspirations: Dwarf Fortress (emergent simulation), RimWorld (storyteller-driven events), Taiyi/Guigubahuang (offline agent evolution), BG3 (NPC depth).

### Why A

Team DNA leans C-end gaming. B-end decision simulation and bare API platform archived as potential pivot paths.

---

## 2. Core Experience Loop

1. **Discover** -- agents populate tiles; player finds them by exploring
2. **Meet & Bond** -- dialogue builds relationships, agents remember per-player
3. **Entangle** -- agents have goals (shop, revenge, research); player may intervene
4. **Absent Evolution** -- while player is away, agents interact, accumulate consequences, evolve
5. **Return & React** -- world has changed; agents reference what happened in player's absence

---

## 3. Current Implementation Status (Stage A)

Stage A is a no-player, auto-running simulator. The world generates its own stories.

### What is built and working:
- Three world packs (SCP, Cthulhu, Liaozhai) with 61 personas, 105 event templates, 30 tiles
- Full stat machine: storyteller -> resolver -> consequences -> tier routing
- Two-layer consequence engine (stat ripples + description mutations, no chain depth limit)
- ConsciousnessLayer + DebatePhase (merged into `conscious.py`)
- Ollama LLM integration (only backend; mock clients removed)
- Language isolation: English source-of-truth, Chinese locale overlays, translation layer
- Continuous-space map (x/y on agents and tiles), SVG renderer
- Streamlit dashboard with chronicle, agent cards, codex
- Persistence (in-memory + Postgres options, merged into single `persistence.py`)
- 24 tests, all green
- All LLM features default ON (dynamic_dialogue, debate, conscious_override, llm_movement)

### What is designed but not built:
- Canvas world map (spec at `docs/ui-redesign-spec.md`)
- Cloud LLM providers (DeepSeek, Qwen-Max -- architecture supports OpenAI-compatible endpoints)
- Player interaction (Stage B)
- AR/LBS (Stage C+)

---

## 4. Worldview Strategy

Three world packs run independently or mixed:

| Pack | Tone | Personas | Events |
|---|---|---|---|
| SCP Foundation | Cold procedural horror | 21 | 36 |
| Cthulhu Mythos | Gothic cosmic dread | 20 | 33 |
| Liaozhai | Warm supernatural folklore | 20 | 36 |

Each pack includes `locale/zh/` overlays for Chinese display names and templates.

Cross-pack events fire only when multiple packs are loaded simultaneously.

---

## 5. Technical Positioning

| Decision | Choice | Rationale |
|---|---|---|
| LLM backend | Ollama only (or "none") | Simple, local-first, no vendor lock-in |
| Content language | English source of truth | Decouples model selection from language capability |
| Display language | Locale overlay system | Add languages without changing source content |
| Consequence model | Two-layer, no recursion | Natural cross-tick chains, easy to reason about |
| Code structure | Flat modules | No deep subpackage nesting; everything findable |
| Persistence | Protocol + two impls | MemoryRepository for dev, PostgresRepository for prod |

---

## 6. Non-goals (what we do NOT build)

- B-end decision simulation (archived Direction B)
- Bare API platform (archived Direction C)
- Pokemon-style collection/battle (not our differentiator)
- High-stakes LLM output (financial/legal advice)
- Real-person personas (privacy concerns)
- AR/mobile (Stage C+, not until Stage A/B prove the simulation is compelling)
