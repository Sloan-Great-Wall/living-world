"""Importance scoring — decides tier routing.

See stat-machine-design.md §'升级判定'.

v2 calibration (2026-04-15):
- Use template's `base_importance` as the dominant signal (it's per-event, hand-tuned).
- Historical-figure bonus is small and only if MULTIPLE are involved.
- Target distribution: ~95% tier1, ~4% tier2, ~1% tier3.
"""

from __future__ import annotations

from living_world.core.agent import Agent
from living_world.core.event import LegendEvent


# Explicit spotlight event kinds that should always push toward Tier 3.
SPOTLIGHT_EVENT_KINDS: set[str] = {
    "containment-breach",       # SCP Keter breach
    "descent",                   # Cthulhu sanity collapse
    "possession",                # Cthulhu body takeover
    "cult-ritual",               # Cthulhu rite
    "renlao-tryst",              # Liaozhai human-ghost love
    "karmic-return",             # Liaozhai ghost return
    "heart-swap",                # Liaozhai body swap
    "yaksha-attack",             # Liaozhai demon
    "682-tests",                 # SCP high-risk test
    "silver-key",                # Cthulhu revelation
    "096-sighting-risk",         # SCP photography risk
    "o5-memo",                   # SCP council decree
}


def score_event_importance(
    event: LegendEvent,
    participants: list[Agent],
    *,
    tile_has_active_player: bool = False,
    base_importance: float = 0.1,
) -> float:
    """Return 0.0-1.0.

    Primary signal: `base_importance` from event template (caller passes it in).
    Modifiers: participant composition + spotlight kinds + player proximity.
    """
    score = float(base_importance)

    # Spotlight kinds only count when template author already marked them important.
    # This prevents every "dagon-ritual with base 0.3" from jumping to tier 3.
    if event.event_kind in SPOTLIGHT_EVENT_KINDS and base_importance >= 0.5:
        score = max(score, 0.7)

    # Historical figures: only 2+ HFs interacting is notable.
    hf_count = sum(1 for p in participants if p.is_historical_figure)
    if hf_count >= 2:
        score += 0.08
    # Single HF adds nothing — they're common in our seeded world.

    # Relationship changes only matter at scale
    if len(event.relationship_changes) >= 2:
        score += 0.05

    # Player present is huge — always promote
    if tile_has_active_player:
        score += 0.35

    # Catastrophic failure in already-big events
    if event.outcome == "failure" and base_importance >= 0.5:
        score += 0.1

    return min(1.0, max(0.0, score))
