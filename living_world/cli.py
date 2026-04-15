"""CLI: `world-sim run|digest|list-packs`."""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from living_world.config import load_settings
from living_world.core.world import World
from living_world.dashboard.build import build_repository
from living_world.llm import EnhancementRouter, MockTier2Client, MockTier3Client, OllamaClient
from living_world.tick_loop import TickEngine
from living_world.world_pack import load_all_packs

app = typer.Typer(no_args_is_help=True)
console = Console()

DEFAULT_PACKS_DIR = Path(__file__).resolve().parent.parent / "world_packs"


def _make_router(tier2: str, tier3: str, ollama_model: str) -> EnhancementRouter:
    """Construct EnhancementRouter based on cli flags.
    tier2/tier3 in {'none','mock','ollama'}.
    """
    t2 = None
    t3 = None
    if tier2 == "mock":
        t2 = MockTier2Client()
    elif tier2 == "ollama":
        t2 = OllamaClient(model=ollama_model, declared_tier=2)
    if tier3 == "mock":
        t3 = MockTier3Client()
    elif tier3 == "ollama":
        t3 = OllamaClient(model=ollama_model, declared_tier=3)
    return EnhancementRouter(tier2=t2, tier3=t3)


def _bootstrap_world(packs_dir: Path, pack_ids: list[str]) -> tuple[World, list]:
    loaded = load_all_packs(packs_dir, pack_ids)
    world = World()
    for pack in loaded:
        world.mark_pack_loaded(pack.pack_id)
        for tile in pack.tiles:
            world.add_tile(tile)
        for agent in pack.personas:
            world.add_agent(agent)
    return world, loaded


@app.command()
def run(
    packs: str = typer.Option("scp", help="Comma-separated pack ids."),
    days: int = typer.Option(10, help="How many virtual days to simulate."),
    seed: int = typer.Option(42, help="Random seed."),
    packs_dir: Path = typer.Option(DEFAULT_PACKS_DIR, help="Base directory containing packs."),
    tier2: str = typer.Option("none", help="Tier 2 backend: none | mock | ollama"),
    tier3: str = typer.Option("none", help="Tier 3 backend: none | mock | ollama"),
    ollama_model: str = typer.Option("gemma3:4b", help="Ollama model name if tier2/3=ollama"),
    persist: bool = typer.Option(False, help="Enable persistence (uses settings.yaml backend)"),
) -> None:
    """Run the simulation. Use --tier2=ollama --ollama-model gemma3:4b for real Tier 2 on MacBook."""
    pack_ids = [p.strip() for p in packs.split(",") if p.strip()]
    console.log(f"Loading packs: {pack_ids} from {packs_dir}")
    world, loaded = _bootstrap_world(packs_dir, pack_ids)
    console.log(f"World bootstrapped: {world.summary()}")

    router = _make_router(tier2, tier3, ollama_model)
    if tier2 == "ollama" or tier3 == "ollama":
        probe = OllamaClient(model=ollama_model)
        if not probe.available():
            console.log(f"[yellow]Warning: Ollama at {probe.base_url} not reachable. Tier 2/3 will error individually.[/]")

    repo = None
    if persist:
        settings = load_settings()
        repo = build_repository(settings)
        console.log(f"Persistence backend: {settings.persistence.backend}")
        repo.save_world(world)  # initial snapshot

    engine = TickEngine(world, loaded, seed=seed, router=router, repository=repo)
    console.log(
        f"Running {days} virtual days "
        f"(tier2={tier2}, tier3={tier3}, model={ollama_model if 'ollama' in (tier2, tier3) else 'n/a'})..."
    )
    all_stats = engine.run(days)

    total_events = sum(s.events_realized for s in all_stats)
    total_spotlight = sum(s.spotlight_candidates for s in all_stats)
    total_promo = sum(s.promotions for s in all_stats)
    console.log(
        f"Done. {total_events} events "
        f"({total_spotlight} spotlight, {total_promo} promotions) | "
        f"T1={router.stats.tier1} T2={router.stats.tier2} T3={router.stats.tier3} "
        f"downgrades={router.stats.downgraded}"
    )
    console.log(f"Historical figure registry: {engine.hf_registry.summary()}")

    recent = world.events_since(max(1, world.current_tick - days + 1))
    table = Table(title=f"Last {min(20, len(recent))} events")
    table.add_column("tick", style="cyan", no_wrap=True)
    table.add_column("pack", style="magenta")
    table.add_column("kind", style="yellow")
    table.add_column("tier", style="red")
    table.add_column("imp", justify="right")
    table.add_column("narrative", overflow="fold")
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
    days: int = typer.Option(7, help="How many virtual days to simulate before digest."),
    seed: int = typer.Option(42),
    packs_dir: Path = typer.Option(DEFAULT_PACKS_DIR),
    tier2: str = typer.Option("none"),
    tier3: str = typer.Option("none"),
    ollama_model: str = typer.Option("gemma3:4b"),
) -> None:
    """Run N days then print a per-day '章回体 digest' grouped by pack."""
    pack_ids = [p.strip() for p in packs.split(",") if p.strip()]
    world, loaded = _bootstrap_world(packs_dir, pack_ids)
    router = _make_router(tier2, tier3, ollama_model)
    engine = TickEngine(world, loaded, seed=seed, router=router)
    engine.run(days)

    events = world.events_since(1)
    # group by (tick, pack)
    by_day: dict[int, dict[str, list]] = defaultdict(lambda: defaultdict(list))
    for e in events:
        by_day[e.tick][e.pack_id].append(e)

    for day in sorted(by_day.keys()):
        console.rule(f"第 {day} 日")
        for pack_id, day_events in sorted(by_day[day].items()):
            console.print(f"[bold magenta]\n【{pack_id}】[/]")
            for e in day_events:
                marker = "★" if e.tier_used >= 2 else "·"
                console.print(f"  {marker} {e.best_rendering()}")

    summary = world.summary()
    console.rule("Summary")
    console.print(summary)
    console.print(
        f"router: T1={router.stats.tier1} T2={router.stats.tier2} T3={router.stats.tier3}"
    )


@app.command("list-packs")
def list_packs(packs_dir: Path = typer.Option(DEFAULT_PACKS_DIR)) -> None:
    """List available packs discovered in packs_dir."""
    for entry in sorted(packs_dir.iterdir()):
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
    cmd = [
        sys.executable, "-m", "streamlit", "run", str(app_file),
        "--server.port", str(port),
        "--server.address", host,
    ]
    console.log(f"Launching dashboard at http://{host}:{port}")
    subprocess.run(cmd)


if __name__ == "__main__":
    app()
