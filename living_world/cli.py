"""CLI: `world-sim run|digest|list-packs|dashboard`.

Thin wrapper around `factory.py` — same engine construction as the dashboard
so advanced features (dialogue, conscience, planner, etc.) light up automatically
when settings.yaml has them enabled.
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
    pack_ids: list[str], days: int, seed: int, *, persist: bool = False,
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
    console.log(
        f"Done. {total_events} events | T1={n.tier1} T3={n.tier3}"
    )
    console.log(f"Historical figures: {engine.hf_registry.summary()}")

    recent = world.events_since(max(1, world.current_tick - days + 1))
    table = Table(title=f"Last {min(20, len(recent))} events")
    for col, style in [("tick", "cyan"), ("pack", "magenta"), ("kind", "yellow"),
                       ("tier", "red"), ("imp", None), ("narrative", None)]:
        table.add_column(col, style=style or "", no_wrap=(col == "tick"),
                          justify="right" if col == "imp" else "left",
                          overflow="fold" if col == "narrative" else None)
    for e in recent[-20:]:
        table.add_row(str(e.tick), e.pack_id, e.event_kind,
                       str(e.tier_used), f"{e.importance:.2f}", e.best_rendering())
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


@app.command("list-packs")
def list_packs() -> None:
    """List available packs discovered in world_packs/."""
    for entry in sorted(PACKS_DIR.iterdir()):
        if entry.is_dir() and (entry / "pack.yaml").exists():
            console.print(f"  - {entry.name}")


@app.command()
def dashboard(
    port: int = typer.Option(8501),
    host: str = typer.Option("localhost"),
) -> None:
    """Launch the Streamlit dashboard in the default browser."""
    import subprocess
    import sys

    app_file = Path(__file__).resolve().parent / "dashboard" / "app.py"
    cmd = [sys.executable, "-m", "streamlit", "run", str(app_file),
           "--server.port", str(port), "--server.address", host]
    console.log(f"Launching dashboard at http://{host}:{port}")
    subprocess.run(cmd)


if __name__ == "__main__":
    app()
