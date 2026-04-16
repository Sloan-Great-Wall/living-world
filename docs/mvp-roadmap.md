# MVP to Mature Product Roadmap

> Current scope (2026-04-16): **Stage A -- no-player auto-running world simulator**.
> Stage B/C/D preserved as long-term direction. No work on them until Stage A exits.
> See [next-steps.md](next-steps.md) for the immediate task list.

---

## Macro Roadmap

```
Stage A: No-player virtual world simulator
  (backend + dashboard, world runs itself)
  Core question: can it generate compelling stories with no human input?
         │
         ▼
Stage B: Player-facing text adventure (DnD feel)
  (web client, text + dice + map, no AR/LBS)
  Core question: is it fun to play?
         │
         ▼
Stage C: AR world simulator
  (mobile native, real-world LBS, DnD feel preserved)
  Core question: does the experience survive the move to mobile?
         │
         ▼
Stage D: AR game layer
  (collection, bonding, PvE/PvP, monetization)
  Core question: can it sustain daily engagement?
```

**Gate rule**: Stage A must prove the simulation is compelling before any Stage B work begins. If the auto-sim is boring, no amount of UI polish saves it.

---

## Stage A -- No-Player World Simulator (CURRENT)

### What Is Built

See [architecture.md](architecture.md) for the full system layout. Summary:

- 3 world packs (SCP, Cthulhu, Liaozhai): 61 personas, 105 events, 30 tiles
- Full tick engine: movement -> interactions -> storyteller -> resolver -> consequences
- Two-layer consequence engine (stat ripples + description mutations, no chain depth limit)
- ConsciousnessLayer + DebatePhase (LLM overlays, merged in `conscious.py`)
- Importance scoring + tier routing (merged into `resolver.py`)
- Ollama LLM backend (only provider; mock clients removed)
- Language isolation: English source, Chinese locale overlays, i18n translation
- Streamlit dashboard with SVG map, chronicle, agent cards, codex
- Persistence: in-memory (default) + PostgreSQL (optional)
- Agent memory: episodic + periodic reflection for historical figures
- Continuous-space map: x/y coords on agents and tiles
- factory.py for shared bootstrap (CLI + dashboard)
- 24 tests, all green

### Exit Criteria

- [ ] 100 virtual days unattended, no crashes
- [ ] 500+ daily legend events, 20+ spotlight
- [ ] Non-developers find the stories memorable (10+ NPCs stick)
- [ ] Tier 1 >= 95% of events, Tier 3 within daily budget

### Remaining Work

See [next-steps.md](next-steps.md) for detailed task lists. Main gaps: content expansion, canvas map, long-run stability testing, observability.

---

## Stage B -- Player Text Adventure (DnD Feel)

### Target
10 internal testers play a text-based RPG in the living world. Web client, no AR.

### Key Features (planned, not started)
- Player account + character creation (DnD-style attributes/class)
- Free-text dialogue with agents (LLM-powered via Tier 3)
- Dice rolls + DC checks visible to player
- Per-player memory scope (agents remember each player separately)
- GM narrator voice (Tier 3 LLM as game master)
- Offline event notifications (what happened while you were away)
- World pack selection at session start

### Exit Criteria
- 30-day retention >= 40% among 10 testers
- Session length >= 25 minutes average
- 80% of players can name "their NPC story"
- Per-player monthly cost < budget target

---

## Stage C -- AR World Simulator

### Target
Move Stage B experience to mobile with real-world LBS. DnD feel preserved.

### Key Features (planned, not started)
- iOS-first native app (Swift + ARKit + map SDK)
- GPS-based tile activation
- Basic AR rendering (2D sprites in camera view)
- Android follow-up (ARCore)
- Anti-cheat (GPS spoofing detection)

### Exit Criteria
- iOS + Android available, first city coverage complete
- Physical exploration rate > 50%
- DnD feel intact on mobile
- 30-day retention >= 25%

---

## Stage D -- AR Game Layer

### Target
Add collection, bonding, PvE/PvP, and monetization on top of Stage C.

### Key Features (planned, not started)
- Agent bonding system (not capture -- relationship depth)
- PvE story battles using debate phase
- PvP via opposing agent debates
- UGC pipeline for player-created agents/events
- Monetization (encounter tickets, premium tiers, cosmetics)

### Exit Criteria
- DAU/MAU >= 25%
- Paid conversion >= 3%
- NPS >= 40
- Player-generated content >= 10% of total

---

## Key Risks

| Stage | Risk | Mitigation |
|---|---|---|
| A | Event pool too small for variety | Expand to 60+ events per pack; tune storyteller tension |
| A | Tier distribution off target | Calibrate base_importance; adjust thresholds |
| B | "Just a chatbot" feeling | Strong dice/DC mechanics, visible stat changes |
| B | Retention below threshold | Strengthen offline hooks (letters, dreams, consequences) |
| C | LBS ops cost | Start small (one city district), validate before expanding |
| D | Regulatory (game license) | Begin application during Stage B; backup: overseas launch first |
| All | LLM provider instability | Architecture supports provider swap via settings.yaml |

---

## The One Rule

**If Stage A's auto-simulation is not compelling, do not advance to Stage B.** Living world products succeed or fail on whether the simulation itself is interesting. Dwarf Fortress, Taiyi, and Smallville all proved this: the world must be worth watching before it is worth playing in.
