# UI Redesign Spec — Canvas World Map + Dashboard Reflow

> Status: **Ready to implement** — all data model changes done, awaiting frontend build.
> Created: 2026-04-16

---

## 1. Current state (what's wrong)

- World map is **SVG grid of rectangle tiles** — static, no animation, no zoom/pan
- Agents rendered as circles in grid cells — doesn't feel like a living world
- Dashboard layout is **Streamlit-native widgets stacked vertically** — not a game UI
- Chronicle and agent cards are CSS-hacked `position:fixed` divs that fight Streamlit

## 2. Target experience

A **top-down 2D world map** that fills the main area:
- **Continuous space** — tiles are circular/organic regions, not grid boxes
- **Agents move** between regions with smooth interpolation (not teleporting between ticks)
- **Click any agent** → their card appears as an overlay panel
- **Zoom + pan** — scroll to zoom, drag to pan the world
- **Live animation** — when auto-play is on, agents drift between positions each tick
- **Pack regions** visually distinct (SCP = cold blue, Liaozhai = warm amber, Cthulhu = purple)

### Reference aesthetics
- Starfield's galaxy map (node-based, floating labels, subtle glow)
- Rimworld's colony view (top-down, agents as small figures moving on terrain)
- Dwarf Fortress (2024) with Kitfox tileset (rooms visible, characters moving)

## 3. Technical approach

### Streamlit Custom Component (React + Canvas)

Streamlit can't do real-time Canvas natively. The solution is a **custom component**:

```
living_world/
  dashboard/
    worldmap/                    ← new React component
      __init__.py                ← Python wrapper (st_worldmap)
      frontend/
        package.json
        src/
          WorldMap.tsx           ← main React component
          Canvas.tsx             ← HTML5 Canvas rendering
          types.ts               ← WorldState interface
        build/                   ← compiled JS (committed for easy install)
```

**Data flow**:
```
Python (tick_loop) → WorldState JSON → Streamlit component args → React → Canvas
                                                                        ↑
                                                                  user clicks
                                                                        ↓
                                                          component returns clicked agent_id
                                                                        ↓
                                                          Python reads via component return value
```

### WorldState JSON interface

```typescript
interface WorldState {
  tick: number;
  packs: string[];

  tiles: Array<{
    tile_id: string;
    display_name: string;
    primary_pack: string;
    tile_type: string;
    x: number;         // world coordinates
    y: number;
    radius: number;
  }>;

  agents: Array<{
    agent_id: string;
    display_name: string;
    pack_id: string;
    is_historical_figure: boolean;
    is_alive: boolean;
    tags: string[];
    current_tile: string;
    x: number;         // position within tile
    y: number;
    // For the info card
    persona_card: string;
    current_goal: string | null;
    life_stage: string;
    age: number;
    attributes: Record<string, number | string>;
  }>;

  recent_events: Array<{
    event_id: string;
    tick: number;
    pack_id: string;
    event_kind: string;
    importance: number;
    tier_used: number;
    narrative: string;
    participants: string[];
  }>;

  selected_agent: string | null;
}
```

### Canvas rendering layers (bottom to top)

1. **Background** — dark gradient matching pack theme regions
2. **Tile regions** — semi-transparent circles with pack-colored borders, tile names
3. **Connections** — faint lines between tiles agents frequently travel between
4. **Agents** — small circles/icons with glow for HF, positioned at x/y within their tile region
5. **Labels** — agent names below their circles (toggle-able)
6. **Selection ring** — golden highlight around selected agent
7. **Event particles** — brief flash/ripple when events happen (optional, nice-to-have)

### Interaction

- **Click agent** → component returns `{agent_id: "..."}` → Python shows agent card
- **Scroll** → zoom in/out (Canvas transform)
- **Drag** → pan (Canvas transform)
- **Hover agent** → tooltip with name + current goal

### Dashboard layout reflow

```
┌─────────────────────────────────────────────────────┐
│ SIDEBAR (Streamlit native)                           │
│ ├─ Living World α                                    │
│ ├─ Stats: Day / Events / Agents / HF                │
│ ├─ Simulation controls (packs, days, seed, play)     │
│ ├─ Inspect agent (selectbox, fallback)               │
│ ├─ Story Library                                     │
│ └─ Settings                                          │
├─────────────────────────────────────────────────────┤
│ MAIN AREA (full width)                               │
│                                                      │
│ ┌──────────────────────────────────────────────────┐ │
│ │ Canvas World Map (custom component)               │ │
│ │ — fills all available space                       │ │
│ │ — zoom/pan/click                                  │ │
│ │                                                    │ │
│ │                                                    │ │
│ │                                                    │ │
│ └──────────────────────────────────────────────────┘ │
│                                                      │
│ ┌──────────────┐ ┌──────────────────────────────────┐│
│ │ Agent Card   │ │ Chronicle                         ││
│ │ (if selected)│ │ (scrolling event log)             ││
│ │              │ │                                    ││
│ └──────────────┘ └──────────────────────────────────┘│
└─────────────────────────────────────────────────────┘
```

Bottom panels are **native Streamlit** (st.columns + st.markdown) — only the
world map is a custom component. This minimizes React code.

## 4. Implementation plan

### Phase 1 — Python side (data pipeline)

- [ ] `dashboard/worldmap/__init__.py` — `st_worldmap(state: WorldState) -> dict | None`
- [ ] `factory.py` — `build_world_state_json(world, settings) -> dict`
  Serializes World + recent events into the JSON shape above.
- [ ] `app.py` reflow — replace SVG block with `st_worldmap()` call

### Phase 2 — React component

- [ ] `dashboard/worldmap/frontend/` scaffold (Create React App or Vite)
- [ ] `WorldMap.tsx` — receives `args.state`, renders Canvas
- [ ] `Canvas.tsx` — 5-layer render loop + zoom/pan transform
- [ ] Click handler → `Streamlit.setComponentValue({agent_id: "..."})`
- [ ] Build → `frontend/build/` (committed so pip install works without Node)

### Phase 3 — Agent card + Chronicle reflow

- [ ] Agent card as floating overlay (absolute position over bottom-left)
- [ ] Chronicle as floating overlay (absolute position over bottom-right)
- [ ] Both use glassmorphism CSS from current `styles.css`
- [ ] Remove old SVG map_view.py (replaced by Canvas)

### Phase 4 — Polish

- [ ] Smooth agent position interpolation between ticks (lerp in requestAnimationFrame)
- [ ] Event particle effects (optional)
- [ ] Minimap in corner (optional)
- [ ] Pack-themed region backgrounds (SCP blue, Liaozhai amber, Cthulhu purple)

## 5. Prerequisites already done

- [x] Tile has x/y/radius coordinates
- [x] Agent has x/y coordinates
- [x] world_pack.py auto-layouts tiles
- [x] Settings has display.locale for i18n
- [x] All content is English source + zh overlay
- [x] 24/24 tests green

## 6. Estimated effort

| Phase | Time | Blocking? |
|---|---|---|
| Phase 1 (Python) | 1 hour | No |
| Phase 2 (React) | 4-6 hours | Yes — needs Node.js for build |
| Phase 3 (Reflow) | 2 hours | After Phase 2 |
| Phase 4 (Polish) | 2-4 hours | Nice-to-have |

Total: **~10-14 hours** for the full Canvas experience.

Alternative: if Node.js setup is too heavy, we could use **Pyodide + raw HTML5 Canvas in st.html()** — no React, no build step, just JavaScript in a string. Less maintainable but faster to prototype (~4 hours total).
