"""Codex rendering — show all authored personas + event templates.

Used by the Dashboard 'Codex' tab to let the team see *all* configured content
(not just what's emerged in a run). This is how you verify content work.
"""

from __future__ import annotations

import html

from living_world.dashboard.map_view import PACK_THEMES, _agent_emoji
from living_world.world_pack.loader import WorldPack


def render_persona_codex_html(packs: list[WorldPack]) -> str:
    """Grid of persona cards — every configured character, grouped by pack."""
    sections: list[str] = []
    for pack in packs:
        th = PACK_THEMES.get(pack.pack_id, PACK_THEMES["scp"])
        cards: list[str] = []
        for a in pack.personas:
            emo = _agent_emoji(a.tags)
            hf = "★" if a.is_historical_figure else ""
            tags_html = "".join(
                f'<span style="font-size:10px;background:{th["floor"]};color:{th["text"]};'
                f'border:1px solid {th["accent"]};padding:1px 6px;border-radius:2px;margin:2px 3px 0 0;'
                f'display:inline-block">{html.escape(t)}</span>'
                for t in sorted(a.tags)
            )
            attr_html = "".join(
                f'<div style="font-size:11px;color:#8a8f9c;margin-top:2px">'
                f'{html.escape(str(k))}: <span style="color:{th["glow"]}">{html.escape(str(v))}</span></div>'
                for k, v in list(a.attributes.items())[:5]
            )
            cards.append(
                f'<div style="background:linear-gradient(180deg,{th["floor"]} 0%,{th["floor_light"]} 100%);'
                f'border:1px solid {th["accent"]};border-radius:4px;padding:12px;'
                f'display:flex;flex-direction:column;gap:6px;">'
                f'<div style="display:flex;align-items:center;gap:8px">'
                f'<div style="font-size:28px;line-height:1">{emo}</div>'
                f'<div style="flex:1;min-width:0">'
                f'<div style="font-size:14px;font-weight:600;color:{th["text"]};'
                f'white-space:nowrap;overflow:hidden;text-overflow:ellipsis">'
                f'{html.escape(a.display_name)} <span style="color:{th["glow"]}">{hf}</span></div>'
                f'<div style="font-size:10px;color:#6a7080">{html.escape(a.agent_id)} · age {a.age}</div>'
                f'</div></div>'
                f'<div style="font-size:12px;color:#c8cede;line-height:1.55">'
                f'{html.escape(a.persona_card or "—")}</div>'
                + (f'<div style="margin-top:4px;font-size:11px;color:#7a8297">🎯 {html.escape(a.current_goal)}</div>' if a.current_goal else "")
                + (f'<div style="margin-top:4px">{tags_html}</div>' if a.tags else "")
                + (f'<div style="margin-top:4px;padding-top:6px;border-top:1px dashed {th["accent"]}40">{attr_html}</div>' if attr_html else "")
                + '</div>'
            )
        sections.append(
            f'<div style="margin-bottom:32px">'
            f'<div style="font-size:16px;font-weight:600;color:{th["text"]};'
            f'letter-spacing:1px;margin-bottom:12px;padding-bottom:6px;'
            f'border-bottom:1px solid {th["accent"]}">'
            f'{th["emblem"]} {pack.pack_id.upper()} <span style="color:#6a7080;font-weight:400">· '
            f'{len(pack.personas)} characters</span></div>'
            f'<div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(280px,1fr));gap:12px">'
            + "".join(cards) + '</div></div>'
        )
    return '<div style="font-family:Inter,-apple-system,system-ui,sans-serif">' + "".join(sections) + "</div>"


def render_story_codex_html(packs: list[WorldPack]) -> str:
    """All event templates — 'fixed plot fragments'.

    Each row shows: event_kind, description, dice, cooldown, and success template.
    """
    sections: list[str] = []
    for pack in packs:
        th = PACK_THEMES.get(pack.pack_id, PACK_THEMES["scp"])
        rows: list[str] = []
        events_sorted = sorted(pack.events.values(), key=lambda e: -e.base_importance)
        for e in events_sorted:
            dice = e.dice_roll or {}
            dc = dice.get("dc", "—")
            stat = dice.get("stat", "—")
            cd = e.cooldown_days
            imp = e.base_importance
            # Preview: success template if present, else first available outcome
            preview = ""
            for key in ("success", "neutral", "failure"):
                o = (e.outcomes or {}).get(key, {}) or {}
                if o.get("template"):
                    preview = o["template"]
                    break

            tier_badge = "T3" if imp >= 0.65 else ("T2" if imp >= 0.35 else "T1")
            tier_color = "#b080ff" if tier_badge == "T3" else ("#ffd76a" if tier_badge == "T2" else "#7a8297")

            rows.append(
                f'<div style="background:{th["floor"]};border-left:2px solid {th["accent"]};'
                f'padding:10px 14px;margin:4px 0;border-radius:3px;font-family:Inter,sans-serif">'
                f'<div style="display:flex;justify-content:space-between;align-items:baseline;gap:12px">'
                f'<div style="font-size:13px;font-weight:600;color:{th["text"]}">'
                f'{html.escape(e.event_kind)}</div>'
                f'<div style="font-size:10px;color:#6a7080;font-family:JetBrains Mono,monospace">'
                f'<span style="color:{tier_color}">{tier_badge}</span> · imp {imp:.2f} · '
                f'stat {html.escape(str(stat))} vs DC {html.escape(str(dc))} · cd {cd}d'
                f'</div></div>'
                f'<div style="font-size:12px;color:#8a8f9c;margin-top:2px">{html.escape(e.description or "")}</div>'
                + (f'<div style="font-size:11px;color:#c8cede;margin-top:6px;font-style:italic;line-height:1.5">↪ {html.escape(preview)}</div>' if preview else "")
                + '</div>'
            )
        sections.append(
            f'<div style="margin-bottom:28px">'
            f'<div style="font-size:16px;font-weight:600;color:{th["text"]};'
            f'letter-spacing:1px;margin-bottom:10px;padding-bottom:6px;border-bottom:1px solid {th["accent"]}">'
            f'{th["emblem"]} {pack.pack_id.upper()} <span style="color:#6a7080;font-weight:400">· '
            f'{len(pack.events)} story fragments</span></div>'
            + "".join(rows) + '</div>'
        )
    return '<div>' + "".join(sections) + '</div>'


def render_tiles_codex_html(packs: list[WorldPack]) -> str:
    """Show every tile with description + tension bias."""
    sections: list[str] = []
    for pack in packs:
        th = PACK_THEMES.get(pack.pack_id, PACK_THEMES["scp"])
        rows: list[str] = []
        for t in pack.tiles:
            tension_bar = int(t.tension_bias * 10)
            bar = "█" * tension_bar + "░" * (10 - tension_bar)
            rows.append(
                f'<div style="background:{th["floor"]};border-left:2px solid {th["accent"]};'
                f'padding:10px 14px;margin:4px 0;border-radius:3px;font-family:Inter,sans-serif">'
                f'<div style="display:flex;justify-content:space-between;align-items:baseline">'
                f'<div style="font-size:13px;font-weight:600;color:{th["text"]}">'
                f'{html.escape(t.display_name)}</div>'
                f'<div style="font-size:10px;color:#6a7080;font-family:JetBrains Mono,monospace">'
                f'{html.escape(t.tile_type)}</div></div>'
                f'<div style="font-size:11px;color:#8a8f9c;margin-top:2px;line-height:1.5">'
                f'{html.escape(t.description or "—")}</div>'
                f'<div style="font-size:10px;color:{th["glow"]};margin-top:4px;'
                f'font-family:JetBrains Mono,monospace">tension {bar} {t.tension_bias:.2f}</div>'
                f'</div>'
            )
        sections.append(
            f'<div style="margin-bottom:24px">'
            f'<div style="font-size:16px;font-weight:600;color:{th["text"]};'
            f'letter-spacing:1px;margin-bottom:10px;padding-bottom:6px;border-bottom:1px solid {th["accent"]}">'
            f'{th["emblem"]} {pack.pack_id.upper()} <span style="color:#6a7080;font-weight:400">· '
            f'{len(pack.tiles)} locations</span></div>'
            + "".join(rows) + '</div>'
        )
    return '<div>' + "".join(sections) + '</div>'
