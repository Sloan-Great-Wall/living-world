"""Locale overlay loading — en vs zh content isolation."""

from __future__ import annotations

from pathlib import Path

from living_world.locale import LocaleOverlay

PACKS_DIR = Path(__file__).resolve().parents[1] / "world_packs"


def test_zh_overlay_loads_scp():
    overlay = LocaleOverlay(PACKS_DIR / "scp", "zh")
    assert overlay.has_content
    zh_name = overlay.agent_field("SCP-173", "display_name")
    assert zh_name is not None
    assert "雕塑" in zh_name


def test_zh_overlay_loads_liaozhai():
    overlay = LocaleOverlay(PACKS_DIR / "liaozhai", "zh")
    zh_name = overlay.agent_field("nie-xiaoqian", "display_name")
    assert zh_name is not None
    assert "聂小倩" in zh_name


def test_en_has_no_overlay():
    """English is the source-of-truth — no overlay needed."""
    overlay = LocaleOverlay(PACKS_DIR / "scp", "en")
    assert not overlay.has_content


def test_missing_field_returns_fallback():
    overlay = LocaleOverlay(PACKS_DIR / "scp", "zh")
    result = overlay.agent_field("SCP-173", "nonexistent_field", fallback="default")
    assert result == "default"


def test_tile_overlay():
    overlay = LocaleOverlay(PACKS_DIR / "scp", "zh")
    zh_tile = overlay.tile_field("con-173", "display_name")
    assert zh_tile is not None
    assert "收容室" in zh_tile
