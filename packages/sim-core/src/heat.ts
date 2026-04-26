/**
 * Tile heat scoring — TypeScript port of `living_world.rules.heat`.
 *
 * Why port: the heat heuristic decides which tiles get the LLM emergent
 * proposer's budget. Today this runs in Python and the result is opaque
 * to the dashboard. Porting lets the dashboard pre-compute and DISPLAY
 * the heat ranking ("Bright Lab is hot today, expect drama") without
 * waiting for an emergent event to land.
 *
 * Pure data-in / data-out: caller pre-aggregates residents + recent
 * tile events and passes them in. The function never reaches into a
 * `World`, matching the rest of sim-core's portability rule.
 */

// ── DTOs ────────────────────────────────────────────────────────────────

export interface AgentForHeat {
  agentId: string;
  isHistoricalFigure: boolean;
  /** Map of (otherAgentId → affinity). Read-only; only |aff|≥40 entries
   *  matter for the strong-pair signal, callers may pre-filter. */
  affinityTo: Readonly<Record<string, number>>;
}

export interface TileForHeat {
  tileId: string;
  residents: ReadonlyArray<AgentForHeat>;
  /** Count of events recorded in this tile within the lookback window. */
  recentEventCount: number;
}

// ── Scoring ─────────────────────────────────────────────────────────────

/**
 * Heat score for one tile. Higher = more likely something dramatic
 * should happen there now.
 *
 * Signal weights (matching Python verbatim):
 *   +1.0 per resident
 *   +2.0 per historical figure
 *   +1.5 per pairwise |affinity| ≥ 40 (friend OR enemy — both = drama)
 *   +0.3 per event in this tile in the lookback window
 *
 * Returns 0.0 if fewer than 2 residents — emergent events need
 * interaction; a single agent in an empty room is not interesting.
 */
export function scoreTileHeat(tile: TileForHeat): number {
  const residents = tile.residents;
  if (residents.length < 2) return 0.0;
  let hfCount = 0;
  for (const a of residents) if (a.isHistoricalFigure) hfCount++;

  let strongPairs = 0;
  for (let i = 0; i < residents.length; i++) {
    const a = residents[i]!;
    for (let j = i + 1; j < residents.length; j++) {
      const b = residents[j]!;
      // a's recorded affinity toward b OR b's toward a — match Python
      // which uses Agent.get_affinity (one-sided lookup; we mirror that).
      const aff = a.affinityTo[b.agentId] ?? 0;
      if (Math.abs(aff) >= 40) strongPairs++;
    }
  }

  return (
    residents.length +
    2 * hfCount +
    1.5 * strongPairs +
    0.3 * tile.recentEventCount
  );
}

export interface HeatOpts {
  /** Top-K cap on returned tiles. Default 2 — matches Python. */
  limit?: number;
  /** Threshold below which a tile is excluded entirely. Default 3.5. */
  minHeat?: number;
}

/**
 * Top-K hottest tiles, ordered desc. Mirrors `hot_tiles`.
 * Tie-breaking by tileId asc (Python sorted() is stable; insertion
 * order across `world.all_tiles()` is the upstream contract — we
 * accept the same convention).
 */
export function hotTiles(
  tiles: ReadonlyArray<TileForHeat>,
  opts: HeatOpts = {},
): TileForHeat[] {
  const limit = opts.limit ?? 2;
  const minHeat = opts.minHeat ?? 3.5;
  const scored: Array<{ tile: TileForHeat; heat: number }> = [];
  for (const t of tiles) {
    const h = scoreTileHeat(t);
    if (h >= minHeat) scored.push({ tile: t, heat: h });
  }
  // sort desc by heat; stable so input order persists for ties.
  scored.sort((a, b) => b.heat - a.heat);
  return scored.slice(0, limit).map((s) => s.tile);
}
