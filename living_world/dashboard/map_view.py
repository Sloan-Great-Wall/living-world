"""World map — inline SVG with per-agent clickable links.

Aesthetic: dark editorial minimalism with game-UI flourishes
(Starfield cool slate + Octopath warm amber accents).

Clicking an agent sets `?agent=<id>` in the URL — Streamlit reads it back
via `st.query_params` and updates the detail card.
"""

from __future__ import annotations

import html

from living_world.core.world import World


PACK_THEMES: dict[str, dict[str, str]] = {
    "scp": {
        "wall": "#1f2a3a",
        "floor": "#0d131c",
        "floor_light": "#121a25",
        "accent": "#5a7fa3",
        "glow": "#8fb4d9",
        "text": "#cbd6e4",
        "emblem": "◉",
    },
    "liaozhai": {
        "wall": "#3a2418",
        "floor": "#150d08",
        "floor_light": "#1d140d",
        "accent": "#b08250",
        "glow": "#d4a373",
        "text": "#e8d4b8",
        "emblem": "❖",
    },
    "cthulhu": {
        "wall": "#2a1d3d",
        "floor": "#0e0817",
        "floor_light": "#150f24",
        "accent": "#8060a5",
        "glow": "#b091d1",
        "text": "#d6c7e4",
        "emblem": "✦",
    },
}

TAG_EMOJI_RULES: list[tuple[str, str]] = [
    ("great-old-one", "🌀"), ("outer-god", "🌌"), ("deity", "⚖️"),
    ("permanent_historical", "👑"), ("anomaly", "◈"),
    ("demon", "😈"), ("ghost", "◐"), ("fox-spirit", "🦊"),
    ("hybrid", "🐟"), ("mi-go", "🦋"), ("dreamer", "◎"),
    ("monk", "卍"), ("cultist", "🕯"), ("ai", "◾"),
    ("o5", "◉"), ("elite", "✦"), ("field-agent", "◇"),
    ("investigator", "◆"), ("law-enforcement", "◆"),
    ("psychologist", "✎"), ("antiquarian", "❧"), ("artist", "✎"),
    ("d-class", "◍"), ("scholar", "✒"), ("academic", "✒"),
    ("researcher", "⚗"), ("staff", "◦"),
    ("scp", "◉"), ("cthulhu", "✦"), ("liaozhai", "❖"),
]


def _agent_emoji(tags: set[str]) -> str:
    for needle, emo in TAG_EMOJI_RULES:
        if needle in tags:
            return emo
    return "●"


def render_world_svg(
    world: World,
    *,
    selected_agent_id: str | None = None,
    base_params: dict[str, str] | None = None,
) -> str:
    """Inline SVG with clickable agents.

    Each agent circle is wrapped in an SVG `<a>` that navigates to
    `?agent=<id>` (preserving any other base_params provided).
    """
    base_params = base_params or {}
    tiles = list(world.all_tiles())
    if not tiles:
        return "<svg width='400' height='120'><text x='10' y='60' fill='#888'>No tiles.</text></svg>"

    by_pack: dict[str, list] = {}
    for t in tiles:
        by_pack.setdefault(t.primary_pack, []).append(t)

    TILE_W, TILE_H = 220, 160
    GAP_X, GAP_Y = 16, 24
    PAD_X, PAD_Y = 24, 24
    HEADER_H = 44
    cols = 4

    defs: list[str] = []
    defs.append(
        '<radialGradient id="vignette" cx="50%" cy="45%" r="75%">'
        '<stop offset="55%" stop-color="rgba(0,0,0,0)"/>'
        '<stop offset="100%" stop-color="rgba(0,0,0,0.55)"/>'
        '</radialGradient>'
    )
    for pid, th in PACK_THEMES.items():
        defs.append(f'<filter id="glow-{pid}"><feGaussianBlur stdDeviation="3"/></filter>')

    parts: list[str] = []
    y = PAD_Y
    max_w = PAD_X * 2 + cols * (TILE_W + GAP_X) - GAP_X

    for pack_id in ("scp", "liaozhai", "cthulhu"):
        if pack_id not in by_pack:
            continue
        th = PACK_THEMES[pack_id]
        pack_tiles = by_pack[pack_id]

        parts.append(
            f'<text x="{PAD_X}" y="{y + 22}" fill="{th["text"]}" '
            f'font-family="Space Grotesk, Inter, sans-serif" '
            f'font-size="14" font-weight="600" letter-spacing="3">'
            f'{th["emblem"]}  {pack_id.upper()}'
            f'</text>'
            f'<text x="{PAD_X + 180}" y="{y + 22}" fill="#5a6270" '
            f'font-family="JetBrains Mono, monospace" font-size="10" letter-spacing="1">'
            f'{len(pack_tiles)} LOCATIONS'
            f'</text>'
            f'<line x1="{PAD_X}" y1="{y + 32}" x2="{max_w - PAD_X}" y2="{y + 32}" '
            f'stroke="{th["accent"]}" stroke-opacity="0.25" stroke-width="1"/>'
        )
        y += HEADER_H

        for i, tile in enumerate(pack_tiles):
            col = i % cols
            row = i // cols
            tx = PAD_X + col * (TILE_W + GAP_X)
            ty = y + row * (TILE_H + GAP_Y)

            parts.append(
                f'<rect x="{tx}" y="{ty}" width="{TILE_W}" height="{TILE_H}" '
                f'fill="{th["floor"]}" stroke="{th["accent"]}" stroke-opacity="0.35" '
                f'stroke-width="1" rx="4"/>'
            )
            parts.append(
                f'<rect x="{tx}" y="{ty}" width="{TILE_W}" height="{TILE_H // 2}" '
                f'fill="{th["floor_light"]}" opacity="0.4" rx="4"/>'
            )
            parts.append(
                f'<text x="{tx + 14}" y="{ty + 20}" fill="{th["text"]}" '
                f'font-family="Inter, sans-serif" font-size="12" font-weight="600">'
                f'{html.escape(tile.display_name[:24])}</text>'
                f'<text x="{tx + TILE_W - 14}" y="{ty + 20}" fill="#5a6270" '
                f'font-family="JetBrains Mono, monospace" font-size="9" text-anchor="end" '
                f'letter-spacing="0.5">'
                f'{html.escape(tile.tile_type[:16])}</text>'
            )
            parts.append(
                f'<line x1="{tx + 14}" y1="{ty + 28}" x2="{tx + TILE_W - 14}" y2="{ty + 28}" '
                f'stroke="{th["accent"]}" stroke-opacity="0.2"/>'
            )

            agents = world.agents_in_tile(tile.tile_id)
            inner_top = ty + 42
            inner_left = tx + 14
            inner_right = tx + TILE_W - 14
            inner_w = inner_right - inner_left
            slots_per_row = 3
            row_h = 38
            for ai, agent in enumerate(agents[:9]):
                ac = ai % slots_per_row
                ar = ai // slots_per_row
                cx = int(inner_left + ac * (inner_w / slots_per_row) + (inner_w / slots_per_row) / 2)
                cy = int(inner_top + ar * row_h + 14)
                is_sel = agent.agent_id == selected_agent_id
                is_hf = agent.is_historical_figure

                # Display only (no link — clicks happen via sidebar selector)
                if is_hf:
                    parts.append(
                        f'<circle cx="{cx}" cy="{cy}" r="15" fill="{th["glow"]}" '
                        f'opacity="0.12" filter="url(#glow-{pack_id})"/>'
                    )
                ring_color = "#e8c56a" if is_sel else th["accent"]
                ring_w = 2.5 if is_sel else 1
                parts.append(
                    f'<circle cx="{cx}" cy="{cy}" r="11" fill="{th["floor_light"]}" '
                    f'stroke="{ring_color}" stroke-width="{ring_w}">'
                    f'<title>{html.escape(agent.display_name)}</title>'
                    f'</circle>'
                )
                emo = _agent_emoji(agent.tags)
                parts.append(
                    f'<text x="{cx}" y="{cy + 4}" fill="{th["text"]}" '
                    f'font-size="12" text-anchor="middle" font-weight="600" '
                    f'pointer-events="none">{emo}</text>'
                )
                name = html.escape(agent.display_name[:11])
                parts.append(
                    f'<text x="{cx}" y="{cy + 24}" fill="{th["text"]}" '
                    f'font-family="Inter, sans-serif" font-size="8.5" text-anchor="middle" '
                    f'opacity="0.75" pointer-events="none">{name}</text>'
                )

            if len(agents) > 9:
                parts.append(
                    f'<text x="{tx + TILE_W - 8}" y="{ty + TILE_H - 8}" '
                    f'fill="{th["glow"]}" font-family="JetBrains Mono, monospace" '
                    f'font-size="9" text-anchor="end" opacity="0.6">'
                    f'+{len(agents) - 9}</text>'
                )

        rows_used = (len(pack_tiles) + cols - 1) // cols
        y += rows_used * (TILE_H + GAP_Y) + 10

    total_h = y + PAD_Y
    parts.append(
        f'<rect x="0" y="0" width="{max_w}" height="{total_h}" '
        f'fill="url(#vignette)" pointer-events="none"/>'
    )

    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="100%" height="{total_h}" '
        f'viewBox="0 0 {max_w} {total_h}" preserveAspectRatio="xMidYMin meet" '
        f'style="background: #07080c; border-radius: 10px; display:block; max-width:100%;">'
        + f'<defs>{"".join(defs)}</defs>'
        + "".join(parts)
        + "</svg>"
    )
    return svg


def render_ticker_html(world: World, *, limit: int = 10) -> str:
    """Recent events styled as a floating card — used for Chronicle panel."""
    events = world.events_since(1)[-limit:]
    if not events:
        return (
            '<div style="padding:20px;color:#5a6270;font-family:Inter,sans-serif;'
            'font-size:13px;text-align:center;letter-spacing:0.2px">'
            '— no events yet · press <b style="color:#e8c56a">▶ Play</b> —</div>'
        )

    chips: list[str] = []
    for e in reversed(events):
        th = PACK_THEMES.get(e.pack_id, PACK_THEMES["scp"])
        tier_glyph = "●●●" if e.tier_used == 3 else ("●●" if e.tier_used == 2 else "●")
        tier_color = "#b091d1" if e.tier_used == 3 else ("#d4a373" if e.tier_used == 2 else "#5a6270")
        body = html.escape(e.best_rendering()[:260])
        chips.append(
            f'<div style="background:{th["floor"]};border-left:2px solid {th["accent"]};'
            f'padding:11px 14px;margin:5px 0;border-radius:3px;'
            f'font-family:Inter,\"Noto Sans SC\",sans-serif;">'
            f'<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:5px">'
            f'<span style="color:{th["glow"]};font-size:10.5px;font-weight:600;letter-spacing:1.2px">'
            f'{th["emblem"]} {html.escape(e.event_kind).upper()}</span>'
            f'<span style="font-family:JetBrains Mono,monospace;font-size:10px;color:#5a6270">'
            f'DAY {e.tick:03d}  <span style="color:{tier_color}">{tier_glyph}</span>'
            f'</span></div>'
            f'<div style="color:{th["text"]};font-size:12.5px;line-height:1.6">{body}</div>'
            f'</div>'
        )
    return (
        '<div style="background:#07080c;padding:10px;border-radius:8px;'
        'max-height:400px;overflow-y:auto">'
        + "".join(chips) + "</div>"
    )
