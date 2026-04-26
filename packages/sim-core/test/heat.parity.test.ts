import { describe, it, expect } from "vitest";

import heatFixtures from "./fixtures/heat.json" with { type: "json" };

import {
  scoreTileHeat,
  hotTiles,
  type TileForHeat,
} from "../src/heat.js";

interface HeatCase {
  name: string;
  tiles: TileForHeat[];
  expected: {
    scores: Record<string, number>;
    hot_tiles_default: string[];
  };
}

describe("heat — parity (scoreTileHeat / hotTiles)", () => {
  for (const c of heatFixtures as unknown as HeatCase[]) {
    it(c.name, () => {
      // Per-tile scores
      for (const tile of c.tiles) {
        const got = scoreTileHeat(tile);
        const want = c.expected.scores[tile.tileId];
        expect(got).toBeCloseTo(want!, 10);
      }
      // hotTiles default options (limit=2, minHeat=3.5)
      const hot = hotTiles(c.tiles).map((t) => t.tileId);
      expect(hot).toEqual(c.expected.hot_tiles_default);
    });
  }
});

describe("heat — TS-side unit tests", () => {
  it("returns 0 when fewer than 2 residents", () => {
    const tile: TileForHeat = {
      tileId: "alone",
      residents: [{ agentId: "a", isHistoricalFigure: true, affinityTo: {} }],
      recentEventCount: 100,
    };
    expect(scoreTileHeat(tile)).toBe(0);
  });

  it("hotTiles respects minHeat threshold", () => {
    const tile: TileForHeat = {
      tileId: "borderline",
      residents: [
        { agentId: "a", isHistoricalFigure: false, affinityTo: {} },
        { agentId: "b", isHistoricalFigure: false, affinityTo: {} },
      ],
      recentEventCount: 0,
    };
    // score = 2 (residents only) → below default 3.5
    expect(hotTiles([tile])).toEqual([]);
    // raise the bar even higher: still empty
    expect(hotTiles([tile], { minHeat: 1.5 })).toEqual([tile]);
  });

  it("hotTiles respects limit", () => {
    const make = (id: string): TileForHeat => ({
      tileId: id,
      residents: [
        { agentId: `${id}-a`, isHistoricalFigure: true, affinityTo: {} },
        { agentId: `${id}-b`, isHistoricalFigure: true, affinityTo: {} },
      ],
      recentEventCount: 0,
    });
    const tiles = [make("t1"), make("t2"), make("t3")];
    const result = hotTiles(tiles, { limit: 2 });
    expect(result).toHaveLength(2);
  });
});
