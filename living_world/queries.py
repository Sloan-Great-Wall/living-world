"""Read-only world queries — used by dashboard, CLI, future API.

Foundation step of the dashboard 3-layer split (KNOWN_ISSUES #3).

Today the dashboard inlines a lot of "filter events / count things /
group by pack" code. By moving those helpers here, ANY consumer (the
current Streamlit dashboard, a future Svelte one, a Jupyter notebook,
a CLI report) reuses the same logic with the same field names.

Discipline: this module never mutates state. Pure functions over
World / TickEngine snapshots. Anything that *changes* the world
belongs in `living_world/phases.py` or `rules/*.py` instead.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

from living_world.core.event import LegendEvent
from living_world.core.world import World


# ── Event queries ──────────────────────────────────────────────────────────

def recent_events(world: World, n: int = 50) -> list[LegendEvent]:
    """Last N events across all packs, oldest-first."""
    all_evts = world.events_since(1)
    return all_evts[-n:]


def events_by_pack(world: World, since_tick: int = 1) -> dict[str, list[LegendEvent]]:
    """Group events by pack_id — useful for per-pack chronicle panels."""
    out: dict[str, list[LegendEvent]] = {}
    for e in world.events_since(since_tick):
        out.setdefault(e.pack_id, []).append(e)
    return out


def events_by_day(world: World, since_tick: int = 1) -> dict[int, list[LegendEvent]]:
    """Group events by tick — used by the digest CLI."""
    out: dict[int, list[LegendEvent]] = {}
    for e in world.events_since(since_tick):
        out.setdefault(e.tick, []).append(e)
    return out


def event_kind_distribution(
    world: World, since_tick: int = 1, *, top_k: int = 10,
) -> list[tuple[str, int]]:
    """Top-K most frequent event kinds since `since_tick`."""
    c: Counter = Counter(e.event_kind for e in world.events_since(since_tick))
    return c.most_common(top_k)


def diversity_summary(world: World, since_tick: int = 1) -> dict:
    """Headline diversity stats: total / unique / top-kind percent."""
    evts = world.events_since(since_tick)
    if not evts:
        return {"total": 0, "unique": 0, "top_kind": None, "top_pct": 0.0}
    kinds = Counter(e.event_kind for e in evts)
    top = kinds.most_common(1)[0]
    return {
        "total": len(evts),
        "unique": len(kinds),
        "top_kind": top[0],
        "top_pct": 100 * top[1] / len(evts),
    }


# ── Agent queries ──────────────────────────────────────────────────────────

def living_agents(world: World, pack_id: str | None = None) -> list:
    return [
        a for a in world.living_agents()
        if pack_id is None or a.pack_id == pack_id
    ]


def death_count(world: World, pack_id: str | None = None) -> int:
    return sum(
        1 for a in world.all_agents()
        if not a.is_alive() and (pack_id is None or a.pack_id == pack_id)
    )


# ── Engine status (for dashboard "what's wired" panel) ─────────────────────

@dataclass
class FeatureStatus:
    name: str
    on: bool
    detail: str = ""


def feature_status(engine) -> list[FeatureStatus]:
    """Compact list of LLM features that are wired and their settings.

    Powers the dashboard's "what's actually live this run" sidebar.
    """
    out = [
        FeatureStatus("memory",
                       engine.memory is not None,
                       f"reflect_every={engine.reflect_every_ticks}"),
        FeatureStatus("planner",
                       engine.agent_planner is not None,
                       f"hf_only={engine.plan_hf_only}"),
        FeatureStatus("chronicler",
                       engine.chronicler is not None,
                       f"every={engine.chronicle_every_ticks}t"),
        FeatureStatus("emergent",
                       engine.emergent_proposer is not None,
                       f"max_per_tick={engine.emergent_max_per_tick}"),
        FeatureStatus("conscience", engine.consciousness is not None),
        FeatureStatus("dialogue_loop", engine.conversation_loop_enabled),
        FeatureStatus("perception",
                       engine.perception is not None,
                       f"≥{engine.perception_threshold:.2f}"
                       if engine.perception is not None else ""),
        FeatureStatus("self_update",
                       engine.self_update is not None,
                       f"≥{engine.self_update_threshold:.2f}"
                       if engine.self_update is not None else ""),
        FeatureStatus("llm_movement",
                       engine.movement.llm_advisor is not None,
                       f"chance={engine.movement.llm_chance:.2f}"
                       if engine.movement.llm_advisor is not None else ""),
        FeatureStatus("memory_reflector",
                       engine.memory is not None
                       and engine.memory.reflector is not None),
    ]
    return out


def narrator_stats(engine) -> dict:
    s = engine.narrator.stats
    return {"tier1": s.tier1, "tier3": s.tier3, "total": s.tier1 + s.tier3}


# ── Chronicle export ──────────────────────────────────────────────────────

def export_chronicle_markdown(world: World) -> str:
    """Render world.chapters as a Markdown chronicle.

    Used by `lw export-chronicle` and any future "share my run" feature.
    Pure function — no I/O, no side effects.
    """
    if not world.chapters:
        return "# (no chapters yet)\n\nThe chronicler hasn't fired in this run.\n"

    by_pack: dict[str, list[dict]] = {}
    for ch in world.chapters:
        by_pack.setdefault(ch.get("pack_id", "?"), []).append(ch)

    lines: list[str] = ["# Chronicle", ""]
    lines.append(f"_World ran {world.current_tick} tick(s). "
                 f"{len(world.chapters)} chapters across "
                 f"{len(by_pack)} pack(s)._\n")

    for pack_id in sorted(by_pack.keys()):
        lines.append(f"## {pack_id}\n")
        for ch in sorted(by_pack[pack_id], key=lambda c: c.get("tick", 0)):
            title = ch.get("title", "(untitled)")
            tick = ch.get("tick", "?")
            body = ch.get("body", "").strip()
            lines.append(f"### Day {tick} — {title}\n")
            lines.append(body)
            lines.append("")  # blank between chapters
    return "\n".join(lines)
