import { describe, it, expect } from "vitest";

import socialFixtures from "./fixtures/social_metrics.json" with { type: "json" };

import {
  computeSocialMetrics,
  type AgentForMetrics,
  type SocialMetrics,
  type MetricsOpts,
} from "../src/socialMetrics.js";

describe("socialMetrics.computeSocialMetrics — parity", () => {
  for (const c of socialFixtures as unknown as Array<{
    name: string;
    agents: AgentForMetrics[];
    opts: MetricsOpts;
    expected: SocialMetrics;
  }>) {
    it(c.name, () => {
      const got = computeSocialMetrics(c.agents, c.opts);
      expect(got.nAgents).toBe(c.expected.nAgents);
      expect(got.nEdges).toBe(c.expected.nEdges);
      expect(got.avgDegree).toBeCloseTo(c.expected.avgDegree, 10);
      expect(got.isolated).toEqual(c.expected.isolated);
      expect(got.components).toEqual(c.expected.components);
      // topCentral: ids may tie on degree → assert as a multiset of pairs
      const sortPairs = (xs: Array<[string, number]>) =>
        [...xs].sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]));
      expect(sortPairs(got.topCentral)).toEqual(sortPairs(c.expected.topCentral));
      expect(got.clusteringGlobal).toBeCloseTo(c.expected.clusteringGlobal, 10);
      expect(got.nComponents).toBe(c.expected.nComponents);
      expect(got.biggestComponentSize).toBe(c.expected.biggestComponentSize);
    });
  }
});

describe("socialMetrics — TS-side unit tests", () => {
  it("empty input yields all-zero metrics", () => {
    const m = computeSocialMetrics([]);
    expect(m.nAgents).toBe(0);
    expect(m.nEdges).toBe(0);
    expect(m.avgDegree).toBe(0);
    expect(m.components).toEqual([]);
    expect(m.clusteringGlobal).toBe(0);
  });

  it("dead agents are excluded", () => {
    const agents: AgentForMetrics[] = [
      { agentId: "a", alive: true, packId: "p", relationships: [{ targetId: "b", affinity: 80 }] },
      { agentId: "b", alive: false, packId: "p", relationships: [{ targetId: "a", affinity: 80 }] },
    ];
    const m = computeSocialMetrics(agents);
    expect(m.nAgents).toBe(1);
    expect(m.nEdges).toBe(0);
    // 'a' is alone in the alive pool — counted as isolated
    expect(m.isolated).toEqual(["a"]);
  });

  it("packId filter restricts the pool", () => {
    const agents: AgentForMetrics[] = [
      { agentId: "a", alive: true, packId: "scp", relationships: [{ targetId: "b", affinity: 80 }] },
      { agentId: "b", alive: true, packId: "scp", relationships: [{ targetId: "a", affinity: 80 }] },
      { agentId: "c", alive: true, packId: "liaozhai", relationships: [] },
    ];
    const m = computeSocialMetrics(agents, { packId: "scp" });
    expect(m.nAgents).toBe(2);
    expect(m.nEdges).toBe(1);
  });
});
