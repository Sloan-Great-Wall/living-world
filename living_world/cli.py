"""CLI: `lw run|digest|list-packs|smoke|test|serve|export-chronicle|social`.

Thin wrapper around `factory.py` — same engine construction the FastAPI
server uses, so advanced features (dialogue, conscience, planner, etc.)
light up automatically when settings.yaml has them enabled.
"""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from living_world import PACKS_DIR
from living_world.config import load_settings
from living_world.factory import bootstrap_world, build_repository, make_engine
from living_world.llm.ollama import OllamaClient

app = typer.Typer(no_args_is_help=True)
console = Console()


def _build_and_run(
    pack_ids: list[str],
    days: int,
    seed: int,
    *,
    persist: bool = False,
) -> tuple:
    """Shared engine construction + N-day run. Returns (world, engine)."""
    settings = load_settings()
    world, loaded = bootstrap_world(PACKS_DIR, pack_ids)
    repo = build_repository(settings) if persist else None
    if repo is not None:
        repo.save_world(world)
    engine = make_engine(world, loaded, settings, seed, repository=repo)

    # Probe Ollama once if it's used
    if settings.llm.tier2_provider == "ollama" or settings.llm.tier3_provider == "ollama":
        probe = OllamaClient(
            model=settings.llm.ollama_tier2_model,
            base_url=settings.llm.ollama_base_url,
        )
        if not probe.available():
            console.log(
                f"[yellow]Warning: Ollama at {probe.base_url} unreachable. "
                f"Tier 2/3 calls will fail individually; world still runs on rules.[/]"
            )
    engine.run(days)
    return world, engine


@app.command()
def run(
    packs: str = typer.Option("scp", help="Comma-separated pack ids."),
    days: int = typer.Option(10, help="How many virtual days to simulate."),
    seed: int = typer.Option(42, help="Random seed."),
    persist: bool = typer.Option(False, help="Enable persistence (uses settings.yaml backend)"),
) -> None:
    """Run the simulation using settings.yaml."""
    pack_ids = [p.strip() for p in packs.split(",") if p.strip()]
    console.log(f"Loading packs: {pack_ids}")
    world, engine = _build_and_run(pack_ids, days, seed, persist=persist)

    total_events = world.event_count()
    n = engine.narrator.stats
    console.log(f"Done. {total_events} events | T1={n.tier1} T3={n.tier3}")
    console.log(f"Historical figures: {engine.hf_registry.summary()}")

    recent = world.events_since(max(1, world.current_tick - days + 1))
    table = Table(title=f"Last {min(20, len(recent))} events")
    for col, style in [
        ("tick", "cyan"),
        ("pack", "magenta"),
        ("kind", "yellow"),
        ("tier", "red"),
        ("imp", None),
        ("narrative", None),
    ]:
        table.add_column(
            col,
            style=style or "",
            no_wrap=(col == "tick"),
            justify="right" if col == "imp" else "left",
            overflow="fold" if col == "narrative" else "ellipsis",
        )
    for e in recent[-20:]:
        table.add_row(
            str(e.tick),
            e.pack_id,
            e.event_kind,
            str(e.tier_used),
            f"{e.importance:.2f}",
            e.best_rendering(),
        )
    console.print(table)


@app.command()
def digest(
    packs: str = typer.Option("scp,liaozhai,cthulhu"),
    days: int = typer.Option(7, help="Days to simulate before digest."),
    seed: int = typer.Option(42),
) -> None:
    """Run N days then print a per-day '章回体 digest' grouped by pack."""
    pack_ids = [p.strip() for p in packs.split(",") if p.strip()]
    world, engine = _build_and_run(pack_ids, days, seed)

    by_day: dict[int, dict[str, list]] = defaultdict(lambda: defaultdict(list))
    for e in world.events_since(1):
        by_day[e.tick][e.pack_id].append(e)

    for day in sorted(by_day.keys()):
        console.rule(f"第 {day} 日")
        for pack_id, day_events in sorted(by_day[day].items()):
            console.print(f"[bold magenta]\n【{pack_id}】[/]")
            for e in day_events:
                marker = "★" if e.tier_used >= 2 else "·"
                console.print(f"  {marker} {e.best_rendering()}")

    console.rule("Summary")
    console.print(world.summary())
    s = engine.narrator.stats
    console.print(f"narrator: T1={s.tier1} T3={s.tier3}")


@app.command("export-chronicle")
def export_chronicle(
    packs: str = typer.Option("scp,liaozhai,cthulhu", help="Packs to load."),
    days: int = typer.Option(15, help="Days to simulate before exporting."),
    seed: int = typer.Option(42),
    out: Path = typer.Option(Path("chronicle.md"), help="Output Markdown file path."),
) -> None:
    """Run N days, then write the chronicle as Markdown to `out`.

    Implements the chronicle-export feature requested 2026-04-22 — see
    KNOWN_ISSUES.md "Chronicle export" section. Pure function lives in
    `living_world.queries.export_chronicle_markdown`, so any other
    consumer (web dashboard, Marimo notebook) can reuse it.
    """
    from living_world.queries import export_chronicle_markdown

    pack_ids = [p.strip() for p in packs.split(",") if p.strip()]
    world, _engine = _build_and_run(pack_ids, days, seed)
    text = export_chronicle_markdown(world)
    out.write_text(text, encoding="utf-8")
    console.log(f"Wrote {len(world.chapters)} chapters → [bold]{out}[/] ({len(text):,} chars)")


@app.command()
def test(
    ticks: int = typer.Option(8, help="Smoke test sim length."),
    skip_unit: bool = typer.Option(False, help="Skip pytest unit/invariant phase."),
    skip_smoke: bool = typer.Option(False, help="Skip the live smoke sim."),
) -> None:
    """Default test command — runs pytest THEN a real smoke simulation.

    The smoke phase is the canonical "is the simulator healthy?" check:
    bootstraps 3 packs, runs `ticks` days with whatever LLM stack is
    configured (real Ollama if up, rules-only otherwise), streams
    events to terminal, asserts all 8 invariants. Exit code is the
    OR of pytest and smoke results.

    For pure unit/invariant testing without the live sim:
        lw test --skip-smoke
    For the smoke sim only:
        lw test --skip-unit
    """
    import subprocess
    import sys

    overall_failed = 0

    if not skip_unit:
        console.rule("Phase 1 · pytest (unit + property + invariant)")
        proc = subprocess.run(
            [sys.executable, "-m", "pytest", "tests/", "-q", "--ignore=tests/test_live_ollama.py"],
            cwd=Path(__file__).resolve().parent.parent,
        )
        if proc.returncode != 0:
            overall_failed += 1
            console.print("[red]Phase 1 FAILED[/]")
        else:
            console.print("[green]Phase 1 passed[/]")

    if not skip_smoke:
        console.rule(f"Phase 2 · live smoke ({ticks} ticks)")
        # Run as subprocess so typer Option defaults resolve normally and
        # rich live output streams cleanly to the inherited stdout.
        proc = subprocess.run(
            [sys.executable, "-m", "living_world.cli", "smoke", "--ticks", str(ticks)],
            cwd=Path(__file__).resolve().parent.parent,
        )
        if proc.returncode != 0:
            overall_failed += 1

    if overall_failed:
        raise typer.Exit(code=1)
    console.rule("[green]All test phases passed[/]")


@app.command()
def smoke(
    packs: str = typer.Option("scp,liaozhai,cthulhu", help="Comma-separated pack ids."),
    ticks: int = typer.Option(8, help="Days to simulate."),
    seed: int = typer.Option(42),
    show_events: bool = typer.Option(True, help="Stream events to terminal as they happen."),
    fail_on_warn: bool = typer.Option(False, help="Treat warning-severity invariants as failure."),
) -> None:
    """End-to-end smoke test: bootstrap, run N ticks, check invariants.

    This is the primary "did the simulator regress?" command. Pair it
    with `lw test` (unit tests) for full coverage:
      - `lw test`  → ~74 unit + property tests, fast (<2s)
      - `lw smoke` → real engine run, streams story to terminal,
                     asserts invariants on the resulting world

    Exit code 0 = all invariants passed; non-zero = at least one
    failed (or warned, with --fail-on-warn). Suitable for CI.
    """
    from living_world.invariants import check_all, summary

    pack_ids = [p.strip() for p in packs.split(",") if p.strip()]
    console.rule(f"Smoke test · {ticks} ticks · {pack_ids}")

    settings = load_settings()
    world, loaded = bootstrap_world(PACKS_DIR, pack_ids)
    engine = make_engine(world, loaded, settings, seed)

    # Snapshot HF inner state at t=0 so we can show drift after the run.
    initial_hf_state = {
        a.agent_id: {
            "name": a.display_name,
            "needs": dict(a.get_needs()),
            "emotions": dict(a.get_emotions()),
            "beliefs_count": len(a.get_beliefs()),
            "goal": a.current_goal,
        }
        for a in world.historical_figures()
    }

    # Probe Ollama; warn if down (sim still runs on rules)
    if settings.llm.tier2_provider == "ollama":
        probe = OllamaClient(
            model=settings.llm.ollama_tier2_model, base_url=settings.llm.ollama_base_url
        )
        if not probe.available():
            console.log("[yellow]Ollama unreachable — running rules-only.[/]")

    # Stream events as they appear
    for _ in range(ticks):
        engine.run(1)
        if show_events:
            new_events = world.events_since(world.current_tick)
            for e in new_events:
                tier_glyph = "●●●" if e.tier_used >= 3 else ("●●" if e.tier_used == 2 else "●")
                tier_color = (
                    "magenta" if e.tier_used >= 3 else ("yellow" if e.tier_used == 2 else "dim")
                )
                em = " emergent" if e.is_emergent else ""
                console.print(
                    f"  [{tier_color}]{tier_glyph}[/] [dim]d{e.tick:03d}[/] "
                    f"[cyan]{e.pack_id}[/] [bold]{e.event_kind}[/]"
                    f"[dim]{em}[/] [{e.outcome}]"
                )
                console.print(f"      [dim]{e.best_rendering()[:200]}[/]")

    # ── Invariants ──
    console.rule("Invariants")
    results = check_all(world, engine)
    table = Table(show_header=True, header_style="bold")
    table.add_column("", width=3)
    table.add_column("invariant", style="cyan")
    table.add_column("detail", style="white")
    for r in results:
        table.add_row(r.emoji, r.name, r.detail)
    console.print(table)

    passed, warned, failed = summary(results)
    color = "green" if failed == 0 else "red"
    console.print(f"\n[{color}]{passed} passed · {warned} warned · {failed} failed[/]")

    # ── Run summary ──
    from living_world.queries import diversity_summary, event_kind_distribution

    ds = diversity_summary(world)
    deaths = sum(1 for a in world.all_agents() if not a.is_alive())
    console.rule("Run summary")
    console.print(
        f"  events       [bold]{ds['total']}[/]   "
        f"unique kinds [bold]{ds['unique']}[/]   "
        f"top {ds['top_kind']} ({ds['top_pct']:.1f}%)"
    )
    console.print(
        f"  chapters     [bold]{len(world.chapters)}[/]   "
        f"deaths       [bold]{deaths}[/]   "
        f"alive [bold]{ds['total'] and sum(1 for _ in world.living_agents())}[/]"
    )
    top = event_kind_distribution(world, top_k=5)
    console.print("  top kinds:   " + ", ".join(f"{k}×{n}" for k, n in top))

    # ── Per-phase latency table (P3 telemetry) ──
    console.rule("Phase latency · mean s/tick (top 8)")
    rows: list[tuple[float, float, str, int]] = []
    for name, samples in engine.phase_latency.items():
        if not samples:
            continue
        mean = sum(samples) / len(samples)
        rows.append((mean, max(samples), name, len(samples)))
    rows.sort(key=lambda r: -r[0])
    for mean, peak, name, n in rows[:8]:
        bar = "█" * min(40, int(mean * 4))
        console.print(
            f"  [bold]{name:22s}[/]  [gold1]{mean:5.2f}s[/]  "
            f"[dim]peak {peak:5.2f}s · n={n}[/]  {bar}"
        )

    # ── HF inner-state drift (the proof self_update + reflector worked) ──
    console.rule("HF inner-state drift (top 8 by absolute change)")
    drifts: list[tuple[str, str, str]] = []
    for a in world.historical_figures():
        before = initial_hf_state.get(a.agent_id)
        if not before:
            continue
        n_now = a.get_needs()
        e_now = a.get_emotions()
        n_b = before["needs"]
        e_b = before["emotions"]
        deltas: list[str] = []
        total_abs = 0.0
        for k in ("hunger", "safety"):
            d = n_now.get(k, 0) - n_b.get(k, 0)
            if abs(d) >= 1:
                deltas.append(f"{k}{d:+.0f}")
                total_abs += abs(d)
        for k in ("fear", "joy", "anger"):
            d = e_now.get(k, 0) - e_b.get(k, 0)
            if abs(d) >= 1:
                deltas.append(f"{k}{d:+.0f}")
                total_abs += abs(d)
        belief_delta = len(a.get_beliefs()) - before["beliefs_count"]
        if belief_delta:
            deltas.append(f"beliefs+{belief_delta}")
            total_abs += belief_delta * 5  # weight beliefs heavily
        goal_changed = a.current_goal != before["goal"]
        if goal_changed:
            deltas.append("goal↻")
            total_abs += 10
        if deltas:
            drifts.append((f"{total_abs:6.1f}", a.display_name, " · ".join(deltas)))
    drifts.sort(key=lambda x: -float(x[0]))
    if drifts:
        for score, name, delta in drifts[:8]:
            console.print(f"  [dim]{score}[/]  [bold]{name:35s}[/]  {delta}")
    else:
        console.print(
            "  [yellow]⚠ no HF inner-state drift detected — "
            "self_update / reflector may not be firing[/]"
        )

    # Exit code for CI
    if failed > 0 or (fail_on_warn and warned > 0):
        raise typer.Exit(code=1)


@app.command()
def serve(
    port: int = typer.Option(8000, help="REST API port."),
    host: str = typer.Option("127.0.0.1"),
    reload: bool = typer.Option(False, help="Auto-reload on code changes."),
) -> None:
    """Run the FastAPI sim API for the Tauri dashboard.

    Pair with `cd dashboard-tauri && bun run dev` (or `bun run tauri dev`)
    for the full game-aesthetic UI. Requires the `serve` extra:
        pip install -e '.[serve]'
    """
    import uvicorn

    console.log(f"Living World API → http://{host}:{port}")
    uvicorn.run(
        "living_world.web.server:app", host=host, port=port, reload=reload, log_level="info"
    )


@app.command()
def social(
    packs: str = typer.Option("scp,liaozhai,cthulhu", help="Packs to load."),
    days: int = typer.Option(10, help="Days to simulate before measuring."),
    seed: int = typer.Option(42),
    threshold: int = typer.Option(30, help="Min |affinity| to count as a social tie."),
    per_pack: bool = typer.Option(True, help="Show metrics broken out per pack."),
) -> None:
    """Run N days, then print social-network metrics over the affinity graph.

    Implements AgentSociety-style social readout — see KNOWN_ISSUES #16.
    Useful for spotting hub characters, factions, and social isolation.
    """
    from living_world.metrics import compute_social_metrics

    pack_ids = [p.strip() for p in packs.split(",") if p.strip()]
    world, _engine = _build_and_run(pack_ids, days, seed)

    agents = list(world.all_agents())
    console.rule("Whole world")
    console.print(compute_social_metrics(agents, min_abs_affinity=threshold).summary())

    if per_pack:
        for pid in pack_ids:
            console.rule(pid)
            console.print(
                compute_social_metrics(
                    agents,
                    min_abs_affinity=threshold,
                    pack_id=pid,
                ).summary()
            )


@app.command("list-packs")
def list_packs() -> None:
    """List available packs discovered in world_packs/."""
    for entry in sorted(PACKS_DIR.iterdir()):
        if entry.is_dir() and (entry / "pack.yaml").exists():
            console.print(f"  - {entry.name}")


if __name__ == "__main__":
    app()
