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
from living_world.dashboard.build import (
    bootstrap_world,
    group_events_by_day,
    make_engine,
)
from living_world.dashboard.codex import (
    render_persona_codex_html,
    render_story_codex_html,
    render_tiles_codex_html,
)
from living_world.dashboard.map_view import (
    PACK_THEMES,
    _agent_emoji,
    render_ticker_html,
    render_world_svg,
)
from living_world.i18n import NoopTranslator, OllamaTranslator, cached
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
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=Space+Grotesk:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&family=Noto+Sans+SC:wght@400;500;700&display=swap');
@import url('https://fonts.googleapis.com/icon?family=Material+Icons');
@import url('https://fonts.googleapis.com/css2?family=Material+Symbols+Rounded:opsz,wght,FILL,GRAD@20..48,100..700,0..1,-50..200');

/* =========================================================================
   Typography — Apple HIG + Material proportions
   Display : Space Grotesk  (tight, geometric, editorial)
   Body    : Inter          (Apple-SF-like; highly readable at small sizes)
   Mono    : JetBrains Mono (tabular data, timestamps)
   CJK     : Noto Sans SC
   Scale   : 34 / 28 / 22 / 17 / 15 / 13 / 11
   ========================================================================= */

.stApp, .stApp p, .stApp label, .stApp button, .stApp input, .stApp textarea,
.stApp [data-testid="stMarkdownContainer"] {
    font-family: Inter, "Noto Sans SC", -apple-system, system-ui, sans-serif;
    font-feature-settings: "cv02", "cv03", "cv04", "cv11";  /* Inter ss01 niceties */
    -webkit-font-smoothing: antialiased;
    text-rendering: optimizeLegibility;
}
/* Keep Material Symbols font on icon elements */
span.material-icons, span.material-icons-outlined,
span.material-symbols-rounded, span.material-symbols-outlined,
i.material-icons, i.material-icons-outlined,
i.material-symbols-rounded, i.material-symbols-outlined,
[class*="material-icons"], [class*="material-symbols"],
[data-testid="stIconMaterial"], [data-testid="stIconMaterial"] *,
header span[data-testid*="icon"], [data-testid="collapsedControl"] span {
    font-family: "Material Symbols Rounded", "Material Icons" !important;
    font-weight: normal !important; font-style: normal !important;
    font-size: 20px; line-height: 1; letter-spacing: normal;
    text-transform: none; display: inline-block; white-space: nowrap;
    direction: ltr; -webkit-font-feature-settings: 'liga';
}

/* Background — Starfield/Octopath: deep space with subtle warm glow */
.stApp {
    background:
      radial-gradient(ellipse at 20% 10%, rgba(60, 40, 80, 0.18) 0%, transparent 50%),
      radial-gradient(ellipse at 80% 90%, rgba(20, 60, 80, 0.15) 0%, transparent 50%),
      radial-gradient(ellipse at 50% 50%, rgba(30, 25, 45, 0.08) 0%, transparent 70%),
      #04050a;
}

/* Headings — Apple Large Title / Title 1-2 scale */
h1, h2, h3, h4, h5, h6 {
    font-family: "Space Grotesk", Inter, sans-serif !important;
    color: #f2f4f8 !important;
    font-weight: 600 !important;
    margin: 0;
}
h1 { font-size: 34px !important; letter-spacing: -0.024em !important; line-height: 1.15 !important; }
h2 { font-size: 28px !important; letter-spacing: -0.018em !important; line-height: 1.2 !important; }
h3 { font-size: 22px !important; letter-spacing: -0.012em !important; line-height: 1.25 !important; font-weight: 600 !important; }
h4 { font-size: 17px !important; letter-spacing: -0.006em !important; line-height: 1.3 !important; }

/* Body text — Apple body 15pt equivalent */
.stApp p, .stApp .stMarkdown p {
    font-size: 15px !important;
    line-height: 1.55 !important;
    color: #cfd4dc !important;
    letter-spacing: -0.003em;
}
.stCaption, .subtle {
    font-size: 12px !important;
    color: #7a8090 !important;
    letter-spacing: 0.01em !important;
    line-height: 1.5 !important;
}

/* Metrics */
div[data-testid="stMetricValue"] {
    color: #f2f4f8 !important;
    font-family: "Space Grotesk", sans-serif !important;
    font-size: 22px !important;
    font-weight: 600 !important;
    letter-spacing: -0.018em !important;
    line-height: 1.2 !important;
}
div[data-testid="stMetricLabel"] {
    color: #7a8090 !important;
    font-family: Inter, sans-serif !important;
    font-size: 10.5px !important;
    font-weight: 500 !important;
    text-transform: uppercase;
    letter-spacing: 0.12em;
}

/* =========================================================================
   Sidebar
   ========================================================================= */
section[data-testid="stSidebar"] {
    background:
      linear-gradient(180deg, rgba(16, 12, 22, 0.6) 0%, rgba(6, 7, 12, 1) 100%);
    border-right: 1px solid #15171f;
}
section[data-testid="stSidebar"] > div { padding-top: 8px; }

/* =========================================================================
   Buttons — Starfield-style amber/slate
   ========================================================================= */

/* Primary (Bootstrap World, ▶ Play): deep slate gradient + amber border + amber text */
.stButton > button[kind="primary"] {
    background: linear-gradient(180deg, #1a1e2c 0%, #0d1018 100%);
    color: #e8c56a;
    border: 1px solid rgba(232, 197, 106, 0.35);
    border-radius: 4px;
    font-family: Inter, sans-serif;
    font-size: 13px;
    font-weight: 600;
    letter-spacing: 0.02em;
    padding: 10px 16px;
    text-transform: none;
    box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.04),
                0 1px 3px rgba(0, 0, 0, 0.3);
    transition: all 0.18s cubic-bezier(0.4, 0, 0.2, 1);
}
.stButton > button[kind="primary"]:hover:not(:disabled) {
    background: linear-gradient(180deg, #242938 0%, #141825 100%);
    border-color: rgba(232, 197, 106, 0.65);
    color: #ffd98a;
    box-shadow: inset 0 1px 0 rgba(255,255,255,0.06),
                0 0 20px rgba(232, 197, 106, 0.2),
                0 4px 12px rgba(0, 0, 0, 0.4);
    transform: translateY(-1px);
}
.stButton > button[kind="primary"]:disabled {
    background: #0d0f15;
    color: #3a4050;
    border-color: #1a1d26;
}
.stButton > button[kind="primary"]:active:not(:disabled) {
    transform: translateY(0);
    box-shadow: inset 0 2px 4px rgba(0,0,0,0.3);
}

/* Secondary (Reset, Story Library): transparent with hairline border */
.stButton > button[kind="secondary"] {
    background: transparent;
    color: #cfd4dc;
    border: 1px solid #24293a;
    border-radius: 4px;
    font-family: Inter, sans-serif;
    font-size: 13px;
    font-weight: 500;
    letter-spacing: 0.01em;
    padding: 10px 16px;
    transition: all 0.18s cubic-bezier(0.4, 0, 0.2, 1);
}
.stButton > button[kind="secondary"]:hover {
    background: rgba(232, 197, 106, 0.05);
    border-color: rgba(232, 197, 106, 0.3);
    color: #e8c56a;
}

/* =========================================================================
   Tabs, inputs, expander — refined
   ========================================================================= */
.stTabs [data-baseweb="tab-list"] {
    gap: 0; background: transparent;
    border-bottom: 1px solid #15171f;
}
.stTabs [data-baseweb="tab"] {
    background: transparent; border: none;
    font-family: Inter, sans-serif; font-size: 13px;
    font-weight: 500; color: #7a8090;
    padding: 12px 18px; letter-spacing: 0.01em;
    transition: color 0.2s ease;
}
.stTabs [data-baseweb="tab"]:hover { color: #cfd4dc; }
.stTabs [aria-selected="true"] {
    color: #e8c56a !important;
}
.stTabs [data-baseweb="tab"]::after {
    content: ''; display: block; height: 2px; width: 0;
    background: #e8c56a;
    transition: width 0.22s cubic-bezier(0.4, 0, 0.2, 1);
    margin-top: 6px;
}
.stTabs [data-baseweb="tab"]:hover::after { width: 40%; }
.stTabs [aria-selected="true"]::after { width: 100%; }

.stSelectbox > div > div,
.stTextInput > div > div,
.stNumberInput > div > div > input {
    background: #0a0c14 !important;
    border: 1px solid #1a1d26 !important;
    color: #cfd4dc !important;
    font-family: Inter, sans-serif !important;
    font-size: 13.5px !important;
    border-radius: 4px !important;
    transition: border-color 0.15s ease, box-shadow 0.15s ease;
}
.stSelectbox > div > div:hover,
.stTextInput > div > div:hover,
.stNumberInput > div > div > input:hover {
    border-color: rgba(232, 197, 106, 0.25) !important;
}
.stSelectbox > div > div:focus-within,
.stTextInput > div > div:focus-within {
    border-color: #e8c56a !important;
    box-shadow: 0 0 0 3px rgba(232, 197, 106, 0.08) !important;
}

hr { border: none; border-top: 1px solid #15171f; margin: 18px 0; }

/* Expander — unify with sidebar-nav-btn Story Library */
.streamlit-expanderHeader, [data-testid="stExpander"] summary {
    background: transparent !important;
    border: 1px solid #15171f !important;
    border-radius: 4px !important;
    font-family: Inter, sans-serif !important;
    font-size: 13px !important;
    font-weight: 500 !important;
    color: #cfd4dc !important;
    padding: 12px 14px !important;
}
[data-testid="stExpander"] summary:hover {
    background: rgba(255, 255, 255, 0.02) !important;
    border-color: #24293a !important;
}

/* Story Library button — mimic expander header: left-aligned text + chevron.
   Aggressive selectors to defeat Streamlit's default centered button layout. */
.sidebar-nav-btn .stButton,
.sidebar-nav-btn .stButton > button {
    display: block !important;
    width: 100% !important;
}
.sidebar-nav-btn .stButton > button[kind="secondary"] {
    background: transparent !important;
    border: 1px solid #15171f !important;
    border-radius: 4px !important;
    color: #cfd4dc !important;
    font-family: Inter, sans-serif !important;
    font-size: 13px !important;
    font-weight: 500 !important;
    padding: 12px 36px !important;  /* leave room for absolute-positioned chevron */
    letter-spacing: 0 !important;
    text-align: left !important;
    justify-content: flex-start !important;
    align-items: center !important;
    position: relative !important;
}
/* Force label children to left-align (Streamlit wraps text in <p> inside <div>) */
.sidebar-nav-btn .stButton > button[kind="secondary"] *,
.sidebar-nav-btn .stButton > button[kind="secondary"] > div,
.sidebar-nav-btn .stButton > button[kind="secondary"] p {
    text-align: left !important;
    justify-content: flex-start !important;
    width: auto !important;
    margin: 0 !important;
    display: inline !important;
}
.sidebar-nav-btn .stButton > button[kind="secondary"]:hover {
    background: rgba(255, 255, 255, 0.02) !important;
    border-color: #24293a !important;
    color: #cfd4dc !important;
    transform: none !important;
}
/* Absolutely-positioned chevron on the left edge */
.sidebar-nav-btn .stButton > button[kind="secondary"]::before {
    content: '›';
    position: absolute;
    left: 16px;
    top: 50%;
    transform: translateY(-50%);
    color: #7a8090;
    font-size: 16px;
    font-weight: 400;
    line-height: 1;
}

/* Checkbox labels */
.stCheckbox > label {
    color: #cfd4dc !important;
    font-size: 14px !important;
    font-family: Inter, sans-serif !important;
}

/* =========================================================================
   Custom component classes (cards, pills, status dots)
   ========================================================================= */
.floating-card {
    /* alias: behave like glass-card for legacy call-sites */
    background: rgba(10, 12, 20, 0.72);
    backdrop-filter: blur(14px) saturate(140%);
    -webkit-backdrop-filter: blur(14px) saturate(140%);
    border: 1px solid rgba(255, 255, 255, 0.06);
    border-radius: 10px;
    padding: 20px 22px;
    box-shadow: 0 1px 3px rgba(0, 0, 0, 0.4),
                0 16px 40px rgba(0, 0, 0, 0.5);
}
.pill {
    display: inline-block; padding: 3px 8px; margin: 2px 3px 2px 0;
    border-radius: 2px; font-family: "JetBrains Mono", monospace;
    font-size: 10.5px; letter-spacing: 0.04em; font-weight: 500;
}
.status-dot {
    display: inline-block; width: 6px; height: 6px;
    border-radius: 50%; margin-right: 6px;
    vertical-align: middle;
}
.mono { font-family: "JetBrains Mono", monospace; }
.section-label {
    font-size: 10.5px; font-weight: 600; letter-spacing: 0.14em;
    color: #7a8090; text-transform: uppercase; margin-bottom: 10px;
}
.field-label {
    font-size: 11.5px; color: #8a8f9c; font-weight: 500;
    letter-spacing: 0.01em; margin-bottom: 6px;
}

/* =========================================================================
   World Map as full-page background + floating cards on top (glassmorphism)
   ========================================================================= */
.map-backdrop {
    position: fixed;
    top: 0;
    left: 21rem;          /* sidebar width — adjust if Streamlit changes */
    right: 0;
    bottom: 0;
    z-index: 0;
    overflow: auto;
    padding: 24px 40px 40px 40px;
    pointer-events: auto;
}
.map-backdrop svg { max-width: 100%; height: auto; }

/* Collapsed sidebar — map expands full width */
[data-testid="stSidebar"][aria-expanded="false"] ~ .main .map-backdrop,
[data-testid="collapsedControl"]:not([style*="display: none"]) ~ * .map-backdrop {
    left: 0;
}

/* Make Streamlit's main container transparent + z-index above map */
.stApp > .main, .main .block-container {
    background: transparent !important;
}
.main .block-container {
    padding: 0 !important;
    max-width: 100% !important;
    position: relative;
    z-index: 5;
}

/* Dock bottom — fixed position bottom strip for cards. Cards in HTML inside this
   div are positioned at the BOTTOM of the viewport, floating over the map. */
.dock-bottom {
    position: fixed;
    left: calc(21rem + 24px);  /* after sidebar */
    right: 24px;
    bottom: 24px;
    z-index: 20;
    display: grid;
    gap: 16px;
    pointer-events: none;   /* pass-through by default */
}
.dock-bottom > * { pointer-events: auto; }  /* re-enable on children */
/* When sidebar collapsed */
[data-testid="stSidebar"][aria-expanded="false"] ~ * .dock-bottom,
[data-testid="collapsedControl"] ~ * .dock-bottom {
    left: 24px;
}
/* 1 card (chronicle only) = single column; 2 cards = two-column */
.dock-bottom.with-agent { grid-template-columns: 1fr 1fr; }
.dock-bottom.chronicle-only { grid-template-columns: 1fr; }

/* Inspect selector — floats over the Chronicle card header, right side.
   Streamlit container `inspect_bar` becomes `.st-key-inspect_bar` in the DOM. */
.st-key-inspect_bar {
    position: fixed !important;
    right: 38px !important;
    bottom: calc(38vh + 14px) !important;  /* align with chronicle title row */
    z-index: 25 !important;
    width: 240px !important;
    max-width: 40vw;
}
.st-key-inspect_bar .stSelectbox > div > div {
    background: rgba(10, 12, 20, 0.85) !important;
    border-color: rgba(255,255,255,0.08) !important;
    backdrop-filter: blur(8px);
    font-size: 12.5px !important;
}

/* Top-dock for live banner */
.dock-top {
    position: fixed;
    top: 14px;
    left: calc(21rem + 24px);
    right: 24px;
    z-index: 20;
    pointer-events: none;
}
.dock-top > * { pointer-events: auto; }
[data-testid="stSidebar"][aria-expanded="false"] ~ * .dock-top,
[data-testid="collapsedControl"] ~ * .dock-top {
    left: 24px;
}

/* Floating glass card — semi-transparent panel that sits over map */
.glass-card {
    background: rgba(10, 12, 20, 0.72);
    backdrop-filter: blur(14px) saturate(140%);
    -webkit-backdrop-filter: blur(14px) saturate(140%);
    border: 1px solid rgba(255, 255, 255, 0.06);
    border-radius: 10px;
    padding: 20px 22px;
    box-shadow: 0 1px 3px rgba(0, 0, 0, 0.4),
                0 16px 40px rgba(0, 0, 0, 0.5);
}

/* =========================================================================
   Motion
   ========================================================================= */
@keyframes fadeInUp {
    from { opacity: 0; transform: translateY(4px); }
    to   { opacity: 1; transform: translateY(0); }
}
.stMarkdown, .element-container, .floating-card {
    animation: fadeInUp 0.28s cubic-bezier(0.4, 0, 0.2, 1);
}

@keyframes livePulse {
    0%, 100% { box-shadow: 0 0 0 0 rgba(110, 196, 110, 0.6); opacity: 1; }
    50%      { box-shadow: 0 0 0 6px rgba(110, 196, 110, 0);   opacity: 0.7; }
}
.live-dot {
    display: inline-block; width: 8px; height: 8px; border-radius: 50%;
    background: #6ec46e; animation: livePulse 1.6s infinite;
}

/* Scrollbar */
::-webkit-scrollbar { width: 8px; height: 8px; }
::-webkit-scrollbar-track { background: transparent; }
::-webkit-scrollbar-thumb { background: #15171f; border-radius: 4px; }
::-webkit-scrollbar-thumb:hover { background: #24293a; }

/* Map SVG hover effect on agent circles */
svg a:hover circle { filter: brightness(1.25); }
svg a { transition: filter 0.12s; }
</style>
""", unsafe_allow_html=True)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_PACKS_DIR = PROJECT_ROOT / _settings.simulation.packs_dir

# ============ Session state ============
if "world" not in st.session_state:
    st.session_state.world = None
    st.session_state.engine = None
    st.session_state.selected_agent = None
    st.session_state.loaded_packs = None
    st.session_state.playing = False
    st.session_state.play_speed = 2  # seconds per tick
    st.session_state.show_codex = False
    st.session_state.show_settings = False


def _reset() -> None:
    for k in ["world", "engine", "selected_agent", "loaded_packs"]:
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
            st.session_state.engine = make_engine(world, loaded, _settings, int(seed))
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

    # Story Library — navigates to the codex "page" in the main area
    st.markdown("<div class='sidebar-nav-btn'>", unsafe_allow_html=True)
    library_label = "Close Story Library" if st.session_state.show_codex else "Story Library"
    if st.button(library_label, width="stretch", type="secondary",
                 key="story_library_btn"):
        st.session_state.show_codex = not st.session_state.show_codex
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
                "Tier 2 provider", ["none", "mock", "ollama"],
                index=["none", "mock", "ollama"].index(_settings.llm.tier2_provider),
            )
            tier3_provider = st.selectbox(
                "Tier 3 provider", ["none", "mock", "ollama"],
                index=["none", "mock", "ollama"].index(_settings.llm.tier3_provider),
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
                "Embedder", ["none", "mock", "ollama"],
                index=["none", "mock", "ollama"].index(_settings.memory.embedder),
            )
            i18n_enabled = st.toggle("Output translation", _settings.i18n.enabled)
            i18n_target = st.selectbox(
                "Target locale", ["en", "zh", "ja"],
                index=["en", "zh", "ja"].index(_settings.i18n.target_locale),
            )

            st.markdown(
                "<div class='section-label' style='margin-top:12px'>Routing</div>",
                unsafe_allow_html=True,
            )
            t2t = st.slider("Tier 2 threshold", 0.0, 1.0, _settings.importance.tier2_threshold, 0.05)
            t3t = st.slider("Tier 3 threshold", 0.0, 1.0, _settings.importance.tier3_threshold, 0.05)

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
            debate_on = st.toggle(
                "Debate Phase (multi-agent round for spotlight events — 5+ LLM calls each)",
                _settings.llm.debate_enabled,
            )
            debate_thr = st.slider(
                "Debate trigger importance",
                0.6, 1.0, _settings.llm.debate_threshold, 0.05,
                disabled=not debate_on,
            )
            llm_move_on = st.toggle(
                "LLM-driven movement (historical figures choose tiles via LLM)",
                _settings.llm.llm_movement_enabled,
            )

            all_saved = st.form_submit_button("Save all")

        if all_saved:
            new = Settings(**{**_settings.model_dump(),
                "llm": {**_settings.llm.model_dump(),
                        "tier2_provider": tier2_provider, "tier3_provider": tier3_provider,
                        "ollama_base_url": ollama_base_url,
                        "ollama_tier2_model": t2m, "ollama_tier3_model": t3m,
                        "dynamic_dialogue_enabled": dialogue_on,
                        "debate_enabled": debate_on,
                        "debate_threshold": debate_thr,
                        "llm_movement_enabled": llm_move_on},
                "memory": {**_settings.memory.model_dump(), "enabled": mem_enabled, "embedder": mem_embed},
                "i18n": {**_settings.i18n.model_dump(), "enabled": i18n_enabled, "target_locale": i18n_target},
                "importance": {"tier2_threshold": t2t, "tier3_threshold": t3t},
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
if st.session_state.playing and st_autorefresh is not None:
    # Advance one tick on THIS render, then schedule a refresh.
    st.session_state.engine.run(1)
    st_autorefresh(interval=st.session_state.play_speed * 1000, key="play_tick")

# Note: agent selection now happens via native Streamlit selectbox in sidebar.
# No URL/query-param navigation — state preserved across reruns,
# auto-play doesn't get interrupted.


# ========== MAP as fixed background ==========
svg = render_world_svg(world, selected_agent_id=st.session_state.selected_agent)
st.markdown(
    f'<div class="map-backdrop">{svg}</div>',
    unsafe_allow_html=True,
)

# ========== TOP DOCK: Live banner ==========
if st.session_state.playing:
    st.markdown(
        f"<div class='dock-top'>"
        f"<div class='glass-card' style='display:inline-flex;align-items:center;gap:10px;"
        f"padding:10px 16px;border-color:rgba(110,196,110,0.25);'>"
        f"<span class='live-dot'></span>"
        f"<span style='font-size:13.5px;color:#cfd4dc'>"
        f"Live simulation &middot; day <b style='color:#e8c56a'>{world.current_tick}</b>"
        f" &middot; advancing every {st.session_state.play_speed}s</span>"
        f"</div></div>",
        unsafe_allow_html=True,
    )


# ========== BOTTOM DOCK: Agent card (if selected) + Chronicle ==========
# Rendered as ONE BIG HTML block wrapped in .dock-bottom (position:fixed).
# This guarantees cards truly stick to the viewport bottom over the map.

selected_agent_obj = None
if st.session_state.selected_agent:
    selected_agent_obj = world.get_agent(st.session_state.selected_agent)

# Build Chronicle HTML (always shown)
translator_for_chron = (
    cached(
        OllamaTranslator(
            model=_settings.i18n.ollama_translate_model,
            base_url=_settings.llm.ollama_base_url,
        ),
        max_size=_settings.i18n.cache_size,
    )
    if _settings.i18n.enabled and _settings.i18n.provider == "ollama"
    else NoopTranslator()
)
do_translate = _settings.i18n.enabled

by_day = group_events_by_day(world)
chron_html = [
    '<div class="glass-card" style="max-height:38vh;overflow-y:auto;padding:16px 20px">',
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
                text = translator_for_chron.translate(e.best_rendering(), target="zh") if do_translate else e.best_rendering()
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

    agent_block = (
        f'<div class="glass-card" style="max-height:70vh;overflow-y:auto;'
        f'padding:18px 20px;border-color:{th["accent"]}4d">'
        # Header
        f'<div style="display:flex;align-items:flex-start;gap:12px;'
        f'padding-bottom:12px;border-bottom:1px solid rgba(255,255,255,0.06);margin-bottom:12px">'
        f'<div style="font-size:36px;line-height:1">{emoji}</div>'
        f'<div style="flex:1;min-width:0">'
        f'<div style="font-family:\'Space Grotesk\';font-size:19px;font-weight:600;'
        f'color:#f2f4f8;letter-spacing:-0.012em;line-height:1.2">{esc(agent.display_name)}</div>'
        f'<div class="mono subtle" style="margin-top:2px;font-size:10.5px">'
        f'{esc(agent.agent_id)} &middot; <span style="color:{th["glow"]}">{hf_badge}</span>'
        f'</div></div></div>'
        # Location + age
        f'<div class="subtle" style="display:flex;gap:14px;flex-wrap:wrap;margin-bottom:12px;font-size:11.5px">'
        f'<span>📍 {esc(agent.current_tile)}</span>'
        f'<span>age {agent.age} &middot; {agent.life_stage.value}</span>'
        f'</div>'
        # Persona
        f'<div class="section-label">Persona</div>'
        f'<div style="font-size:13px;color:#cfd4dc;line-height:1.6">{esc(agent.persona_card)}</div>'
        f'{goal_html}'
        + (f'<div class="section-label" style="margin-top:12px">Tags</div><div>{tags_html}</div>'
            if tags_html else '')
        + f'{attr_html}{rel_html}{story_html}'
        + '</div>'
    )

# Final dock-bottom wrapper
dock_class = "with-agent" if agent_block else "chronicle-only"
st.markdown(
    f'<div class="dock-bottom {dock_class}">{agent_block}{chronicle_block}</div>',
    unsafe_allow_html=True,
)

# ── Inspect selector — lives visually inside the Chronicle card header ──
# Must be a Streamlit widget (not HTML) so clicks don't trigger navigation.
# Positioned via CSS `.st-key-inspect-bar` to float over the Chronicle card top.
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


# Codex is accessible via the "Story Library" button in sidebar.
