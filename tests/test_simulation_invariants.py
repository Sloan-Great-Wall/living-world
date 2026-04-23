"""Run a real simulation in pytest, then assert all invariants hold.

This is the Layer-3/4 net that catches statistical / time-series bugs
the unit tests can't see. Runs rules-only (no Ollama) so it's fast
(~2-3s) and deterministic.

For the full LLM-stack version, run `lw smoke --ticks 12` from CLI.
"""

from __future__ import annotations

import pytest

from living_world import PACKS_DIR
from living_world.config import load_settings
from living_world.factory import bootstrap_world, make_engine
from living_world.invariants import check_all, summary


@pytest.fixture(scope="module")
def short_run():
    """Bootstrap 3 packs, run 6 rule-layer ticks, return (world, engine)."""
    settings = load_settings()
    # Disable everything LLM-bound so this runs fast + deterministic
    settings.llm.tier2_provider = "none"
    settings.llm.tier3_provider = "none"
    settings.llm.dynamic_dialogue_enabled = False
    settings.llm.llm_movement_enabled = False
    settings.llm.weekly_planning_enabled = False
    settings.llm.conversation_loop_enabled = False
    settings.llm.chronicler_enabled = False
    settings.llm.emergent_events_enabled = False
    settings.llm.subjective_perception_enabled = False
    settings.llm.self_update_enabled = False
    settings.llm.conscious_override_enabled = False
    settings.memory.enabled = False

    world, loaded = bootstrap_world(PACKS_DIR, ["scp", "liaozhai", "cthulhu"])
    engine = make_engine(world, loaded, settings, seed=42)
    engine.run(6)
    return world, engine


def test_smoke_run_produces_events(short_run):
    world, _ = short_run
    assert world.event_count() > 0, "rules-only run should still produce events"


def test_invariant_no_unfilled_placeholders(short_run):
    world, engine = short_run
    from living_world.invariants import no_unfilled_placeholders

    r = no_unfilled_placeholders(world, engine)
    assert r.passed, r.detail


def test_invariant_same_kind_per_tick_capped(short_run):
    world, engine = short_run
    from living_world.invariants import same_kind_per_tick_capped

    r = same_kind_per_tick_capped(world, engine)
    assert r.passed, r.detail


def test_invariant_all_event_participants_real(short_run):
    world, engine = short_run
    from living_world.invariants import all_event_participants_real

    r = all_event_participants_real(world, engine)
    assert r.passed, r.detail


def test_invariant_alive_count_monotone(short_run):
    world, engine = short_run
    from living_world.invariants import alive_count_monotone

    r = alive_count_monotone(world, engine)
    assert r.passed, r.detail


def test_invariant_no_orphan_chapters(short_run):
    world, engine = short_run
    from living_world.invariants import no_orphan_chapters

    r = no_orphan_chapters(world, engine)
    assert r.passed, r.detail


def test_check_all_passes_on_clean_run(short_run):
    """Aggregate check — entire battery must pass on a fresh rules-only run."""
    world, engine = short_run
    results = check_all(world, engine)
    passed, warned, failed = summary(results)
    assert failed == 0, "\n".join(f"❌ {r.name}: {r.detail}" for r in results if not r.passed)
