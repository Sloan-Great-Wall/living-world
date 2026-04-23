/**
 * Social network metrics — TypeScript port of `living_world/metrics/social.py`.
 *
 * Pure data-in / data-out: no World coupling. Caller passes a flat
 * array of `{agentId, alive, packId, relationships: [{targetId, affinity}]}`
 * and gets back the same `SocialMetrics` shape Python emits.
 *
 * Determinism: components and isolated lists are sorted exactly like
 * Python — by id within each component, components by descending size.
 * `topCentral` ties broken by JS sort stability (matches Python's stable
 * `sorted` since input order is preserved upstream of the metric).
 */

export interface RelationshipLite {
  targetId: string;
  affinity: number;
}

export interface AgentForMetrics {
  agentId: string;
  alive: boolean;
  packId: string;
  relationships: ReadonlyArray<RelationshipLite>;
}

export interface SocialMetrics {
  nAgents: number;
  nEdges: number;
  avgDegree: number;
  isolated: string[];
  components: string[][];
  topCentral: Array<[string, number]>;
  clusteringGlobal: number;
  // Derived getters as plain fields for ease of JSON parity
  nComponents: number;
  biggestComponentSize: number;
}

export interface MetricsOpts {
  minAbsAffinity?: number;
  packId?: string;
  topK?: number;
}

// ── Public API ──────────────────────────────────────────────────────────

export function affinityGraph(
  agents: ReadonlyArray<AgentForMetrics>,
  opts: MetricsOpts = {},
): Map<string, Set<string>> {
  const minAbs = opts.minAbsAffinity ?? 30;
  const packFilter = opts.packId;
  const pool = agents.filter(
    (a) => a.alive && (packFilter === undefined || a.packId === packFilter),
  );
  const poolIds = new Set(pool.map((a) => a.agentId));
  const adj = new Map<string, Set<string>>();
  for (const a of pool) adj.set(a.agentId, new Set());
  for (const a of pool) {
    for (const rel of a.relationships) {
      if (!poolIds.has(rel.targetId)) continue;
      if (Math.abs(rel.affinity) >= minAbs) {
        adj.get(a.agentId)!.add(rel.targetId);
        // Symmetrize — but only between pool members
        if (adj.has(rel.targetId)) {
          adj.get(rel.targetId)!.add(a.agentId);
        }
      }
    }
  }
  return adj;
}

export function computeSocialMetrics(
  agents: ReadonlyArray<AgentForMetrics>,
  opts: MetricsOpts = {},
): SocialMetrics {
  const topK = opts.topK ?? 5;
  const adj = affinityGraph(agents, opts);
  const n = adj.size;
  if (n === 0) {
    return {
      nAgents: 0, nEdges: 0, avgDegree: 0, isolated: [], components: [],
      topCentral: [], clusteringGlobal: 0, nComponents: 0,
      biggestComponentSize: 0,
    };
  }

  // Edges (count once per pair) — ordered tuple (min, max)
  const edgesSeen = new Set<string>();
  for (const [a, neigh] of adj) {
    for (const b of neigh) {
      const lo = a < b ? a : b;
      const hi = a < b ? b : a;
      edgesSeen.add(`${lo}\u0000${hi}`);
    }
  }
  const nEdges = edgesSeen.size;

  const degrees = new Map<string, number>();
  for (const [a, neigh] of adj) degrees.set(a, neigh.size);

  let degSum = 0;
  for (const d of degrees.values()) degSum += d;
  const avgDegree = degSum / n;

  const isolated = [...degrees.entries()]
    .filter(([, d]) => d === 0)
    .map(([a]) => a)
    .sort();

  const topCentral: Array<[string, number]> = [...degrees.entries()]
    .sort((a, b) => b[1] - a[1])
    .slice(0, topK);

  const components = connectedComponents(adj);
  const clustering = globalClustering(adj);

  return {
    nAgents: n,
    nEdges,
    avgDegree,
    isolated,
    components,
    topCentral,
    clusteringGlobal: clustering,
    nComponents: components.length,
    biggestComponentSize: components.reduce((m, c) => Math.max(m, c.length), 0),
  };
}

// ── Internals ───────────────────────────────────────────────────────────

function connectedComponents(adj: Map<string, Set<string>>): string[][] {
  const seen = new Set<string>();
  const out: string[][] = [];
  // Iteration order in Python is insertion order; same for JS Map.
  for (const start of adj.keys()) {
    if (seen.has(start)) continue;
    const comp: string[] = [];
    const stack: string[] = [start];
    while (stack.length > 0) {
      const node = stack.pop()!;
      if (seen.has(node)) continue;
      seen.add(node);
      comp.push(node);
      for (const nb of adj.get(node)!) {
        if (!seen.has(nb)) stack.push(nb);
      }
    }
    out.push(comp.sort());
  }
  out.sort((a, b) => b.length - a.length);
  return out;
}

function globalClustering(adj: Map<string, Set<string>>): number {
  const coeffs: number[] = [];
  for (const [, neigh] of adj) {
    const k = neigh.size;
    if (k < 2) continue;
    const nlist = [...neigh];
    let triangles = 0;
    for (let i = 0; i < nlist.length; i++) {
      for (let j = i + 1; j < nlist.length; j++) {
        const ni = adj.get(nlist[i]!);
        if (ni && ni.has(nlist[j]!)) triangles++;
      }
    }
    const possible = (k * (k - 1)) / 2;
    coeffs.push(possible > 0 ? triangles / possible : 0);
  }
  if (coeffs.length === 0) return 0;
  return coeffs.reduce((a, b) => a + b, 0) / coeffs.length;
}
