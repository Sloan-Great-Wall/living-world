"""Unified settings for the entire project.

Single source of truth for all tunables. Loaded from:
  1. `settings.yaml` at project root (if present)
  2. Environment variables prefixed LIVING_WORLD_*
  3. CLI flags (override both)

A YAML schema also enables the Streamlit dashboard's "Settings" tab to
edit values live and write back.
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field


ProviderName = Literal["none", "mock", "ollama"]


# ---- Tunable groups ----

class LLMSettings(BaseModel):
    """Which backend to use for each tier + model names."""

    tier2_provider: ProviderName = "mock"
    tier3_provider: ProviderName = "mock"

    # when provider = ollama
    ollama_base_url: str = "http://localhost:11434"
    ollama_tier2_model: str = "gemma3:4b"
    ollama_tier3_model: str = "gemma3:4b"  # same by default for MacBook; swap to phi4 etc on GPU
    ollama_timeout_seconds: float = 60.0

    # future: vllm / openai-compatible endpoints
    openai_base_url: str | None = None
    openai_api_key: str | None = None

    # ─── Advanced LLM-driven features (all opt-in, all more expensive) ───
    # Dynamic dialogue: at Tier 3, LLM writes full narrative from persona+memory
    # instead of template substitution. 1 LLM call per spotlight event.
    dynamic_dialogue_enabled: bool = False

    # Debate Phase: multi-agent round (orchestrator + N stakeholders + synth).
    # 5-7 LLM calls per triggered event. Very rich, very slow.
    debate_enabled: bool = False
    debate_threshold: float = 0.75
    debate_min_stakeholders: int = 3
    debate_max_stakeholders: int = 5

    # LLM-driven movement: historical figures ask the LLM where to go.
    # Off by default — one LLM call per eligible tick per agent.
    llm_movement_enabled: bool = False
    llm_movement_hf_only: bool = True
    llm_movement_chance: float = 0.3


class BudgetSettings(BaseModel):
    """Daily token ceilings; router auto-downgrades when hit."""

    tier2_tokens_per_day: int = 1_000_000
    tier3_tokens_per_day: int = 200_000


class ImportanceSettings(BaseModel):
    """Thresholds for routing to each tier.

    Calibrated 2026-04-15: target distribution ~95% T1 / ~4% T2 / ~1% T3.
    Raise thresholds if T2/T3 ratio creeps up; the content team should
    earn Tier 2+ with explicit template `base_importance` settings.
    """

    tier2_threshold: float = 0.35
    tier3_threshold: float = 0.65


class HistoricalFigureSettings(BaseModel):
    spotlight_threshold: float = 0.6
    notable_threshold: float = 0.3
    notable_count_for_promotion: int = 3
    strong_relationship_affinity: int = 70
    inactivity_days_for_demotion: int = 30


class StorytellerOverride(BaseModel):
    """Optional global override of pack storyteller configs (if set)."""

    force_personality: Literal["", "balanced", "peaceful", "chaotic"] = ""
    max_events_per_day_override: int | None = None
    tension_target_override: float | None = None


class SimulationSettings(BaseModel):
    default_packs: list[str] = Field(default_factory=lambda: ["scp", "liaozhai", "cthulhu"])
    default_days: int = 30
    default_seed: int = 42
    packs_dir: str = "world_packs"


class I18nSettings(BaseModel):
    """Output translation for non-English user locales."""

    enabled: bool = False
    target_locale: Literal["en", "zh", "ja"] = "zh"
    provider: Literal["noop", "ollama"] = "ollama"
    ollama_translate_model: str = "gemma3:4b"
    cache_size: int = 4096


class MemorySettings(BaseModel):
    """Agent memory / embedding config."""

    enabled: bool = False
    embedder: Literal["none", "mock", "ollama"] = "mock"
    ollama_embed_model: str = "nomic-embed-text"
    reflect_every_ticks: int = 7
    recall_top_k: int = 5


class PersistenceSettings(BaseModel):
    backend: Literal["memory", "postgres"] = "memory"
    postgres_dsn: str = "postgresql://lw:lw_dev_only@localhost:5433/living_world"
    # how often (every N ticks) to snapshot full world state; events always append every tick
    snapshot_every_ticks: int = 10


class DashboardSettings(BaseModel):
    host: str = "localhost"
    port: int = 8501
    page_title: str = "Living World — Stage A"


class Settings(BaseModel):
    """Root settings object."""

    llm: LLMSettings = Field(default_factory=LLMSettings)
    budget: BudgetSettings = Field(default_factory=BudgetSettings)
    importance: ImportanceSettings = Field(default_factory=ImportanceSettings)
    historical_figures: HistoricalFigureSettings = Field(default_factory=HistoricalFigureSettings)
    storyteller: StorytellerOverride = Field(default_factory=StorytellerOverride)
    simulation: SimulationSettings = Field(default_factory=SimulationSettings)
    memory: MemorySettings = Field(default_factory=MemorySettings)
    i18n: I18nSettings = Field(default_factory=I18nSettings)
    persistence: PersistenceSettings = Field(default_factory=PersistenceSettings)
    dashboard: DashboardSettings = Field(default_factory=DashboardSettings)


DEFAULT_SETTINGS_PATH = Path(__file__).resolve().parent.parent / "settings.yaml"


def load_settings(path: Path | None = None) -> Settings:
    p = path or DEFAULT_SETTINGS_PATH
    if not p.exists():
        return Settings()
    with p.open("r", encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}
    return Settings(**raw)


def save_settings(settings: Settings, path: Path | None = None) -> None:
    p = path or DEFAULT_SETTINGS_PATH
    with p.open("w", encoding="utf-8") as f:
        yaml.safe_dump(settings.model_dump(), f, allow_unicode=True, sort_keys=False)
