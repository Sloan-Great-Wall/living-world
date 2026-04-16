# Next Steps -- Remaining Stage A Work

> What remains before Stage A exit criteria are met.
> Last updated: 2026-04-16

---

## Stage A Exit Criteria (unchanged)

All four must pass:

- [ ] World runs **100 virtual days** unattended without crashing
- [ ] Daily output: **500+ legend events**, 20+ spotlight-level
- [ ] Team non-developers read a week of digest and remember 10+ NPC stories
- [ ] **Tier 1 >= 95%** of total events; Tier 3 daily spend < budget cap

---

## What Is Done

| Area | Status |
|---|---|
| World pack system (3 packs, YAML-driven) | Done |
| Stat machine: storyteller + resolver + importance | Done |
| Consequence engine (two-layer: stat + description) | Done |
| ConsciousnessLayer + DebatePhase | Done |
| LLM integration (Ollama only, mock removed) | Done |
| Language isolation (English source, zh overlays, i18n) | Done |
| Persistence (memory + Postgres, merged module) | Done |
| Memory system (episodic + reflection) | Done |
| Continuous-space map (x/y coords) | Done |
| Dashboard (Streamlit, SVG map, chronicle, codex) | Done |
| Factory module (shared bootstrap for CLI + dashboard) | Done |
| 24 tests | Done |

---

## What Remains

### S1: Content Expansion

Current content is functional but thin (61 personas, 105 events). To hit 500+ daily events with narrative variety:

- [ ] **S1.1** Expand each pack to 40-50 personas (currently 20-21 each)
- [ ] **S1.2** Expand event pools to 60+ per pack (currently 33-36 each)
- [ ] **S1.3** Add cross-pack events for mixed-mode runs
- [ ] **S1.4** Tune `base_importance` values so tier distribution matches targets
- [ ] **S1.5** Complete Chinese locale overlays for all new content

### S2: Canvas World Map

The SVG grid map is functional but not engaging. Design spec exists at `docs/ui-redesign-spec.md`.

- [ ] **S2.1** Build Streamlit custom component (React + Canvas)
- [ ] **S2.2** Smooth agent movement animation between ticks
- [ ] **S2.3** Zoom + pan
- [ ] **S2.4** Click-to-inspect agent cards
- [ ] **S2.5** Pack-specific region coloring (SCP=blue, Liaozhai=amber, Cthulhu=purple)

### S3: Long-Run Stability

- [ ] **S3.1** Run 100-day stress test across all three packs
- [ ] **S3.2** Profile memory usage over long runs (event log growth)
- [ ] **S3.3** Verify Postgres persistence survives dashboard restarts
- [ ] **S3.4** Add event log compaction or archival for runs > 100 days

### S4: Observability

- [ ] **S4.1** Per-tier call counts and latency tracking in dashboard
- [ ] **S4.2** Daily token spend display
- [ ] **S4.3** Consequence engine stats (stat ripples, mutations fired)
- [ ] **S4.4** Consciousness layer stats (activations, approvals, adjustments, vetoes)

### S5: Cloud LLM Preparation

Not needed for Stage A exit, but architecture is ready:

- [ ] **S5.1** Add OpenAI-compatible client for cloud APIs (DeepSeek V3, Gemma 4)
- [ ] **S5.2** Per-tier provider configuration (different models for Tier 2 vs Tier 3)
- [ ] **S5.3** Prompt cache configuration for cloud providers

### S6: Test Coverage

- [ ] **S6.1** Test consciousness layer verdict parsing edge cases
- [ ] **S6.2** Test debate phase with mock LLM responses
- [ ] **S6.3** Integration test: 30-day run with all packs, verify no crashes
- [ ] **S6.4** Test locale overlay loading for all three packs

---

## Priority Order

1. **S1 (Content)** + **S3 (Stability)** -- directly gate exit criteria
2. **S4 (Observability)** -- needed to verify tier distribution targets
3. **S2 (Canvas Map)** -- improves demo quality but not required for exit
4. **S6 (Tests)** -- ongoing, expand alongside features
5. **S5 (Cloud LLM)** -- Stage B preparation, not Stage A blocker
