"""Streamlit dashboard — modern editorial aesthetic, all settings in sidebar, map center."""

from __future__ import annotations

import html as _html
from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components


try:
    from streamlit_autorefresh import st_autorefresh
except ImportError:
    st_autorefresh = None

from living_world.config import DEFAULT_SETTINGS_PATH, Settings, load_settings, save_settings
from living_world.factory import (
    bootstrap_world,
    build_world_state_json,
    group_events_by_day,
    make_engine,
)
from living_world.tick_logger import TickLogger
from living_world.dashboard.canvas_map import render_canvas_map
from living_world.dashboard.codex import (
    render_persona_codex_html,
    render_story_codex_html,
    render_tiles_codex_html,
)
from living_world.dashboard.controls import render_controls_page
from living_world.dashboard.map_view import (
    PACK_THEMES,
    _agent_emoji,
)
from living_world.llm.ollama import OllamaClient
from living_world.world_pack import load_all_packs


def esc(s: str | None) -> str:
    return _html.escape(s or "—")


_settings = load_settings()
st.set_page_config(
    page_title="Living World",
    layout="wide",
    initial_sidebar_state="expanded",
    menu_items=None,
)

# ============ Typography + styling ============
# Headings: Space Grotesk · Body: Inter · Data: JetBrains Mono · Chinese: Noto Sans SC
# Material Symbols is loaded explicitly so Streamlit's built-in icon glyphs render.

# ============ Load dark-theme stylesheet from external file ============
_STYLES = (Path(__file__).parent / "styles.css").read_text()
st.markdown(f"<style>{_STYLES}</style>", unsafe_allow_html=True)

from living_world import PACKS_DIR as DEFAULT_PACKS_DIR

# ============ Session state ============
if "world" not in st.session_state:
    st.session_state.world = None
    st.session_state.engine = None
    st.session_state.selected_agent = None
    st.session_state.loaded_packs = None
    st.session_state.playing = False
    st.session_state.play_speed = 2  # seconds per tick
    st.session_state.show_settings = False
    st.session_state.show_controls = False
    st.session_state.show_codex = False


def _reset() -> None:
    # Close the logger file handle if one is open, so we don't leak fds
    # and so the next run starts a clean log.
    old_logger = st.session_state.get("tick_logger")
    if old_logger is not None:
        try:
            old_logger.close()
        except Exception:
            pass
    for k in ["world", "engine", "selected_agent", "loaded_packs", "tick_logger"]:
        st.session_state[k] = None
    st.session_state.playing = False


@st.cache_data(show_spinner=False)
def _discover_all_packs():
    pack_ids = sorted(
        p.name for p in DEFAULT_PACKS_DIR.iterdir()
        if p.is_dir() and (p / "pack.yaml").exists()
    )
    return load_all_packs(DEFAULT_PACKS_DIR, pack_ids), pack_ids


_all_packs, _all_pack_ids = _discover_all_packs()


# ============ SIDEBAR — Everything here ============
ollama_ok = OllamaClient(base_url=_settings.llm.ollama_base_url).available()

with st.sidebar:
    # ─── Brand header (minimal) ───
    st.markdown(
        "<div style='display:flex;align-items:center;gap:10px;margin:4px 0 18px 0'>"
        "<div style='font-family:\"Space Grotesk\";font-size:22px;font-weight:600;"
        "color:#f2f4f8;letter-spacing:-0.022em'>Living World</div>"
        "<div class='pill' style='background:#1a1d26;color:#8a8f9c'>α</div>"
        "</div>",
        unsafe_allow_html=True,
    )

    # ─── World stats (only when running) ───
    if st.session_state.world is not None:
        s = st.session_state.world.summary()
        c1, c2 = st.columns(2)
        c1.metric("Day", s["tick"])
        c2.metric("Events", s["events_logged"])
        c3, c4 = st.columns(2)
        c3.metric("Agents", s["agents_alive"])
        c4.metric("HF", s["historical_figures"])
        st.markdown("---")

    # ═══════════════════════════════════════════════════════
    # SIMULATION panel — one cohesive block
    # ═══════════════════════════════════════════════════════
    st.markdown(
        "<div class='section-label' style='margin-bottom:12px'>Simulation</div>",
        unsafe_allow_html=True,
    )

    # Worlds (checkboxes)
    st.markdown(
        "<div class='field-label'>Worlds</div>",
        unsafe_allow_html=True,
    )
    _defaults_source = (
        st.session_state.loaded_packs
        or [p for p in _settings.simulation.default_packs if p in _all_pack_ids]
    )
    selected_packs: list[str] = []
    _pack_emoji = {p.pack_id: PACK_THEMES.get(p.pack_id, PACK_THEMES["scp"])["emblem"]
                    for p in _all_packs}
    for pid in _all_pack_ids:
        label = f"{_pack_emoji.get(pid, '●')}  {pid}"
        if st.checkbox(label, value=(pid in _defaults_source), key=f"pack_{pid}"):
            selected_packs.append(pid)

    # Days + Seed on one row
    st.markdown(
        "<div class='field-label' style='margin-top:14px'>Days per Run &nbsp;·&nbsp; Random seed</div>",
        unsafe_allow_html=True,
    )
    c_sl1, c_sl2 = st.columns(2)
    with c_sl1:
        step_days = st.number_input(
            "days_label", min_value=1, max_value=365, value=10, step=1,
            label_visibility="collapsed",
            help="Virtual days to advance per Run / per auto-Play tick.",
        )
    with c_sl2:
        seed = st.number_input(
            "seed_label", value=_settings.simulation.default_seed, step=1,
            label_visibility="collapsed",
            help="Same seed + same setup reproduces the same history.",
        )

    st.markdown("<div style='height:10px'></div>", unsafe_allow_html=True)

    # Single primary action: Start (first time = bootstrap + play),
    # toggle to Pause when running.
    if st.session_state.world is None:
        if st.button("▶  Start simulation", type="primary",
                     width="stretch", disabled=not selected_packs):
            world, loaded = bootstrap_world(DEFAULT_PACKS_DIR, selected_packs)
            st.session_state.world = world
            st.session_state.tick_logger = TickLogger("logs/tick.log")
            st.session_state.engine = make_engine(world, loaded, _settings, int(seed), tick_logger=st.session_state.tick_logger)
            st.session_state.loaded_packs = selected_packs
            st.session_state.playing = True  # auto-start
            st.rerun()
    else:
        play_label = "⏸  Pause" if st.session_state.playing else "▶  Resume"
        if st.button(play_label, type="primary", width="stretch"):
            st.session_state.playing = not st.session_state.playing
            st.rerun()

        c_run1, c_run2 = st.columns(2)
        with c_run1:
            if st.button(f"+{int(step_days)} days", width="stretch",
                         help="Jump forward N days immediately"):
                with st.spinner(f"Simulating {int(step_days)} days…"):
                    st.session_state.engine.run(int(step_days))
                st.rerun()
        with c_run2:
            if st.button("Reset", width="stretch"):
                _reset()
                st.rerun()

        if st.session_state.playing:
            _speed_labels = {4: "Slow", 2: "Normal", 1: "Fast"}
            st.session_state.play_speed = st.select_slider(
                "Playback speed",
                options=[4, 2, 1],
                value=st.session_state.play_speed,
                format_func=lambda s: _speed_labels.get(s, f"{s}s"),
            )

    st.markdown("---")

    # Story Library — YAML content browser (personas, stories, locations)
    st.markdown("<div class='sidebar-nav-btn'>", unsafe_allow_html=True)
    library_label = (
        "Close Story Library" if st.session_state.show_codex else "Story Library"
    )
    if st.button(library_label, width="stretch", type="secondary",
                 key="story_library_btn"):
        st.session_state.show_codex = not st.session_state.show_codex
        st.session_state.show_controls = False
        st.rerun()
    st.markdown("</div>", unsafe_allow_html=True)

    # World Controls — direct manipulation panel (agents, events, emergent)
    st.markdown("<div class='sidebar-nav-btn'>", unsafe_allow_html=True)
    controls_label = (
        "Close World Controls" if st.session_state.show_controls else "World Controls"
    )
    if st.button(
        controls_label, width="stretch", type="secondary",
        key="world_controls_btn",
        disabled=st.session_state.world is None,
    ):
        st.session_state.show_controls = not st.session_state.show_controls
        st.session_state.show_codex = False
        st.rerun()
    st.markdown("</div>", unsafe_allow_html=True)

    # Settings — stays as native expander (inline panel)
    with st.expander("Settings"):
        # Move subtitle + Ollama status inside settings
        st.markdown(
            f"<div style='display:flex;align-items:center;gap:10px;margin-bottom:14px;"
            f"padding:10px 12px;background:#0a0c14;border-radius:4px;border:1px solid #15171f'>"
            f"<span class='status-dot' style='background:{'#6ec46e' if ollama_ok else '#c85050'}'></span>"
            f"<div>"
            f"<div style='font-size:12.5px;color:#cfd4dc;font-weight:500'>"
            f"Ollama {'connected' if ollama_ok else 'offline'}</div>"
            f"<div class='mono subtle' style='margin-top:2px;font-size:10.5px'>"
            f"Stage A · auto-simulator · {_settings.llm.ollama_tier2_model}</div>"
            f"</div></div>",
            unsafe_allow_html=True,
        )
        with st.form("all_settings", clear_on_submit=False):
            st.markdown("<div class='section-label'>LLM</div>", unsafe_allow_html=True)
            tier2_provider = st.selectbox(
                "Tier 2 provider", ["none", "ollama"],
                index=["none", "ollama"].index(_settings.llm.tier2_provider),
            )
            tier3_provider = st.selectbox(
                "Tier 3 provider", ["none", "ollama"],
                index=["none", "ollama"].index(_settings.llm.tier3_provider),
            )
            t2m = st.text_input("Tier 2 model", _settings.llm.ollama_tier2_model)
            t3m = st.text_input("Tier 3 model", _settings.llm.ollama_tier3_model)
            ollama_base_url = st.text_input("Ollama URL", _settings.llm.ollama_base_url)

            st.markdown(
                "<div class='section-label' style='margin-top:12px'>Memory &amp; translation</div>",
                unsafe_allow_html=True,
            )
            mem_enabled = st.toggle("Agent memory", _settings.memory.enabled)
            mem_embed = st.selectbox(
                "Embedder", ["none", "ollama"],
                index=["none", "ollama"].index(_settings.memory.embedder),
            )

            st.markdown(
                "<div class='section-label' style='margin-top:12px'>Routing</div>",
                unsafe_allow_html=True,
            )
            t3t = st.slider("Tier 3 threshold", 0.0, 1.0, _settings.importance.tier3_threshold, 0.05)

            st.markdown(
                "<div class='section-label' style='margin-top:12px'>Cadences (every N ticks)</div>",
                unsafe_allow_html=True,
            )
            weekly_n = st.slider(
                "Weekly maintenance (planner / reflect / demote / snapshot)",
                3, 21, int(_settings.memory.reflect_every_ticks), 1,
            )
            chronicle_n = st.slider(
                "Chronicler chapter cadence",
                7, 60, int(_settings.llm.chronicle_every_ticks), 1,
            )

            st.markdown(
                "<div class='section-label' style='margin-top:12px'>Storyteller</div>",
                unsafe_allow_html=True,
            )
            force_p = st.selectbox(
                "Force personality", ["", "balanced", "peaceful", "chaotic"],
                index=["", "balanced", "peaceful", "chaotic"].index(_settings.storyteller.force_personality),
            )

            st.markdown(
                "<div class='section-label' style='margin-top:12px'>"
                "Advanced LLM features (slow; opt-in)</div>",
                unsafe_allow_html=True,
            )
            dialogue_on = st.toggle(
                "Dynamic dialogue (Tier 3 uses LLM-written narrative instead of template)",
                _settings.llm.dynamic_dialogue_enabled,
            )
            llm_move_on = st.toggle(
                "LLM-driven movement (historical figures choose tiles via LLM)",
                _settings.llm.llm_movement_enabled,
            )
            weekly_plan_on = st.toggle(
                "Weekly agent planning (HF agents get LLM-generated intentions each week)",
                _settings.llm.weekly_planning_enabled,
            )
            convo_loop_on = st.toggle(
                "Conversation loop (Tier-2+ two-agent events trigger A→B LLM reaction; "
                "updates affinity + beliefs from content — EXPENSIVE, opt-in)",
                _settings.llm.conversation_loop_enabled,
            )
            chronicler_on = st.toggle(
                "Chronicler (说书人 — every 14 ticks, LLM records highlights as a "
                "chapter. Observes only, does not influence future events)",
                _settings.llm.chronicler_enabled,
            )
            emergent_on = st.toggle(
                "Emergent events (LLM invents novel events on hot tiles from "
                "persona/belief/affinity context — EXPENSIVE, opt-in)",
                _settings.llm.emergent_events_enabled,
            )
            perception_on = st.toggle(
                "Subjective perception (each agent's memory of an important "
                "event is rewritten by LLM from their first-person POV)",
                _settings.llm.subjective_perception_enabled,
            )
            self_update_on = st.toggle(
                "Self-update on important events (LLM speaks AS the participant "
                "and reports inner shifts — attributes, needs, emotions, goal, "
                "motivations, beliefs, reflection. AgentSociety route)",
                _settings.llm.self_update_enabled,
            )

            all_saved = st.form_submit_button("Save all")

        if all_saved:
            new = Settings(**{**_settings.model_dump(),
                "llm": {**_settings.llm.model_dump(),
                        "tier2_provider": tier2_provider, "tier3_provider": tier3_provider,
                        "ollama_base_url": ollama_base_url,
                        "ollama_tier2_model": t2m, "ollama_tier3_model": t3m,
                        "dynamic_dialogue_enabled": dialogue_on,
                        "llm_movement_enabled": llm_move_on,
                        "weekly_planning_enabled": weekly_plan_on,
                        "conversation_loop_enabled": convo_loop_on,
                        "chronicler_enabled": chronicler_on,
                        "emergent_events_enabled": emergent_on,
                        "subjective_perception_enabled": perception_on,
                        "self_update_enabled": self_update_on,
                        "chronicle_every_ticks": int(chronicle_n)},
                "memory": {**_settings.memory.model_dump(), "enabled": mem_enabled,
                            "embedder": mem_embed, "reflect_every_ticks": int(weekly_n)},
                "persistence": {**_settings.persistence.model_dump(),
                                 "snapshot_every_ticks": int(weekly_n)},
                "importance": {"tier3_threshold": t3t},
                "storyteller": {**_settings.storyteller.model_dump(), "force_personality": force_p},
            })
            save_settings(new)
            st.success("Saved · reload to apply")

    st.markdown(
        f"<div class='subtle' style='margin-top:24px;text-align:center'>"
        f"{len(_all_packs)} packs · "
        f"{sum(len(p.personas) for p in _all_packs)} personas · "
        f"{sum(len(p.events) for p in _all_packs)} events"
        f"</div>",
        unsafe_allow_html=True,
    )


# ============ MAIN AREA ============
# If Story Library is open, show Codex — regardless of world state
if st.session_state.show_codex:
    st.markdown("<h1>Story Library</h1>", unsafe_allow_html=True)
    st.caption("Every authored character, story, and location · the source material the world draws from.")
    tp, ts, tl = st.tabs(["Characters", "Stories", "Locations"])
    with tp:
        components.html(render_persona_codex_html(_all_packs), height=900, scrolling=True)
    with ts:
        components.html(render_story_codex_html(_all_packs), height=900, scrolling=True)
    with tl:
        components.html(render_tiles_codex_html(_all_packs), height=800, scrolling=True)
    st.stop()

# World Controls page — direct manipulation of the running world
if st.session_state.show_controls and st.session_state.world is not None:
    render_controls_page(st.session_state.world, st.session_state.engine)
    st.stop()

if st.session_state.world is None:
    # Minimal welcome — no Codex dump, no pack cards; just get them going
    st.markdown(
        "<div style='padding:80px 20px 20px 0;max-width:620px'>"
        "<h1 style='font-size:36px;margin-bottom:16px'>A world waits.</h1>"
        "<p style='font-size:15px;color:#8a8f9c;line-height:1.75;margin-bottom:20px'>"
        "Pick the worlds you want to simulate in the sidebar, then press "
        "<b style='color:#e8ecf2'>Bootstrap</b>. "
        "Once started, press <b style='color:#e8ecf2'>▶ Play</b> to let the days pass — "
        "you'll see people move, events unfold, and stories emerge."
        "</p>"
        "<p class='subtle'>Want to read what's authored into the worlds first? "
        "Open <b style='color:#c8cdd5'>📚 Story Library</b> from the sidebar.</p>"
        "</div>",
        unsafe_allow_html=True,
    )
    st.stop()


world = st.session_state.world

# ── Auto-play: drive continuous simulation ──
# When playing, the page auto-refreshes every `play_speed` seconds, and
# each refresh advances 1 virtual day. This gives live motion to the map.
if st.session_state.playing:
    if st_autorefresh is None:
        st.warning("⚠️ `streamlit-autorefresh` not installed — auto-play disabled. "
                   "Use the **+N days** button to advance manually, or run "
                   "`pip install streamlit-autorefresh` to enable live mode.")
    else:
        # Advance one tick on THIS render, then schedule a refresh.
        try:
            st.session_state.engine.run(1)
        except Exception as exc:
            st.error(f"Engine tick failed: {type(exc).__name__}: {exc}")
            st.session_state.playing = False
        st_autorefresh(interval=st.session_state.play_speed * 1000, key="play_tick")

# Note: agent selection now happens via native Streamlit selectbox in sidebar.
# No URL/query-param navigation — state preserved across reruns,
# auto-play doesn't get interrupted.


# ========== 1. LIVE BANNER (if playing) ==========
if st.session_state.playing:
    st.markdown(
        f"<div class='glass-card live-banner'>"
        f"<span class='live-dot'></span>"
        f"<span style='font-size:13.5px;color:#cfd4dc'>"
        f"Live &middot; day <b style='color:#e8c56a'>{world.current_tick}</b>"
        f" &middot; every {st.session_state.play_speed}s</span>"
        f"</div>",
        unsafe_allow_html=True,
    )

# ========== 2. CANVAS WORLD MAP ==========
_world_state = build_world_state_json(
    world, selected_agent=st.session_state.selected_agent,
)
# Use components.html (NOT st.html) — components.html creates a sized iframe
# that supports JavaScript execution AND a fixed height. st.html in 1.56 has
# no height parameter and the iframe collapses to 0px.
components.html(render_canvas_map(_world_state), height=720, scrolling=False)

# ========== 3. INSPECT AGENT SELECTOR ==========
_agents_for_picker = sorted(
    world.all_agents(),
    key=lambda a: (not a.is_historical_figure, a.pack_id, a.display_name),
)
_picker_ids = ["— none —"] + [a.agent_id for a in _agents_for_picker]
_picker_labels = {"— none —": "— none —"}
for a in _agents_for_picker:
    th = PACK_THEMES.get(a.pack_id, PACK_THEMES["scp"])
    star = "★" if a.is_historical_figure else " "
    dead = "  ✝" if not a.is_alive() else ""
    _picker_labels[a.agent_id] = f"{star} {th['emblem']}  {a.display_name}{dead}"
try:
    _cur_idx = _picker_ids.index(st.session_state.selected_agent or "— none —")
except ValueError:
    _cur_idx = 0

with st.container(key="inspect_bar"):
    picked = st.selectbox(
        "Inspect agent",
        _picker_ids,
        index=_cur_idx,
        format_func=lambda x: _picker_labels.get(x, x),
        label_visibility="collapsed",
        key="inspect_agent_picker",
    )
    new_sel = None if picked == "— none —" else picked
    if new_sel != st.session_state.selected_agent:
        st.session_state.selected_agent = new_sel
        st.rerun()

# ========== 4. AGENT CARD + CHRONICLE (side by side) ==========
selected_agent_obj = None
if st.session_state.selected_agent:
    selected_agent_obj = world.get_agent(st.session_state.selected_agent)

# Build Chronicle HTML
by_day = group_events_by_day(world)
chron_html = [
    '<div class="glass-card" style="max-height:50vh;overflow-y:auto;padding:16px 20px">',
    '<div style="display:flex;align-items:baseline;justify-content:space-between;'
    'margin-bottom:12px;padding-bottom:10px;border-bottom:1px solid rgba(255,255,255,0.06)">'
    '<div style="font-family:\'Space Grotesk\';font-size:17px;font-weight:600;color:#f2f4f8;'
    'letter-spacing:-0.012em">Chronicle</div>'
    '<div class="subtle">scrolling world log</div>'
    '</div>',
]
if not by_day:
    chron_html.append(
        '<div style="text-align:center;padding:24px 20px">'
        '<p class="subtle">No events yet &middot; '
        'press <b style="color:#e8c56a">▶ Play</b> in the sidebar</p></div>'
    )
else:
    for day in sorted(by_day.keys(), reverse=True):
        chron_html.append(
            f'<div class="mono" style="color:#7a8090;font-size:10.5px;letter-spacing:0.18em;'
            f'margin:12px 0 6px 0;padding-bottom:4px;border-bottom:1px solid rgba(255,255,255,0.05)">'
            f'DAY {day:03d}</div>'
        )
        for pack_id, events in sorted(by_day[day].items()):
            th = PACK_THEMES.get(pack_id, PACK_THEMES["scp"])
            chron_html.append(
                f'<div style="font-size:10.5px;color:{th["text"]};letter-spacing:0.14em;'
                f'margin:4px 0 3px 0;font-weight:600">{th["emblem"]} {pack_id.upper()}</div>'
            )
            for e in events:
                marker = "●●●" if e.tier_used == 3 else ("●●" if e.tier_used == 2 else "●")
                tier_col = "#b091d1" if e.tier_used == 3 else ("#d4a373" if e.tier_used == 2 else "#3d4454")
                text = e.best_rendering()
                chron_html.append(
                    f'<div style="color:#cfd4dc;font-size:12.5px;line-height:1.6;'
                    f'margin:2px 0 2px 8px;border-left:1px solid {th["accent"]}40;padding-left:10px">'
                    f'<span class="mono" style="color:{tier_col};font-size:10px;margin-right:5px">{marker}</span>'
                    f'{esc(text)}</div>'
                )
chron_html.append('</div>')
chronicle_block = "".join(chron_html)

# Build Agent card HTML (only if agent selected)
agent_block = ""
if selected_agent_obj:
    agent = selected_agent_obj
    th = PACK_THEMES.get(agent.pack_id, PACK_THEMES["scp"])
    emoji = _agent_emoji(agent.tags)
    hf_badge = "★ HISTORICAL" if agent.is_historical_figure else "ORDINARY"

    tags_html = " ".join(
        f'<span class="pill" style="background:{th["floor"]};color:{th["text"]};'
        f'border:1px solid {th["accent"]}66">{esc(t)}</span>'
        for t in sorted(agent.tags)
    ) if agent.tags else ""

    attr_html = ""
    if agent.attributes:
        attr_rows = "".join(
            f'<div style="display:flex;justify-content:space-between;padding:3px 0;'
            f'border-bottom:1px dashed rgba(255,255,255,0.04);font-size:11.5px">'
            f'<span style="color:#8a8f9c">{esc(str(k))}</span>'
            f'<span class="mono" style="color:{th["glow"]}">{esc(str(v))}</span></div>'
            for k, v in list(agent.attributes.items())[:8]
        )
        attr_html = (
            f'<div class="section-label" style="margin-top:12px">Attributes</div>'
            f'<div>{attr_rows}</div>'
        )

    # Beliefs (LLM-evolved, stored in state_extra)
    belief_html = ""
    _beliefs = agent.get_beliefs()
    if _beliefs:
        belief_rows = "".join(
            f'<div style="padding:4px 0;border-bottom:1px dashed rgba(255,255,255,0.04);font-size:11.5px">'
            f'<span class="mono" style="color:{th["glow"]};font-size:10px">{esc(topic)}</span>'
            f'<div style="color:#cfd4dc;line-height:1.4;margin-top:2px">{esc(belief)}</div></div>'
            for topic, belief in list(_beliefs.items())[:6]
        )
        belief_html = (
            f'<div class="section-label" style="margin-top:12px">Beliefs · evolved</div>'
            f'<div>{belief_rows}</div>'
        )

    # Weekly plan (LLM-generated, stored in state_extra)
    plan_html = ""
    _plan = agent.get_weekly_plan()
    if _plan:
        def _fmt_plan_list(key):
            items = _plan.get(key) or []
            if not isinstance(items, list) or not items:
                return ""
            lis = "".join(f"<li style='margin:2px 0'>{esc(str(x))}</li>" for x in items[:5])
            return (
                f"<div style='font-size:11px;color:#8a8f9c;margin-top:6px'>{esc(key)}</div>"
                f"<ul style='font-size:12px;color:#cfd4dc;margin:2px 0 0 18px;padding:0'>{lis}</ul>"
            )
        plan_body = _fmt_plan_list("goals_this_week") + _fmt_plan_list("seek") + _fmt_plan_list("avoid")
        if plan_body:
            plan_html = (
                f'<div class="section-label" style="margin-top:12px">Weekly Plan · LLM</div>'
                f'<div>{plan_body}</div>'
            )

    rel_html = ""
    if agent.relationships:
        rel_rows = "".join(
            f'<div style="display:flex;justify-content:space-between;padding:2px 0;font-size:11.5px">'
            f'<span style="color:#cfd4dc">{esc(r.target_id)}</span>'
            f'<span class="mono subtle">{esc(r.kind)} · {r.affinity:+d}</span></div>'
            for r in sorted(agent.relationships.values(), key=lambda x: -abs(x.affinity))[:5]
        )
        rel_html = (
            f'<div class="section-label" style="margin-top:12px">Relationships</div>'
            f'<div>{rel_rows}</div>'
        )

    ev = [e for e in world.events_since(1) if agent.agent_id in e.participants]
    story_html = ""
    if ev:
        story_rows = []
        for e in reversed(ev[-6:]):
            tier_glyph = "●●●" if e.tier_used == 3 else ("●●" if e.tier_used == 2 else "●")
            tier_col = "#b091d1" if e.tier_used == 3 else ("#d4a373" if e.tier_used == 2 else "#5a6270")
            story_rows.append(
                f'<div style="margin-bottom:8px;padding-bottom:8px;border-bottom:1px solid rgba(255,255,255,0.04)">'
                f'<div class="mono subtle" style="margin-bottom:2px;font-size:10px">'
                f'<span style="color:{tier_col}">{tier_glyph}</span> '
                f'DAY {e.tick:03d} &middot; {esc(e.event_kind)}</div>'
                f'<div style="font-size:12.5px;color:#cfd4dc;line-height:1.55">{esc(e.best_rendering())}</div>'
                f'</div>'
            )
        story_html = (
            f'<div class="section-label" style="margin-top:12px">'
            f'Personal Story &middot; {len(ev)} fragments</div>'
            f'<div>{"".join(story_rows)}</div>'
        )

    goal_html = (
        f'<div style="font-size:13px;color:{th["glow"]};margin-top:10px;'
        f'padding:7px 10px;background:{th["floor"]};border-radius:3px">'
        f'<b>Goal</b> &middot; {esc(agent.current_goal)}</div>'
        if agent.current_goal else ''
    )

    # ── Inner state: needs / emotions / motivations (LLM-driven layer) ──

    def _bar(label: str, value: float, color: str) -> str:
        # Tiny inline bar widget. value clamped 0..100.
        v = max(0.0, min(100.0, float(value)))
        return (
            f'<div style="display:flex;align-items:center;gap:8px;font-size:11px;'
            f'margin:2px 0">'
            f'<span style="width:62px;color:#8a8f9c">{esc(label)}</span>'
            f'<div style="flex:1;height:6px;background:#15171f;border-radius:3px;'
            f'overflow:hidden">'
            f'<div style="height:100%;width:{v:.0f}%;background:{color}"></div>'
            f'</div>'
            f'<span class="mono" style="width:28px;text-align:right;color:#cfd4dc">{int(v):d}</span>'
            f'</div>'
        )

    needs = agent.get_needs()
    needs_html = ""
    if needs:
        rows = "".join(_bar(k, v, "#5a7fa3") for k, v in needs.items())
        needs_html = (
            f'<div class="section-label" style="margin-top:12px">'
            f'Needs &middot; <span class="subtle">Maslow drives</span></div>'
            f'<div>{rows}</div>'
        )

    emotions = agent.get_emotions()
    emotions_html = ""
    if emotions:
        # Color per emotion
        emo_color = {"fear": "#c85050", "joy": "#e8c56a", "anger": "#d4673a"}
        rows = "".join(
            _bar(k, v, emo_color.get(k, "#8a8f9c")) for k, v in emotions.items()
        )
        emotions_html = (
            f'<div class="section-label" style="margin-top:12px">'
            f'Emotions &middot; <span class="subtle">decay each tick</span></div>'
            f'<div>{rows}</div>'
        )

    motivations = agent.get_motivations()
    motivations_html = ""
    if motivations:
        items = "".join(
            f'<li style="margin:2px 0;font-size:12px;color:#cfd4dc">{esc(m)}</li>'
            for m in motivations[:3]
        )
        motivations_html = (
            f'<div class="section-label" style="margin-top:12px">'
            f'Motivations &middot; <span class="subtle">LLM-driven urges</span></div>'
            f'<ul style="margin:4px 0 0 16px;padding:0">{items}</ul>'
        )

    # Position: now meaningful (set by movement._spot_in_tile)
    pos_html = (
        f'<div class="subtle" style="font-size:10.5px;margin-top:8px">'
        f'pos · <span class="mono">({agent.x:.0f}, {agent.y:.0f})</span></div>'
    )

    agent_block = (
        f'<div class="glass-card" style="max-height:50vh;overflow-y:auto;'
        f'padding:18px 20px;border-color:{th["accent"]}4d">'
        f'<div style="display:flex;align-items:flex-start;gap:12px;'
        f'padding-bottom:12px;border-bottom:1px solid rgba(255,255,255,0.06);margin-bottom:12px">'
        f'<div style="font-size:36px;line-height:1">{emoji}</div>'
        f'<div style="flex:1;min-width:0">'
        f'<div style="font-family:\'Space Grotesk\';font-size:19px;font-weight:600;'
        f'color:#f2f4f8;letter-spacing:-0.012em;line-height:1.2">{esc(agent.display_name)}</div>'
        f'<div class="mono subtle" style="margin-top:2px;font-size:10.5px">'
        f'{esc(agent.agent_id)} &middot; <span style="color:{th["glow"]}">{hf_badge}</span>'
        f'</div></div></div>'
        f'<div class="subtle" style="display:flex;gap:14px;flex-wrap:wrap;margin-bottom:12px;font-size:11.5px">'
        f'<span>📍 {esc(agent.current_tile)}</span>'
        f'<span>age {agent.age} &middot; {agent.life_stage.value}</span>'
        f'</div>'
        f'<div class="section-label">Persona</div>'
        f'<div style="font-size:13px;color:#cfd4dc;line-height:1.6">{esc(agent.persona_card)}</div>'
        f'{goal_html}'
        + (f'<div class="section-label" style="margin-top:12px">Tags</div><div>{tags_html}</div>'
            if tags_html else '')
        + f'{pos_html}{needs_html}{emotions_html}{motivations_html}'
        + f'{plan_html}{belief_html}{attr_html}{rel_html}{story_html}'
        + '</div>'
    )

# Render panels in normal flow
panel_class = "with-agent" if agent_block else "chronicle-only"
st.markdown(
    f'<div class="bottom-panels {panel_class}">{agent_block}{chronicle_block}</div>',
    unsafe_allow_html=True,
)

# ========== 4.5 CHAPTERS (说书人) ==========
# The Chronicler periodically observes emergent highlights and writes a
# chapter. These are descriptive only — they never steer future events.
_chapters = world.chapters
if _chapters:
    with st.expander(f"Chapters · {len(_chapters)} recorded by the 说书人",
                     expanded=False):
        # newest first
        for ch in reversed(_chapters[-12:]):
            th = PACK_THEMES.get(ch.get("pack_id", "scp"), PACK_THEMES["scp"])
            st.markdown(
                f'<div class="glass-card" style="margin-bottom:12px;padding:16px 20px;'
                f'border-left:3px solid {th["accent"]}">'
                f'<div class="mono subtle" style="font-size:10.5px;letter-spacing:0.14em;'
                f'margin-bottom:6px">{th["emblem"]} {ch.get("pack_id","").upper()} '
                f'&middot; DAY {ch.get("tick",0):03d}</div>'
                f'<div style="font-family:\'Space Grotesk\';font-size:18px;'
                f'font-weight:600;color:#f2f4f8;margin-bottom:8px">'
                f'{esc(ch.get("title",""))}</div>'
                f'<div style="font-size:13.5px;color:#cfd4dc;line-height:1.65">'
                f'{esc(ch.get("body",""))}</div>'
                f'</div>',
                unsafe_allow_html=True,
            )

# ========== 5. ENGINE LOG VIEWER ==========
_tick_logger = st.session_state.get("tick_logger")
if _tick_logger is not None:
    with st.expander("Engine Log (debug)", expanded=False):
        _log_filter = st.radio(
            "Filter",
            ["All", "LLM only", "Decisions", "Events", "Social", "Movement"],
            horizontal=True, label_visibility="collapsed",
        )
        _raw_lines = _tick_logger.get_lines(last_n=300)
        if _log_filter == "LLM only":
            _raw_lines = [l for l in _raw_lines if "[LLM]" in l]
        elif _log_filter == "Decisions":
            markers = ("PLAN", "EMERGENT", "PERSONA_EVOLVED", "CHAPTER", "CONSCIOUS")
            _raw_lines = [l for l in _raw_lines
                          if any(m in l for m in markers) or "TICK" in l or "===" in l]
        elif _log_filter == "Events":
            _raw_lines = [l for l in _raw_lines
                          if "EVENT" in l or "TIER" in l or "EMERGENT" in l
                          or "SUMMARY" in l or "TICK" in l or "===" in l]
        elif _log_filter == "Social":
            markers = ("DIALOGUE_REACT", "BELIEF", "RUMOR", "INTERACTION")
            _raw_lines = [l for l in _raw_lines
                          if any(m in l for m in markers) or "TICK" in l or "===" in l]
        elif _log_filter == "Movement":
            _raw_lines = [l for l in _raw_lines
                          if "MOVE" in l or "TICK" in l or "===" in l]
        _log_text = "\n".join(_raw_lines[-150:])
        st.code(_log_text or "(no log entries yet)", language="text")
