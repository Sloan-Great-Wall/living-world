"""Shared map-view constants and helpers.

Originally hosted the SVG world-map renderer (`render_world_svg`) and the
Chronicle ticker (`render_ticker_html`). Both were replaced by
`canvas_map.py` (Canvas world map) and inline HTML in `app.py`
(Chronicle) respectively. The remaining exports are shared styling
constants + an emoji lookup that several modules still import.
"""

from __future__ import annotations


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
