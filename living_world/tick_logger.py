"""Structured tick logger — traces every decision in the simulation loop.

Two output formats, picked at construction time (or via `LW_LOG_JSON=1`):

  - **text** (default): human-readable indented lines, what we've always had
  - **json**:  one JSON object per line, machine-parseable

Why JSON (AI-Native criterion B — errors must be type-dispatchable):
  An AI agent debugging a failed run needs to filter / aggregate events
  by kind, agent, tile, tier, error_kind. Greppable text lines force
  brittle regex; JSON-line lets the AI run e.g.

      jq -c 'select(.event=="EVENT" and .outcome=="failure")' sim.log
      jq -c 'select(.event=="ERROR" and .kind=="llm_timeout") | .agent' sim.log

  …or load into a DataFrame in 3 lines. The text path is preserved for
  human eyeball debugging.

Phase coverage:
  - Movement, Interactions, Proposals, Events, Tier routing,
    Consequences, Memory, Plans, Beliefs, Dialogue, Chapters,
    Emergent events, Template promote/prune, Self-update, LLM errors

Usage:
    from living_world.tick_logger import TickLogger
    logger = TickLogger("logs/sim.log")               # text
    logger = TickLogger("logs/sim.json", json=True)   # JSON lines
    # Or pick via env:
    logger = TickLogger("logs/sim.log", json=None)    # honours LW_LOG_JSON
    engine.tick_logger = logger
    engine.run(30)
"""

from __future__ import annotations

import json as _json
import os
from collections import deque
from datetime import datetime
from pathlib import Path
from typing import Any


class TickLogger:
    """Append-only structured log for simulation debugging.

    Logs to file (if path given) AND keeps the last `buffer_size` lines
    in memory for the dashboard GUI to display.

    Parameters
    ----------
    path
        Output file; None = no file (buffer + stdout only).
    buffer_size
        How many recent lines to retain for dashboard GUI pull.
    json
        `True` = JSON-lines output. `False` = human text. `None` =
        honour the `LW_LOG_JSON` environment variable (any truthy value
        turns JSON on). Default None so AI-driven batch runs can flip
        the format without code edits.
    """

    def __init__(
        self,
        path: str | Path | None = None,
        *,
        buffer_size: int = 2000,
        json: bool | None = None,
    ) -> None:
        self._path = Path(path) if path else None
        self._file = None
        if self._path:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            self._file = open(self._path, "a", encoding="utf-8")
        self._buffer: deque[str] = deque(maxlen=buffer_size)
        if json is None:
            json = os.environ.get("LW_LOG_JSON", "").lower() in ("1", "true", "yes")
        self._json_mode = bool(json)
        self._current_tick: int = 0
        self._emit(
            "session_start",
            {"ts": datetime.now().isoformat(), "mode": "json" if self._json_mode else "text"},
            text=f"=== Living World tick log started {datetime.now().isoformat()} ===",
        )

    # ── Core emitter ──

    def _emit(self, event: str, payload: dict[str, Any], *, text: str) -> None:
        """Write one line in the active format.

        `event` is the machine-readable tag (MOVE / EVENT / ERROR / ...);
        `payload` is the structured body; `text` is the human form.
        In JSON mode we serialise {tick, event, ...payload}; in text
        mode we emit the `text` argument verbatim.
        """
        if self._json_mode:
            line = _json.dumps(
                {"tick": self._current_tick, "event": event, **payload},
                ensure_ascii=False,
                default=str,
            )
        else:
            line = text
        self._buffer.append(line)
        if self._file:
            self._file.write(line + "\n")
            self._file.flush()

    def _write(self, line: str) -> None:
        """Backwards-compat raw emission (text only). Used by legacy
        callers that haven't been ported to `_emit` yet. In JSON mode
        the line is wrapped as {event: 'raw', text: ...}."""
        if self._json_mode:
            self._emit("raw", {"text": line}, text=line)
        else:
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
        self._current_tick = tick
        if self._json_mode:
            self._emit("tick_start", {}, text="")
        else:
            self._write(f"{'=' * 60}")
            self._write(f"TICK {tick:04d}")
            self._write(f"{'=' * 60}")

    def tick_end(self, tick: int, stats) -> None:
        self._emit(
            "tick_end",
            {
                "proposals": stats.proposals,
                "events": stats.events_realized,
                "moves": stats.movements,
                "reactions": stats.reactions,
                "promotions": stats.promotions,
                "tier1": stats.tier1,
                "tier3": stats.tier3,
            },
            text=(
                f"  SUMMARY  proposals={stats.proposals} events={stats.events_realized} "
                f"moves={stats.movements} reactions={stats.reactions} "
                f"promotions={stats.promotions} "
                f"T1={stats.tier1} T3={stats.tier3}"
            ),
        )

    def movement(self, agent_id: str, from_tile: str, to_tile: str, method: str) -> None:
        """method: 'rule-affinity' | 'rule-relationship' | 'llm-advisor'"""
        self._emit(
            "movement",
            {"agent": agent_id, "from": from_tile, "to": to_tile, "method": method},
            text=f"  MOVE  [{method}] {agent_id}: {from_tile} -> {to_tile}",
        )

    def interaction(self, kind: str, participants: list[str], outcome: str, tile_id: str) -> None:
        """kind: 'lethal' | 'companionship' | 'flight' | 'hazard'"""
        self._emit(
            "interaction",
            {"kind": kind, "participants": list(participants), "outcome": outcome, "tile": tile_id},
            text=f"  INTERACTION  [rule] {kind} @ {tile_id}: "
            f"{', '.join(participants)} -> {outcome}",
        )

    def storyteller_proposal(self, tile_id: str, event_kind: str, priority: float) -> None:
        self._emit(
            "proposal",
            {"tile": tile_id, "kind": event_kind, "priority": round(priority, 4)},
            text=f"  PROPOSAL  [rule] {tile_id}: {event_kind} (priority={priority:.2f})",
        )

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
        self._emit(
            "event",
            {
                "event_id": event_id,
                "kind": event_kind,
                "tile": tile_id,
                "participants": list(participants),
                "outcome": outcome,
                "roll": roll,
                "dc": dc,
                "importance": round(importance, 4),
                "conscious_verdict": conscious_verdict,
            },
            text=(
                f"  EVENT  [{'d20=' + str(roll) + ' vs DC ' + str(dc) if roll is not None else 'no-roll'}] "
                f"{event_kind} @ {tile_id}: {', '.join(participants)} -> {outcome} "
                f"(imp={importance:.2f}"
                + (f" conscious={conscious_verdict}" if conscious_verdict else "")
                + ")"
            ),
        )

    def tier_routing(self, event_id: str, tier: int, method: str) -> None:
        """method: 'template' | 'llm-dialogue'"""
        tag = "rule" if tier == 1 else "LLM"
        self._emit(
            "tier",
            {"event_id": event_id, "tier": tier, "method": method},
            text=f"  TIER   [{tag}] tier={tier} method={method} event={event_id[:8]}",
        )

    def consequence(self, event_kind: str, target_id: str, changes: str) -> None:
        self._emit(
            "consequence",
            {"event_kind": event_kind, "target": target_id, "changes": changes},
            text=f"  CONSEQUENCE  [rule] {event_kind} -> {target_id}: {changes}",
        )

    def promotion(self, agent_id: str, reason: str) -> None:
        self._emit(
            "promotion",
            {"agent": agent_id, "reason": reason},
            text=f"  PROMOTE  [rule] {agent_id}: {reason}",
        )

    def consciousness_call(
        self,
        event_kind: str,
        verdict: str,
        reason: str | None,
    ) -> None:
        self._emit(
            "conscious",
            {"event_kind": event_kind, "verdict": verdict, "reason": reason or ""},
            text=(
                f"  CONSCIOUS  [LLM] {event_kind}: verdict={verdict}"
                + (f" reason={reason}" if reason else "")
            ),
        )

    def memory_store(self, agent_id: str, kind: str, importance: float) -> None:
        self._emit(
            "memory",
            {"agent": agent_id, "kind": kind, "importance": round(importance, 4)},
            text=f"  MEMORY  [rule] {agent_id}: {kind} (imp={importance:.2f})",
        )

    def plan_generated(self, agent_id: str, plan: dict) -> None:
        goals = plan.get("goals_this_week") or []
        seek = plan.get("seek") or []
        avoid = plan.get("avoid") or []
        self._emit(
            "plan",
            {"agent": agent_id, "goals": goals[:3], "seek": seek[:3], "avoid": avoid[:3]},
            text=(f"  PLAN  [LLM] {agent_id}: goals={goals[:3]} seek={seek[:3]} avoid={avoid[:3]}"),
        )

    def belief_updated(self, agent_id: str, topic: str, belief: str) -> None:
        self._emit(
            "belief",
            {"agent": agent_id, "topic": topic, "belief": belief[:400]},
            text=f"  BELIEF  [LLM] {agent_id}: {topic} -> {belief[:120]}",
        )

    def dialogue_reaction(
        self,
        listener_id: str,
        speaker_id: str,
        affinity_delta: int,
        reply: str,
        belief_update: str | None,
    ) -> None:
        self._emit(
            "dialogue",
            {
                "listener": listener_id,
                "speaker": speaker_id,
                "affinity_delta": affinity_delta,
                "reply": reply[:300],
                "belief_update": belief_update[:300] if belief_update else None,
            },
            text=(
                f"  DIALOGUE_REACT  [LLM] {listener_id} <- {speaker_id}: "
                f"affinity{affinity_delta:+d} reply={reply[:60]!r}"
                + (f" belief={belief_update[:80]!r}" if belief_update else "")
            ),
        )

    def chapter_written(self, tick: int, title: str) -> None:
        self._emit(
            "chapter",
            {"day": tick, "title": title},
            text=f"  CHAPTER  [LLM] day {tick:03d}: {title}",
        )

    def emergent_event(self, event_kind: str, tile_id: str, participants: list[str]) -> None:
        self._emit(
            "emergent",
            {"kind": event_kind, "tile": tile_id, "participants": list(participants)},
            text=(f"  EMERGENT  [LLM] {event_kind} @ {tile_id}: {', '.join(participants)}"),
        )

    def template_promoted(self, event_kind: str, pack_id: str, importance: float) -> None:
        self._emit(
            "template_promoted",
            {"pack": pack_id, "kind": event_kind, "importance": round(importance, 4)},
            text=(
                f"  TEMPLATE_PROMOTED  [rule] {pack_id}/{event_kind} "
                f"(imp={importance:.2f}) joined the storyteller pool"
            ),
        )

    def template_pruned(self, event_kind: str, pack_id: str) -> None:
        self._emit(
            "template_pruned",
            {"pack": pack_id, "kind": event_kind},
            text=f"  TEMPLATE_PRUNED  [rule] {pack_id}/{event_kind} dropped from pool",
        )

    def self_update(self, agent_id: str, applied: dict) -> None:
        bits = []
        if "attribute_deltas" in applied:
            bits.append(
                "attrs=" + ",".join(f"{k}{v:+d}" for k, v in applied["attribute_deltas"].items())
            )
        if "emotions_deltas" in applied:
            bits.append(
                "emo=" + ",".join(f"{k}{v:+.0f}" for k, v in applied["emotions_deltas"].items())
            )
        if "needs_deltas" in applied:
            bits.append(
                "needs=" + ",".join(f"{k}{v:+.0f}" for k, v in applied["needs_deltas"].items())
            )
        if "tags_added" in applied:
            bits.append(f"+tag={applied['tags_added']}")
        if "tags_removed" in applied:
            bits.append(f"-tag={applied['tags_removed']}")
        if "new_goal" in applied:
            bits.append(f"goal={applied['new_goal'][:40]!r}")
        if "belief_update" in applied:
            bu = applied["belief_update"]
            bits.append(f"belief={bu['topic']}:{bu['belief'][:40]!r}")
        self._emit(
            "self_update",
            {"agent": agent_id, "applied": applied},
            text=f"  SELF_UPDATE  [LLM] {agent_id}: {' '.join(bits) or '(empty)'}",
        )

    # ── NEW: typed LLM error logging (AI-Native criterion B) ──

    def llm_error(
        self,
        module: str,
        kind: str,
        message: str,
        *,
        agent_id: str | None = None,
    ) -> None:
        """Emit a structured record for an LLM-backend failure.

        `kind` comes from LLMError.kind (llm_timeout / llm_unreachable /
        llm_bad_response / llm_unknown). AI debuggers can filter with
        `jq 'select(.event=="llm_error" and .kind=="llm_timeout")'`
        and instantly see which module + agent flaked.
        """
        self._emit(
            "llm_error",
            {"module": module, "kind": kind, "message": message[:400], "agent": agent_id or ""},
            text=f"  LLM_ERROR  [{module}] kind={kind} agent={agent_id or '-'} msg={message[:120]}",
        )

    def phase_error(self, name: str, exc: Exception) -> None:
        """A phase raised instead of returning. Caught by step() so the
        tick keeps moving; we record kind + message for AI diagnosis."""
        self._emit(
            "phase_error",
            {"phase": name, "exc_type": exc.__class__.__name__, "message": str(exc)[:400]},
            text=f"  PHASE_ERROR  [{name}] {exc.__class__.__name__}: {exc}",
        )

    def debug(self, msg: str) -> None:
        self._emit("debug", {"message": msg}, text=f"  DEBUG  {msg}")
