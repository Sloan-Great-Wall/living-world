"""Importance scoring regression tests."""

from __future__ import annotations

from living_world.core.agent import Agent
from living_world.core.event import LegendEvent
from living_world.statmachine.importance import score_event_importance


def _agent(aid: str, hf: bool = False) -> Agent:
    return Agent(
        agent_id=aid, pack_id="test", display_name=aid,
        persona_card="test persona",
        is_historical_figure=hf,
    )


def _event(kind: str, outcome: str = "neutral", rel_changes: int = 0) -> LegendEvent:
    return LegendEvent(
        event_id="00000000-0000-0000-0000-000000000001",
        tick=1, pack_id="test", tile_id="t1",
        event_kind=kind, outcome=outcome,
        participants=[],
        relationship_changes=[{"a": "x", "b": "y"}] * rel_changes,
    )


def test_routine_event_stays_tier1():
    score = score_event_importance(
        _event("chat"), [_agent("a"), _agent("b")],
        base_importance=0.1,
    )
    assert score < 0.35, f"routine chat should stay Tier 1, got {score}"


def test_hf_single_does_not_promote():
    """One HF alone is common in our world, should not bump."""
    score = score_event_importance(
        _event("chat"), [_agent("a", hf=True), _agent("b")],
        base_importance=0.1,
    )
    assert score < 0.35


def test_double_hf_drama_pushes_to_tier2():
    score = score_event_importance(
        _event("dispute", rel_changes=2), [_agent("a", hf=True), _agent("b", hf=True)],
        base_importance=0.25,
    )
    assert score >= 0.35, f"double HF drama should reach Tier 2, got {score}"


def test_spotlight_kind_with_high_base_reaches_tier3():
    score = score_event_importance(
        _event("cult-ritual"), [_agent("a", hf=True), _agent("b", hf=True)],
        base_importance=0.7,
    )
    assert score >= 0.65


def test_player_presence_promotes_aggressively():
    score = score_event_importance(
        _event("chat"), [_agent("a")],
        base_importance=0.1,
        tile_has_active_player=True,
    )
    assert score >= 0.35, "player-present interactions must be at least Tier 2"
