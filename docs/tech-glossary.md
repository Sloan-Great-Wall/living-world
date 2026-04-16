# Technical Glossary

> Key terms used throughout the codebase and documentation.
> Last updated: 2026-04-16

---

## 1. Core Concepts

### Agent
A character in the world. Defined by a pydantic `Agent` model with: identity (agent_id, pack_id, display_name, persona_card), attributes (open dict per pack), tags, alignment, life_stage, age, position (current_tile + x/y coords), relationships, inventory, and current_goal. Agents are NOT LLM sessions -- they are data records that get fed to LLMs when importance warrants it.

### Persona Card
A short English text (< 500 chars) describing an agent's identity, background, and speaking style. Stored in `world_packs/<pack>/personas/<id>.yaml`. This is what the LLM reads to stay in character.

### Tile
A location in the world. Has x/y center coordinates, a radius, and belongs to a primary pack. Agents reside in tiles. Tiles control which packs' events can fire there.

### World Pack
A self-contained content directory (`world_packs/<id>/`) containing pack.yaml (manifest), personas/*.yaml, events/*.yaml, tiles/*.yaml, and optional locale overlays. Three ship with the project: SCP, Cthulhu, Liaozhai.

### World
The in-memory state object (`core/world.py`) holding all agents, tiles, and the event log. Single source of truth for the tick loop and dashboard.

### LegendEvent
A realized event -- what actually happened. Append-only. Contains participants, witnesses, outcome, stat/relationship changes, and up to three narrative renderings (template, enhanced, spotlight).

---

## 2. Tick & Simulation

### Tick
One discrete time step. Each tick represents one virtual day. The engine calls `TickEngine.step()` which runs movement, interactions, storyteller proposals, event resolution, consequences, and periodic maintenance.

### Tick Loop
The main simulation loop in `tick_loop.py`. Calls `step()` N times. Each step: movement -> interactions -> storyteller proposals -> dice-roll resolution -> consequence application.

### Phase
Substeps within a tick. Current phases (in order): Movement, Interactions, Storyteller proposals + Resolution, Consequences, Periodic tasks (demotion, reflection, snapshot).

---

## 3. Stat Machine & Consequences

### Storyteller
A per-tile event scheduler (`storyteller.py`) inspired by RimWorld's Cassandra/Phoebe/Randy. Has a personality (balanced/peaceful/chaotic), tracks a tension curve, respects cooldowns. Outputs 0-N EventProposals per tick.

### EventResolver
Takes an EventProposal + template, finds eligible participants in the tile, performs a D&D-style DC dice roll, applies stat/relationship changes, and produces a LegendEvent. Lives in `statmachine/resolver.py`.

### Importance Score
A 0.0-1.0 float computed by `score_event_importance()` in `resolver.py`. Primary signal is the event template's `base_importance`. Modifiers: spotlight event kinds, multiple historical figures, relationship changes, player proximity. Determines tier routing.

### Consequence Engine (`statmachine/consequences.py`)
The two-layer change system applied after every event:
- **Stat layer**: Numeric attribute changes (fear, morale, sanity...) + relationship deltas for witnesses. Fires on every qualifying event.
- **Description layer**: Rare mutations to agent identity -- tag changes, goal rewrites, life stage transitions. Guarded by attribute conditions + low probability.

No chain depth limit. Changes persist on agents, and the next tick naturally reacts.

### ConsciousnessLayer (`statmachine/conscious.py`)
LLM-driven per-event verdict. When activated (probabilistically, based on importance), asks the LLM whether a rule-proposed event should APPROVE, ADJUST (different outcome), or VETO. Overrides the dice roll when it fires.

### DebatePhase (`statmachine/conscious.py`)
Multi-agent LLM round for top-importance events. Orchestrator picks 3-5 stakeholders, each generates a first-person reaction via a worker LLM, then the orchestrator synthesizes a coherent narrative paragraph.

### Historical Figure
An agent flagged `is_historical_figure=True`. Gets finer simulation: participates in more events, gets periodic memory reflection, eligible for LLM-driven movement. Promotion/demotion managed by `HistoricalFigureRegistry`.

---

## 4. LLM Integration

### Tier 1 (Rules)
Pure Python. Template-based narrative rendering. Zero LLM cost. Handles 95%+ of all events.

### Tier 2 (Local LLM)
Ollama-backed. Used for narrative enhancement of medium-importance events. Default model: `gemma3:4b`.

### Tier 3 (Local or Cloud LLM)
Ollama-backed (same or different model). Used for dynamic dialogue, debate phase synthesis, conscious override. Default model: `gemma3:4b` (swap to larger model on GPU hardware).

### EnhancementRouter (`llm/router.py`)
Routes events to Tier 1/2/3 based on importance score and budget constraints. Handles auto-downgrade when daily token limits are hit.

### OllamaClient (`llm/ollama.py`)
The only real LLM client implementation. Connects to Ollama's `/api/generate` endpoint. Used for Tier 2, Tier 3, translation, embedding, movement advice, and consciousness queries.

### Provider
Either `"ollama"` or `"none"`. Set per tier in `settings.yaml`. No mock clients exist.

---

## 5. Language & Locale

### Locale Overlay (`locale.py`)
Chinese (or other language) display values for static YAML content. Lives in `world_packs/<pack>/locale/zh/`. Provides localized display_name, persona_card, event templates without changing the English source of truth.

### i18n Translation (`i18n.py`)
Runtime translation of LLM-generated text. Uses OllamaTranslator (reuses small Ollama model for en->zh translation) or NoopTranslator (passthrough). Controlled by `display.locale` and `display.translate_generated` settings.

### English Source of Truth
All YAML content (personas, events, tiles) and all LLM prompts are in English. This simplifies model selection (no Chinese capability requirement) and makes testing against standard English benchmarks straightforward.

---

## 6. Persistence & Memory

### Repository (`persistence.py`)
Protocol for world state persistence. Two implementations: MemoryRepository (in-memory, default) and PostgresRepository (pgvector-backed, optional).

### AgentMemoryStore (`memory/memory_store.py`)
Episodic memory backed by embeddings. Agents remember events they participated in. Periodic reflection compresses recent memories into narrative summaries for historical figures.

### Embedding
Vector representation of text for semantic search. Uses OllamaEmbedder with `nomic-embed-text` model by default.

---

## 7. UI

### Dashboard
Streamlit-based web UI (`dashboard/app.py`). Shows: SVG world map, chronicle log, agent cards, codex (story library). Launched via `./lw` or `./lw dashboard`.

### SVG Grid Map
Current map renderer (`dashboard/map_view.py`). Tiles as circles with agent dots. No zoom/pan.

### Canvas World Map (PLANNED)
Designed in [ui-redesign-spec.md](ui-redesign-spec.md) but not yet implemented. Would replace SVG with a Streamlit custom React component using HTML5 Canvas for smooth animation, zoom/pan, and click-to-inspect.

---

## 8. Key References

- [Generative Agents: Interactive Simulacra (Park et al. 2023)](https://arxiv.org/abs/2304.03442)
- [Generative Agent Simulations of 1000 People (Park et al. 2024)](https://arxiv.org/abs/2411.10109)
- [Effective context engineering for AI agents -- Anthropic](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents)
