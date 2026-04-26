/**
 * Read-only world queries — TypeScript port of `living_world.queries`.
 *
 * Pure data-in / data-out: caller supplies the event list (or chapter
 * list); we never reach into a `World` object. This keeps the module
 * portable to the browser, where `World` doesn't exist.
 *
 * Phase 3 motivation:
 *   These helpers were called from the FastAPI server PER REQUEST.
 *   The dashboard now runs them client-side from a single `/api/events`
 *   fetch, eliminating round-trips for every filter / aggregation toggle.
 *
 * Parity discipline (AI-Native criterion A):
 *   `scripts/dump_fixtures.py` writes JSON fixtures from Python; this
 *   module's tests assert byte-identical results. Any algorithmic drift
 *   is caught at `make check` time.
 */

import type { Outcome } from "./dice.js";

// ── DTOs (mirror the Python LegendEvent / Chapter shape) ────────────────

/**
 * Event projection used by the query helpers. Wider than `EventLite` in
 * dice.ts because queries need pack/tier metadata that dice doesn't.
 * Use this for inputs to query functions; dashboard receives matching
 * `WorldEvent` from `/api/events`.
 */
export interface EventForQueries {
  eventId: string;
  tick: number;
  packId: string;
  tileId: string;
  eventKind: string;
  outcome: Outcome;
  importance: number;
  tierUsed: number;
  isEmergent: boolean;
  participants: ReadonlyArray<string>;
  // Optional rendering fields the chronicle export reads.
  templateRendering?: string;
  spotlightRendering?: string;
}

export interface ChapterForExport {
  tick: number;
  packId: string;
  title: string;
  body: string;
  eventIds: ReadonlyArray<string>;
}

// ── Event list slicers ──────────────────────────────────────────────────

/**
 * Last N events (oldest first) — caller passes the full ordered list.
 * Returns the same array slice Python's `recent_events` would.
 */
export function recentEvents(
  events: ReadonlyArray<EventForQueries>,
  n: number = 50,
): EventForQueries[] {
  if (n >= events.length) return events.slice();
  return events.slice(events.length - n);
}

/** Events grouped by `packId`. Insertion order preserved per pack. */
export function eventsByPack(
  events: ReadonlyArray<EventForQueries>,
): Map<string, EventForQueries[]> {
  const out = new Map<string, EventForQueries[]>();
  for (const e of events) {
    const arr = out.get(e.packId);
    if (arr) arr.push(e);
    else out.set(e.packId, [e]);
  }
  return out;
}

/** Events grouped by tick. Tick keys come back sorted ascending. */
export function eventsByDay(
  events: ReadonlyArray<EventForQueries>,
): Map<number, EventForQueries[]> {
  const out = new Map<number, EventForQueries[]>();
  for (const e of events) {
    const arr = out.get(e.tick);
    if (arr) arr.push(e);
    else out.set(e.tick, [e]);
  }
  // Re-sort by key for stable consumer iteration; Python's defaultdict
  // doesn't guarantee key order across insertion patterns.
  return new Map([...out.entries()].sort((a, b) => a[0] - b[0]));
}

// ── Aggregations ────────────────────────────────────────────────────────

/**
 * Top-K most frequent event kinds, descending by count, ties broken by
 * insertion order (matching Python `collections.Counter.most_common`).
 */
export function eventKindDistribution(
  events: ReadonlyArray<EventForQueries>,
  topK: number = 10,
): Array<[string, number]> {
  const counts = new Map<string, number>();
  for (const e of events) {
    counts.set(e.eventKind, (counts.get(e.eventKind) ?? 0) + 1);
  }
  // Stable sort: Map iteration is insertion order, sort is stable in V8.
  return [...counts.entries()]
    .sort((a, b) => b[1] - a[1])
    .slice(0, topK);
}

export interface DiversitySummary {
  total: number;
  unique: number;
  top_kind: string | null;
  top_pct: number;
}

/**
 * Headline diversity stats. Field names use snake_case for the two
 * legacy keys (top_kind / top_pct) so this stays compatible with the
 * Python output that ships through `/api/world` today.
 */
export function diversitySummary(
  events: ReadonlyArray<EventForQueries>,
): DiversitySummary {
  if (events.length === 0) {
    return { total: 0, unique: 0, top_kind: null, top_pct: 0.0 };
  }
  const counts = new Map<string, number>();
  for (const e of events) counts.set(e.eventKind, (counts.get(e.eventKind) ?? 0) + 1);
  // most_common(1)
  let topKind = "";
  let topN = 0;
  for (const [k, v] of counts) {
    if (v > topN) {
      topKind = k;
      topN = v;
    }
  }
  return {
    total: events.length,
    unique: counts.size,
    top_kind: topKind,
    top_pct: (100 * topN) / events.length,
  };
}

// ── Chronicle markdown export ───────────────────────────────────────────

/**
 * Render the chapter list as a Markdown chronicle.
 *
 * Mirrors `living_world.queries.export_chronicle_markdown` exactly so
 * "Download chronicle.md" can run in the browser without a round-trip.
 */
export function exportChronicleMarkdown(
  chapters: ReadonlyArray<ChapterForExport>,
  currentTick: number,
): string {
  if (chapters.length === 0) {
    return "# (no chapters yet)\n\nThe chronicler hasn't fired in this run.\n";
  }
  const byPack = new Map<string, ChapterForExport[]>();
  for (const ch of chapters) {
    const arr = byPack.get(ch.packId);
    if (arr) arr.push(ch);
    else byPack.set(ch.packId, [ch]);
  }
  const lines: string[] = ["# Chronicle", ""];
  lines.push(
    `_World ran ${currentTick} tick(s). ${chapters.length} chapters across ` +
      `${byPack.size} pack(s)._\n`,
  );
  // Sort packs alphabetically; chapters within each pack by tick asc.
  for (const packId of [...byPack.keys()].sort()) {
    lines.push(`## ${packId}\n`);
    const pack = byPack.get(packId)!;
    const sorted = [...pack].sort((a, b) => (a.tick ?? 0) - (b.tick ?? 0));
    for (const ch of sorted) {
      const title = ch.title || "(untitled)";
      const tick = ch.tick;
      const body = (ch.body ?? "").trim();
      lines.push(`### Day ${tick} — ${title}\n`);
      lines.push(body);
      lines.push(""); // blank between chapters
    }
  }
  return lines.join("\n");
}
