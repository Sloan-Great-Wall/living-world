"""Locale layer — dual-language content isolation.

Architecture:
  1. STATIC CONTENT (personas, events, tiles):
     English = source of truth at world_packs/<pack>/*.yaml
     Chinese = optional overlay at world_packs/<pack>/locale/zh/*.yaml
     Other locales follow same pattern: locale/<lang_code>/

  2. RUNTIME (LLM input):
     Always English. Models receive English persona_card, events, prompts.

  3. DISPLAY (UI output):
     If user locale = "en", show English as-is.
     If user locale = "zh", look up Chinese overlay for static content;
     for LLM-generated text, prompt the LLM to use the target language directly.

This module provides:
  - load_locale_overlay(): reads zh/ personas and returns a dict of {field: localized_value}
  - localize_agent(): returns display-ready fields for a given locale
  - localize_event_template(): returns localized event template text
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml


def _load_yaml(p: Path) -> dict[str, Any] | None:
    if not p.exists():
        return None
    with p.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


class LocaleOverlay:
    """Caches locale-specific field overrides for a pack.

    Usage:
        overlay = LocaleOverlay(Path("world_packs/liaozhai"), "zh")
        zh_name = overlay.agent_field("nie-xiaoqian", "display_name", fallback="Nie Xiaoqian")
    """

    def __init__(self, pack_dir: Path, lang: str = "zh") -> None:
        self.lang = lang
        self._agents: dict[str, dict[str, Any]] = {}
        self._events: dict[str, dict[str, Any]] = {}
        self._tiles: dict[str, dict[str, Any]] = {}

        locale_dir = pack_dir / "locale" / lang
        if not locale_dir.exists():
            return

        # Load persona overlays
        persona_dir = locale_dir / "personas"
        if persona_dir.exists():
            for f in persona_dir.glob("*.yaml"):
                data = _load_yaml(f)
                if data and "agent_id" in data:
                    self._agents[data["agent_id"]] = data

        # Load event overlays
        events_dir = locale_dir / "events"
        if events_dir.exists():
            for f in events_dir.glob("*.yaml"):
                data = _load_yaml(f) or {}
                for ev in data.get("events", []):
                    if "event_kind" in ev:
                        self._events[ev["event_kind"]] = ev

        # Load tile overlays
        tiles_dir = locale_dir / "tiles"
        if tiles_dir.exists():
            for f in tiles_dir.glob("*.yaml"):
                data = _load_yaml(f) or {}
                for t in data.get("tiles", []):
                    if "tile_id" in t:
                        self._tiles[t["tile_id"]] = t

    def agent_field(self, agent_id: str, field: str, fallback: Any = None) -> Any:
        """Return localized field for an agent, or fallback if not available."""
        return self._agents.get(agent_id, {}).get(field, fallback)

    def event_template(self, event_kind: str, outcome: str, fallback: str = "") -> str:
        """Return localized event template for a specific outcome."""
        ev = self._events.get(event_kind, {})
        outcomes = ev.get("outcomes", {})
        return outcomes.get(outcome, {}).get("template", fallback)

    def tile_field(self, tile_id: str, field: str, fallback: Any = None) -> Any:
        return self._tiles.get(tile_id, {}).get(field, fallback)

    @property
    def has_content(self) -> bool:
        return bool(self._agents or self._events or self._tiles)


class LocaleRegistry:
    """Manages locale overlays for all loaded packs."""

    def __init__(self) -> None:
        self._overlays: dict[tuple[str, str], LocaleOverlay] = {}  # (pack_id, lang) → overlay

    def load(self, pack_id: str, pack_dir: Path, lang: str) -> LocaleOverlay:
        key = (pack_id, lang)
        if key not in self._overlays:
            self._overlays[key] = LocaleOverlay(pack_dir, lang)
        return self._overlays[key]

    def get(self, pack_id: str, lang: str) -> LocaleOverlay | None:
        return self._overlays.get((pack_id, lang))
