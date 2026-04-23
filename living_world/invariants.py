"""Simulation invariants — properties that should hold for ANY healthy run.

These catch the class of bugs that single-call unit tests miss: statistical,
multi-tick, distribution-of-outputs problems. The 2026-04-22 6-tick run
exposed three such bugs (?-placeholder leak, emergent pair fixation, same-
kind same-tick repetition) that 70 passing unit tests said nothing about.

Each invariant takes (world, engine) and returns InvariantResult. Run all
of them via `check_all(world, engine)`. Used by:
  - `lw smoke` CLI (human-readable report after each run)
  - tests/test_simulation_invariants.py (pytest assertion)
  - dashboard "Health" panel (future)

When you add a new invariant, ADD A REGRESSION TEST in
tests/test_new_modules.py that asserts the bug it catches exists in
broken code. This forces invariants to be falsifiable, not vacuous.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass


@dataclass
class InvariantResult:
    name: str
    passed: bool
    detail: str
    severity: str = "error"  # error | warn | info

    @property
    def emoji(self) -> str:
        return "✅" if self.passed else ("⚠️" if self.severity == "warn" else "❌")


# ── individual invariants ───────────────────────────────────────────────────


def no_unfilled_placeholders(world, engine) -> InvariantResult:
    """Bug A regression: no event narrative contains a literal "?" or
    a Template substitution leak."""
    bad = []
    for e in world.events_since(1):
        text = (e.template_rendering or "") + " " + (e.spotlight_rendering or "")
        # Lone ? characters (not in valid punctuation context)
        if " ? " in text or text.endswith(" ?") or "${" in text or "$a" in text:
            bad.append(f"d{e.tick:03d}/{e.event_kind}")
    return InvariantResult(
        name="no_unfilled_placeholders",
        passed=not bad,
        detail=(
            f"{len(bad)} event(s) leak placeholders: "
            + ", ".join(bad[:5])
            + ("…" if len(bad) > 5 else "")
        )
        if bad
        else "all event narratives substitute cleanly",
    )


# Sentinels that should never appear in a real narrative — they're
# either LLM prompt echoes or graceful-failure markers.
_PROMPT_LEAK_SENTINELS = (
    "Rewrite the following",
    "Output ONLY the narrative",
    "No analysis, no headers",
    # Old "[ollama-error:" sentinel was retired when LLMError became
    # typed (see llm/base.py). Kept here for legacy-snapshot detection
    # only — new failures arrive as resp.error and never reach
    # narrative text.
    "[ollama-error:",
    "JSON object",
    "Your reflection JSON",
    "Your verdict JSON",
    "RECENT MEMORIES",
    "PEOPLE CURRENTLY HERE",
    "WHAT JUST HAPPENED",
)


def no_prompt_leakage(world, engine) -> InvariantResult:
    """Found via lw smoke 2026-04-22: when Ollama is unreachable, narrator
    was writing prompt fragments as the event narrative. Detects any
    sentinel from a known LLM prompt template appearing in a final event
    narrative or chapter body."""
    bad: list[str] = []
    for e in world.events_since(1):
        text = (e.template_rendering or "") + " " + (e.spotlight_rendering or "")
        for s in _PROMPT_LEAK_SENTINELS:
            if s in text:
                bad.append(f"d{e.tick:03d}/{e.event_kind}::{s[:30]}")
                break
    for ch in world.chapters:
        body = ch.get("body", "")
        for s in _PROMPT_LEAK_SENTINELS:
            if s in body:
                bad.append(f"chapter d{ch.get('tick', '?')}::{s[:30]}")
                break
    return InvariantResult(
        name="no_prompt_leakage",
        passed=not bad,
        detail=(f"{len(bad)} prompt leaks: " + " · ".join(bad[:3]) + ("…" if len(bad) > 3 else ""))
        if bad
        else "no prompt sentinels found in any narrative or chapter",
    )


def same_kind_per_tick_capped(world, engine, *, cap: int = 1) -> InvariantResult:
    """Bug C regression: at most `cap` events of the same kind per tick."""
    counts: dict[tuple[int, str], int] = {}
    for e in world.events_since(1):
        key = (e.tick, e.event_kind)
        counts[key] = counts.get(key, 0) + 1
    over = [(k, n) for k, n in counts.items() if n > cap]
    return InvariantResult(
        name="same_kind_per_tick_capped",
        passed=not over,
        detail=(
            f"{len(over)} (tick,kind) pairs exceed cap {cap}: "
            + ", ".join(f"d{t}/{k}×{n}" for (t, k), n in over[:5])
        )
        if over
        else f"no event_kind fires more than {cap}× per tick across world",
    )


def emergent_pair_diversity(
    world,
    engine,
    *,
    min_unique_pairs: int = 3,
    window_ticks: int = 10,
) -> InvariantResult:
    """Bug B regression: emergent should not loop the same agent set.

    Over the last `window_ticks` days, count distinct sorted-tuple
    participant sets among emergent events. Require at least
    `min_unique_pairs` distinct sets if there were ≥ min_unique_pairs
    emergent events to begin with.
    """
    t = world.current_tick
    emergent = [
        tuple(sorted(e.participants))
        for e in world.events_since(max(1, t - window_ticks))
        if e.is_emergent
    ]
    if len(emergent) < min_unique_pairs:
        return InvariantResult(
            name="emergent_pair_diversity",
            passed=True,
            detail=f"only {len(emergent)} emergent events in last {window_ticks} ticks — too few to evaluate",
            severity="info",
        )
    distinct = len(set(emergent))
    return InvariantResult(
        name="emergent_pair_diversity",
        passed=distinct >= min_unique_pairs,
        detail=f"{distinct}/{len(emergent)} unique cast in last {window_ticks} ticks (need ≥ {min_unique_pairs})",
        severity="warn",
    )


def all_event_participants_real(world, engine) -> InvariantResult:
    """No event references an agent_id that doesn't exist in the world."""
    known = {a.agent_id for a in world.all_agents()}
    bad: list[str] = []
    for e in world.events_since(1):
        for pid in e.participants:
            if pid not in known:
                bad.append(f"d{e.tick:03d}/{e.event_kind}/{pid}")
                break
    return InvariantResult(
        name="all_event_participants_real",
        passed=not bad,
        detail=(f"{len(bad)} ghost participants: " + ", ".join(bad[:5]))
        if bad
        else "every event participant exists in the world",
    )


def diversity_floor(world, engine, *, max_top_kind_pct: float = 25.0) -> InvariantResult:
    """No single event_kind dominates the run."""
    evts = world.events_since(1)
    if not evts:
        return InvariantResult(
            name="diversity_floor",
            passed=True,
            detail="no events yet",
            severity="info",
        )
    kinds = Counter(e.event_kind for e in evts)
    top_kind, top_n = kinds.most_common(1)[0]
    pct = 100 * top_n / len(evts)
    return InvariantResult(
        name="diversity_floor",
        passed=pct <= max_top_kind_pct,
        detail=f"top kind '{top_kind}' = {pct:.1f}% of events (cap {max_top_kind_pct:.0f}%)",
        severity="warn",
    )


def alive_count_monotone(world, engine) -> InvariantResult:
    """No agent should resurrect — life_stage=DECEASED is terminal."""
    # Cheap proxy: every dead agent has age recorded; we don't have a
    # full audit log, so instead just verify is_alive() === (life_stage != DECEASED)
    bad: list[str] = []
    for a in world.all_agents():
        from living_world.core.agent import LifeStage

        if (a.life_stage == LifeStage.DECEASED) != (not a.is_alive()):
            bad.append(a.agent_id)
    return InvariantResult(
        name="alive_count_monotone",
        passed=not bad,
        detail=(f"{len(bad)} agents with inconsistent alive/life_stage: " + ", ".join(bad[:5]))
        if bad
        else "alive flag matches life_stage for every agent",
    )


def high_importance_events_leave_marks(
    world,
    engine,
    *,
    importance_threshold: float = 0.7,
    min_marked_pct: float = 60.0,
) -> InvariantResult:
    """A high-importance event SHOULD shift its participants' inner state
    (self_update fires + writes deltas, OR fallback emotion bumps).

    Failing this invariant means narrative ("O5-03 was dragged into a
    pocket dimension and lost his sanity") doesn't match mechanics
    (his fear/morale unchanged). Surfaced 2026-04-22 from 6-tick smoke
    where the user noticed "缺 self_update 数值反映".

    We can only check this if engine has a self_update module wired
    AND it tracks .stats — otherwise we skip with severity=info.
    """
    su = getattr(engine, "self_update", None)
    if su is None or not hasattr(su, "stats"):
        return InvariantResult(
            name="high_importance_events_leave_marks",
            passed=True,
            detail="self_update module not wired — invariant skipped",
            severity="info",
        )
    high_imp = [
        e
        for e in world.events_since(1)
        if e.importance >= importance_threshold and not e.is_emergent
    ]
    if not high_imp:
        return InvariantResult(
            name="high_importance_events_leave_marks",
            passed=True,
            detail=f"no events ≥ {importance_threshold} importance yet",
            severity="info",
        )
    # We can't trace per-event whether self_update fired (no per-event
    # log). Use aggregate proxy: the ratio of self_update calls to
    # high-importance event-participants pairs. If it's <50%, something
    # is dropping calls.
    expected_calls = sum(len(e.participants) for e in high_imp)
    actual_calls = su.stats.get("calls", 0)
    pct = 100.0 * actual_calls / max(1, expected_calls)
    return InvariantResult(
        name="high_importance_events_leave_marks",
        passed=pct >= min_marked_pct,
        detail=(
            f"{actual_calls} self_update calls / {expected_calls} expected "
            f"(high-imp participants) = {pct:.0f}% (need ≥ {min_marked_pct:.0f}%)"
        ),
        severity="warn",
    )


def no_orphan_chapters(world, engine) -> InvariantResult:
    """Every chapter's event_ids should reference real events."""
    known = {e.event_id for e in world.events_since(1)}
    bad: list[str] = []
    for ch in world.chapters:
        for eid in ch.get("event_ids", []):
            if eid not in known:
                bad.append(f"ch{ch.get('tick', '?')}/{eid}")
                break
    return InvariantResult(
        name="no_orphan_chapters",
        passed=not bad,
        detail=(f"{len(bad)} chapters reference unknown events: " + ", ".join(bad[:3]))
        if bad
        else f"all {len(world.chapters)} chapter event_ids resolve",
    )


# ── Runner ──────────────────────────────────────────────────────────────────


ALL_INVARIANTS = [
    no_unfilled_placeholders,
    no_prompt_leakage,
    same_kind_per_tick_capped,
    emergent_pair_diversity,
    all_event_participants_real,
    diversity_floor,
    alive_count_monotone,
    no_orphan_chapters,
    high_importance_events_leave_marks,
]


def check_all(world, engine) -> list[InvariantResult]:
    out: list[InvariantResult] = []
    for fn in ALL_INVARIANTS:
        try:
            out.append(fn(world, engine))
        except Exception as e:
            out.append(
                InvariantResult(
                    name=fn.__name__,
                    passed=False,
                    detail=f"invariant raised: {e!r}",
                )
            )
    return out


def summary(results: list[InvariantResult]) -> tuple[int, int, int]:
    """Return (passed, warned, failed) counts."""
    passed = warned = failed = 0
    for r in results:
        if r.passed:
            passed += 1
        elif r.severity == "warn":
            warned += 1
        else:
            failed += 1
    return passed, warned, failed
