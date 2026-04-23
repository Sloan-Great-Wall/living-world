"""Marimo notebook — multi-seed batch diversity + invariant report.

Run interactively:
    marimo edit reports/diversity.py
Run as script (CI mode, prints summary, exit 0/1 on invariant failures):
    python reports/diversity.py [--seeds 5] [--ticks 10]
Export shareable HTML:
    marimo export html reports/diversity.py -o /tmp/diversity.html

What it does:
- Bootstraps the 3-pack world for each of N seeds, runs M ticks
  rules-only (fast, deterministic — ~2s/run)
- Aggregates per-seed metrics: total events, unique kinds, top-kind %,
  invariant pass/fail counts, deaths, agent activity distribution
- Renders comparative tables + simple charts so you can see at a glance
  whether a sim configuration produces consistent / diverse stories

Why marimo (not Jupyter):
- Cells are pure .py files → git-diff friendly, no JSON cell metadata
- Reactive: change `n_seeds` and downstream cells re-run automatically
- `marimo export html` ships a self-contained interactive doc
"""

import marimo

__generated_with = "0.23.2"
app = marimo.App(width="medium")


@app.cell
def _imports():
    import statistics
    import sys
    from collections import Counter
    from pathlib import Path

    import marimo as mo

    repo_root = Path(__file__).resolve().parent.parent
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))

    from living_world import PACKS_DIR
    from living_world.config import load_settings
    from living_world.factory import bootstrap_world, make_engine
    from living_world.invariants import check_all, summary
    from living_world.queries import (
        diversity_summary, event_kind_distribution,
    )

    return (
        Counter,
        PACKS_DIR,
        bootstrap_world,
        check_all,
        diversity_summary,
        event_kind_distribution,
        load_settings,
        make_engine,
        mo,
        statistics,
        summary,
    )


@app.cell
def _params(mo):
    n_seeds = mo.ui.slider(1, 10, value=5, label="seeds")
    n_ticks = mo.ui.slider(2, 30, value=8, label="ticks per run")
    pack_choice = mo.ui.multiselect(
        options=["scp", "liaozhai", "cthulhu"],
        value=["scp", "liaozhai", "cthulhu"],
        label="packs",
    )
    mo.md(
        f"# Multi-seed diversity report\n\n"
        f"Vary the controls below — every downstream cell re-runs."
    )
    return n_seeds, n_ticks, pack_choice


@app.cell
def _show_controls(mo, n_seeds, n_ticks, pack_choice):
    mo.hstack([n_seeds, n_ticks, pack_choice])
    return


@app.cell
def _run_batch(
    PACKS_DIR,
    bootstrap_world,
    check_all,
    diversity_summary,
    event_kind_distribution,
    load_settings,
    make_engine,
    mo,
    n_seeds,
    n_ticks,
    pack_choice,
    summary,
):
    # Force rules-only for speed + determinism (no Ollama dependency).
    settings = load_settings()
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

    runs = []
    for seed in range(n_seeds.value):
        world, loaded = bootstrap_world(PACKS_DIR, list(pack_choice.value))
        engine = make_engine(world, loaded, settings, seed)
        engine.run(n_ticks.value)
        ds = diversity_summary(world)
        inv_results = check_all(world, engine)
        passed, warned, failed = summary(inv_results)
        runs.append({
            "seed": seed,
            "events": ds["total"],
            "unique_kinds": ds["unique"],
            "top_kind": ds["top_kind"],
            "top_pct": round(ds["top_pct"], 1),
            "deaths": sum(1 for a in world.all_agents() if not a.is_alive()),
            "alive": sum(1 for _ in world.living_agents()),
            "chapters": len(world.chapters),
            "inv_pass": passed,
            "inv_warn": warned,
            "inv_fail": failed,
            "top5": event_kind_distribution(world, top_k=5),
        })
    mo.md(
        f"## ✅ Ran {n_seeds.value} seeds × {n_ticks.value} ticks "
        f"on packs {sorted(pack_choice.value)}"
    )
    return (runs,)


@app.cell
def _per_seed_table(mo, runs):
    seed_rows = [
        {
            "seed": run["seed"],
            "events": run["events"],
            "unique kinds": run["unique_kinds"],
            "top kind": f"{run['top_kind']} ({run['top_pct']}%)",
            "deaths": run["deaths"],
            "alive": run["alive"],
            "chapters": run["chapters"],
            "invariants": f"{run['inv_pass']}✅ {run['inv_warn']}⚠️ {run['inv_fail']}❌",
        }
        for run in runs
    ]
    mo.md("### Per-seed breakdown")
    mo.ui.table(seed_rows)
    return


@app.cell
def _aggregate_stats(mo, runs, statistics):
    agg_n = len(runs)
    agg_events = [r["events"] for r in runs]
    agg_unique = [r["unique_kinds"] for r in runs]
    agg_top_pct = [r["top_pct"] for r in runs]
    agg_deaths = [r["deaths"] for r in runs]
    agg_failed = sum(r["inv_fail"] for r in runs)
    agg_warned = sum(r["inv_warn"] for r in runs)

    def _fmt(xs):
        if not xs:
            return "—"
        if len(xs) == 1:
            return f"{xs[0]:.1f}"
        return f"{statistics.mean(xs):.1f} ± {statistics.stdev(xs):.1f}"

    mo.md(
        f"""
    ### Aggregate across {agg_n} seeds

    | metric | value |
    |--------|-------|
    | events / run | **{_fmt(agg_events)}** |
    | unique kinds / run | **{_fmt(agg_unique)}** |
    | top-kind % / run | **{_fmt(agg_top_pct)}** (lower = more diverse) |
    | deaths / run | **{_fmt(agg_deaths)}** |
    | invariant failures total | **{agg_failed}** {'❌' if agg_failed else '✅'} |
    | invariant warnings total | {agg_warned} {'⚠️' if agg_warned else ''} |
    """
    )
    return agg_failed, agg_warned


@app.cell
def _kind_freq_across_seeds(Counter, mo, runs):
    """Which event kinds appear across many seeds (universal vs rare)."""
    kind_seed_count: Counter = Counter()
    for run in runs:
        for kind, _ in run["top5"]:
            kind_seed_count[kind] += 1
    mo.md("### Kind universality\n\n"
           "How many seeds had each kind in their top-5? "
           "Universal = appears every run; rare = lucky one-off.")
    kind_rows = [
        {"kind": k, "seeds_with_it": n, "fraction": f"{n}/{len(runs)}"}
        for k, n in kind_seed_count.most_common(20)
    ]
    mo.ui.table(kind_rows)
    return


@app.cell
def _verdict(agg_failed, agg_warned, mo):
    if agg_failed > 0:
        verdict = mo.md(f"## ❌ {agg_failed} invariant failures across runs — investigate")
    elif agg_warned > 0:
        verdict = mo.md(f"## ⚠️ {agg_warned} warnings — sim healthy but watch")
    else:
        verdict = mo.md("## ✅ All invariants pass on every seed")
    verdict
    return


def _cli():
    """Run rules-only smoke across N seeds, print summary, exit 0/1."""
    import argparse
    import sys
    from pathlib import Path
    repo = Path(__file__).resolve().parent.parent
    if str(repo) not in sys.path:
        sys.path.insert(0, str(repo))

    from living_world import PACKS_DIR
    from living_world.config import load_settings
    from living_world.factory import bootstrap_world, make_engine
    from living_world.invariants import check_all, summary
    from living_world.queries import diversity_summary

    p = argparse.ArgumentParser()
    p.add_argument("--seeds", type=int, default=5)
    p.add_argument("--ticks", type=int, default=8)
    p.add_argument("--packs", default="scp,liaozhai,cthulhu")
    args = p.parse_args()

    settings = load_settings()
    for attr in (
        "dynamic_dialogue_enabled", "llm_movement_enabled",
        "weekly_planning_enabled", "conversation_loop_enabled",
        "chronicler_enabled", "emergent_events_enabled",
        "subjective_perception_enabled", "self_update_enabled",
        "conscious_override_enabled",
    ):
        setattr(settings.llm, attr, False)
    settings.llm.tier2_provider = "none"
    settings.llm.tier3_provider = "none"
    settings.memory.enabled = False
    pack_ids = [p.strip() for p in args.packs.split(",") if p.strip()]

    total_failed = 0
    print(f"Running {args.seeds} seeds × {args.ticks} ticks on {pack_ids}")
    for seed in range(args.seeds):
        world, loaded = bootstrap_world(PACKS_DIR, pack_ids)
        engine = make_engine(world, loaded, settings, seed)
        engine.run(args.ticks)
        ds = diversity_summary(world)
        results = check_all(world, engine)
        passed, warned, failed = summary(results)
        total_failed += failed
        print(
            f"  seed={seed}  events={ds['total']:3d}  "
            f"unique={ds['unique']:2d}  top={ds['top_kind']}({ds['top_pct']:.1f}%)  "
            f"inv={passed}✅/{warned}⚠/{failed}❌"
        )
    print(f"\nTotal invariant failures: {total_failed}")
    sys.exit(1 if total_failed else 0)


if __name__ == "__main__":
    # Dual-mode entry: with --flag arguments → CLI batch (CI-friendly).
    # Otherwise → marimo app (run via `marimo edit/run reports/diversity.py`).
    import sys
    if any(a.startswith("--") for a in sys.argv[1:]):
        _cli()
    else:
        app.run()
