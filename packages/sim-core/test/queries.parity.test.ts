import { describe, it, expect } from "vitest";

import queriesFixtures from "./fixtures/queries.json" with { type: "json" };
import chronicleFixtures from "./fixtures/chronicle.json" with { type: "json" };

import {
  recentEvents,
  eventsByPack,
  eventsByDay,
  eventKindDistribution,
  diversitySummary,
  exportChronicleMarkdown,
  type EventForQueries,
  type ChapterForExport,
  type DiversitySummary,
} from "../src/queries.js";

interface QueriesCase {
  name: string;
  events: EventForQueries[];
  expected: {
    recentEvents_5: EventForQueries[];
    eventsByPack: Record<string, EventForQueries[]>;
    eventsByDay: Record<string, EventForQueries[]>;
    eventKindDistribution_3: Array<[string, number]>;
    diversitySummary: DiversitySummary;
  };
}

describe("queries — parity (recent / groupings / diversity)", () => {
  for (const c of queriesFixtures as unknown as QueriesCase[]) {
    it(c.name, () => {
      // recentEvents
      expect(recentEvents(c.events, 5)).toEqual(c.expected.recentEvents_5);

      // eventsByPack — Map → object for comparison
      const byPack = Object.fromEntries(eventsByPack(c.events));
      expect(byPack).toEqual(c.expected.eventsByPack);

      // eventsByDay — Map<number, …> → string-keyed object (json fixtures)
      const byDay: Record<string, EventForQueries[]> = {};
      for (const [k, v] of eventsByDay(c.events)) byDay[String(k)] = v;
      expect(byDay).toEqual(c.expected.eventsByDay);

      // eventKindDistribution
      expect(eventKindDistribution(c.events, 3))
        .toEqual(c.expected.eventKindDistribution_3);

      // diversitySummary
      const ds = diversitySummary(c.events);
      expect(ds.total).toBe(c.expected.diversitySummary.total);
      expect(ds.unique).toBe(c.expected.diversitySummary.unique);
      expect(ds.top_kind).toBe(c.expected.diversitySummary.top_kind);
      expect(ds.top_pct).toBeCloseTo(c.expected.diversitySummary.top_pct, 10);
    });
  }
});

interface ChronicleCase {
  name: string;
  chapters: ChapterForExport[];
  currentTick: number;
  expected: string;
}

describe("queries.exportChronicleMarkdown — parity", () => {
  for (const c of chronicleFixtures as unknown as ChronicleCase[]) {
    it(c.name, () => {
      const got = exportChronicleMarkdown(c.chapters, c.currentTick);
      expect(got).toBe(c.expected);
    });
  }
});

describe("queries — TS-side unit tests", () => {
  it("recentEvents returns full list when n exceeds length", () => {
    const evs = [{
      eventId: "1", tick: 1, packId: "p", tileId: "t",
      eventKind: "x", outcome: "neutral" as const, importance: 0.1,
      tierUsed: 1, isEmergent: false, participants: [],
    }];
    expect(recentEvents(evs, 100)).toEqual(evs);
  });

  it("diversitySummary on empty events", () => {
    const ds = diversitySummary([]);
    expect(ds).toEqual({ total: 0, unique: 0, top_kind: null, top_pct: 0 });
  });

  it("eventKindDistribution caps at topK", () => {
    const make = (kind: string) => ({
      eventId: kind, tick: 1, packId: "p", tileId: "t",
      eventKind: kind, outcome: "neutral" as const, importance: 0.1,
      tierUsed: 1, isEmergent: false, participants: [],
    });
    const evs = ["a", "a", "a", "b", "b", "c"].map(make);
    expect(eventKindDistribution(evs, 2))
      .toEqual([["a", 3], ["b", 2]]);
  });
});
