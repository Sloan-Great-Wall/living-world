"""Structured tick logger — traces every decision in the simulation loop.

Writes a human-readable log showing each phase of every tick:
  - Movement: which agents moved, rule-based vs LLM-advised
  - Interactions: lethal encounters, companionship, flight (all rules)
  - Storyteller: proposals generated per tile (all rules)
  - Events: dice roll outcome, importance score, tier routing
  - Consciousness: LLM veto/adjust/approve (if active)
  - Consequences: stat ripples, description mutations (all rules)
  - Enhancement: Tier 1 (template) or Tier 3 (LLM dialogue rewrite)

Usage:
    from living_world.tick_logger import TickLogger
    logger = TickLogger("logs/sim.log")   # or TickLogger() for stdout
    engine.tick_logger = logger            # wire into TickEngine
    engine.run(30)
    # inspect logs/sim.log or logger.get_lines()
"""

from __future__ import annotations

import sys
from collections import deque
from datetime import datetime
from pathlib import Path


class TickLogger:
    """Append-only structured log for simulation debugging.

    Logs to file (if path given) AND keeps the last `buffer_size` lines
    in memory for the dashboard GUI to display.
    """

    def __init__(self, path: str | Path | None = None, *, buffer_size: int = 2000) -> None:
        self._path = Path(path) if path else None
        self._file = None
        if self._path:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            self._file = open(self._path, "a", encoding="utf-8")
        self._buffer: deque[str] = deque(maxlen=buffer_size)
        self._write(f"=== Living World tick log started {datetime.now().isoformat()} ===")

    def _write(self, line: str) -> None:
        self._buffer.append(line)
        if self._file:
            self._file.write(line + "\n")
            self._file.flush()

    def get_lines(self, last_n: int = 200) -> list[str]:
        """Return the last N log lines from the in-memory buffer."""
        buf = list(self._buffer)
        return buf[-last_n:]

    def close(self) -> None:
        if self._file:
            self._file.close()

    # ── Phase loggers ──

    def tick_start(self, tick: int) -> None:
        self._write(f"{'='*60}")
        self._write(f"TICK {tick:04d}")
        self._write(f"{'='*60}")

    def tick_end(self, tick: int, stats) -> None:
        self._write(
            f"  SUMMARY  proposals={stats.proposals} events={stats.events_realized} "
            f"moves={stats.movements} reactions={stats.reactions} "
            f"promotions={stats.promotions} "
            f"T1={stats.tier1} T3={stats.tier3}"
        )

    def movement(self, agent_id: str, from_tile: str, to_tile: str, method: str) -> None:
        """method: 'rule-affinity' | 'rule-relationship' | 'llm-advisor'"""
        self._write(f"  MOVE  [{method}] {agent_id}: {from_tile} -> {to_tile}")

    def interaction(self, kind: str, participants: list[str], outcome: str, tile_id: str) -> None:
        """kind: 'lethal' | 'companionship' | 'flight' | 'hazard'"""
        names = ", ".join(participants)
        self._write(f"  INTERACTION  [rule] {kind} @ {tile_id}: {names} -> {outcome}")

    def storyteller_proposal(self, tile_id: str, event_kind: str, priority: float) -> None:
        self._write(f"  PROPOSAL  [rule] {tile_id}: {event_kind} (priority={priority:.2f})")

    def event_resolved(
        self,
        event_id: str,
        event_kind: str,
        tile_id: str,
        participants: list[str],
        outcome: str,
        roll: int | None,
        dc: int | None,
        importance: float,
        conscious_verdict: str | None,
    ) -> None:
        roll_str = f"d20={roll} vs DC {dc}" if roll is not None else "no-roll"
        conscious_str = f" conscious={conscious_verdict}" if conscious_verdict else ""
        names = ", ".join(participants)
        self._write(
            f"  EVENT  [{roll_str}] {event_kind} @ {tile_id}: "
            f"{names} -> {outcome} (imp={importance:.2f}{conscious_str})"
        )

    def tier_routing(self, event_id: str, tier: int, method: str) -> None:
        """method: 'template' | 'llm-dialogue'"""
        tag = "rule" if tier == 1 else "LLM"
        self._write(f"  TIER   [{tag}] tier={tier} method={method} event={event_id[:8]}")

    def consequence(self, event_kind: str, target_id: str, changes: str) -> None:
        self._write(f"  CONSEQUENCE  [rule] {event_kind} -> {target_id}: {changes}")

    def promotion(self, agent_id: str, reason: str) -> None:
        self._write(f"  PROMOTE  [rule] {agent_id}: {reason}")

    def consciousness_call(
        self, event_kind: str, verdict: str, reason: str | None
    ) -> None:
        self._write(
            f"  CONSCIOUS  [LLM] {event_kind}: verdict={verdict}"
            + (f" reason={reason}" if reason else "")
        )

    def memory_store(self, agent_id: str, kind: str, importance: float) -> None:
        self._write(f"  MEMORY  [rule] {agent_id}: {kind} (imp={importance:.2f})")

    def plan_generated(self, agent_id: str, plan: dict) -> None:
        goals = plan.get("goals_this_week") or []
        seek = plan.get("seek") or []
        avoid = plan.get("avoid") or []
        self._write(
            f"  PLAN  [LLM] {agent_id}: "
            f"goals={goals[:3]} seek={seek[:3]} avoid={avoid[:3]}"
        )

    def belief_updated(self, agent_id: str, topic: str, belief: str) -> None:
        self._write(f"  BELIEF  [LLM] {agent_id}: {topic} -> {belief[:120]}")

    def reflection(self, agent_id: str, tick: int, new_beliefs: int) -> None:
        """Park-style reflection fired for an agent on this tick."""
        self._write(
            f"  REFLECT  [LLM] {agent_id} @ d{tick:03d}: "
            f"{new_beliefs} new belief(s)"
        )

    def dialogue_reaction(
        self, listener_id: str, speaker_id: str,
        affinity_delta: int, reply: str, belief_update: str | None,
    ) -> None:
        self._write(
            f"  DIALOGUE_REACT  [LLM] {listener_id} <- {speaker_id}: "
            f"affinity{affinity_delta:+d} reply={reply[:60]!r}"
            + (f" belief={belief_update[:80]!r}" if belief_update else "")
        )

    def chapter_written(self, tick: int, title: str) -> None:
        self._write(f"  CHAPTER  [LLM] day {tick:03d}: {title}")

    def emergent_event(self, event_kind: str, tile_id: str, participants: list[str]) -> None:
        self._write(
            f"  EMERGENT  [LLM] {event_kind} @ {tile_id}: "
            f"{', '.join(participants)}"
        )

    def template_promoted(self, event_kind: str, pack_id: str, importance: float) -> None:
        self._write(
            f"  TEMPLATE_PROMOTED  [rule] {pack_id}/{event_kind} "
            f"(imp={importance:.2f}) joined the storyteller pool"
        )

    def template_pruned(self, event_kind: str, pack_id: str) -> None:
        self._write(f"  TEMPLATE_PRUNED  [rule] {pack_id}/{event_kind} dropped from pool")

    def self_update(self, agent_id: str, applied: dict) -> None:
        bits = []
        if "attribute_deltas" in applied:
            bits.append("attrs=" + ",".join(f"{k}{v:+d}" for k, v in applied["attribute_deltas"].items()))
        if "emotions_deltas" in applied:
            bits.append("emo=" + ",".join(f"{k}{v:+.0f}" for k, v in applied["emotions_deltas"].items()))
        if "needs_deltas" in applied:
            bits.append("needs=" + ",".join(f"{k}{v:+.0f}" for k, v in applied["needs_deltas"].items()))
        if "tags_added" in applied:
            bits.append(f"+tag={applied['tags_added']}")
        if "tags_removed" in applied:
            bits.append(f"-tag={applied['tags_removed']}")
        if "new_goal" in applied:
            bits.append(f"goal={applied['new_goal'][:40]!r}")
        if "belief_update" in applied:
            bu = applied["belief_update"]
            bits.append(f"belief={bu['topic']}:{bu['belief'][:40]!r}")
        self._write(f"  SELF_UPDATE  [LLM] {agent_id}: {' '.join(bits) or '(empty)'}")

    def debug(self, msg: str) -> None:
        self._write(f"  DEBUG  {msg}")
