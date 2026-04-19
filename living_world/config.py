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


ProviderName = Literal["none", "ollama"]


# ---- Tunable groups ----

class LLMSettings(BaseModel):
    """Which backend to use for each tier + model names."""

    # ── Two LLM clients (legacy Tier 2 / Tier 3 names kept for settings.yaml
    # compatibility). Despite the names, only TWO LLM CALL PATHS exist now:
    #
    #   tier2_*  → "agent-layer" client. Used by every agent/* module:
    #              conscience, planner, move_advisor, dialogue, emergent,
    #              perception, self_update. This is the workhorse.
    #
    #   tier3_*  → "narrator" client. Only used by the Narrator (narrative
    #              rewrites of high-importance events) and the Chronicler
    #              (chapter writing). Pick a richer model here if you want
    #              prettier prose; cheaper agent calls then run on tier2.
    #
    # The historical "Tier 2 mid-tier rewrite" path was deleted in 2026-04;
    # the slot remained because the underlying Ollama client is shared by
    # the entire agents/ layer. Renaming would break user settings files.

    tier2_provider: ProviderName = "ollama"
    tier3_provider: ProviderName = "ollama"

    # when provider = ollama
    ollama_base_url: str = "http://localhost:11434"
    ollama_tier2_model: str = "gemma3:4b"   # the "agent-layer" model
    ollama_tier3_model: str = "gemma3:4b"   # the "narrator" model
    ollama_timeout_seconds: float = 60.0

    # future: vllm / openai-compatible endpoints
    openai_base_url: str | None = None
    openai_api_key: str | None = None

    # ─── Subconscious + Conscious architecture ─────────────────────────
    # Rules = subconscious (always running). LLM = conscious (probabilistic,
    # overrides subconscious at high-importance moments).

    # Dynamic dialogue: conscious narrative at Tier 3
    dynamic_dialogue_enabled: bool = True

    # LLM-driven movement: historical figures decide via LLM
    # ── LLM ratio knobs ──
    # The defaults here are tuned to match a System-1/System-2 split that
    # leans further toward conscious deliberation than the original ~95/5.
    # For HF agents we now run System-2 (LLM) on most consequential
    # decisions; ordinary agents stay rules-heavy. This mirrors the
    # observation that protagonists in human cognition get more deliberate
    # thought, while bystanders run on habit.

    llm_movement_enabled: bool = True
    llm_movement_hf_only: bool = True
    llm_movement_chance: float = 0.6   # was 0.3 — HF agents now LLM-thought 60% of moves

    # Conscious event override — when a rule-proposed event happens, the LLM
    # may APPROVE / ADJUST / VETO based on participants' personas + memory.
    # Lower threshold (more events eligible) + higher activation chance
    # (more of those eligible actually go to LLM) ≈ humans deliberating
    # over a wider range of social situations, not just crises.
    conscious_override_enabled: bool = True
    conscious_override_threshold: float = 0.35  # was 0.50 — lower = more events get conscious review
    conscious_override_chance: float = 0.70     # was 0.50 — more eligible events actually fire

    # ── Decision-layer LLM features (goal-driven behavior) ──

    # Rule-path goal bonus: tiles whose name/type contain any token from the
    # agent's current_goal / weekly_plan get this multiplier on their affinity
    # weight. 1.0 = disabled. No LLM call involved — cheap heuristic.
    goal_driven_movement_bonus: float = 1.4

    # Weekly planning: once every 7 ticks, call Tier-2 LLM to produce a short
    # plan for each historical-figure agent. Plan is stored on agent.state_extra
    # and consumed by movement + storyteller.
    weekly_planning_enabled: bool = True
    weekly_planning_hf_only: bool = True

    # Storyteller goal-alignment bonus: events whose kind/description match a
    # resident agent's goal or weekly plan get their weight boosted (capped).
    goal_aligned_event_bonus: float = 1.5

    # Conversation loop: 2-participant events trigger an A→B LLM reaction
    # that mutates the listener's affinity + beliefs based on what happened.
    # Default ON now — this is one of the three "irreplaceable" LLM paths.
    conversation_loop_enabled: bool = True

    # Chronicler (说书人): records emergent highlights as chapters.
    # Strictly descriptive; never influences future events.
    chronicler_enabled: bool = True
    chronicle_every_ticks: int = 14

    # Emergent event proposer: LLM invents novel events on hot tiles.
    # Default ON: this is the System-2 source of novelty (rules can't
    # invent new event kinds). 3/tick is brain-budget sized.
    emergent_events_enabled: bool = True
    emergent_max_per_tick: int = 3

    # Subjective perception: every important event (importance ≥ threshold)
    # is rewritten from each participant's first-person POV before being
    # stored in their memory. Same event → different memory per agent.
    # Cost: 1 LLM call per participant per qualifying event.
    subjective_perception_enabled: bool = True
    subjective_perception_threshold: float = 0.5

    # AgentSelfUpdate: after important events, the LLM speaks AS each
    # participant and reports how their inner state shifted (attributes,
    # needs, emotions, beliefs, goal, motivations, reflection). Replaces
    # the rigid pre-authored stat ripples for important events.
    self_update_enabled: bool = True
    self_update_threshold: float = 0.5



class BudgetSettings(BaseModel):
    """Daily token ceiling for the LLM-narrative pathway."""

    tier3_tokens_per_day: int = 200_000


class ImportanceSettings(BaseModel):
    """Importance threshold for routing an event to Tier-3 LLM narrative."""

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


class MemorySettings(BaseModel):
    """Agent memory / embedding config."""

    enabled: bool = True
    embedder: Literal["none", "ollama"] = "ollama"
    ollama_embed_model: str = "nomic-embed-text"
    reflect_every_ticks: int = 7
    recall_top_k: int = 5


class PersistenceSettings(BaseModel):
    # how often (every N ticks) to snapshot full world state; events always
    # append every tick. Aligned to 7 (weekly cadence) — same boundary as
    # the planner / reflect / demote phases, so all maintenance happens on
    # the same tick instead of at staggered "magic numbers".
    snapshot_every_ticks: int = 7


class DisplaySettings(BaseModel):
    """What the user sees. Completely separate from what the LLM receives."""
    locale: Literal["en", "zh"] = "en"
    # "en" → show English source content as-is + no translation of generated text
    # "zh" → show Chinese locale overlay for static content + translate generated text
    translate_generated: bool = False  # if True AND locale=zh, LLM output gets translated


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
    display: DisplaySettings = Field(default_factory=DisplaySettings)
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
