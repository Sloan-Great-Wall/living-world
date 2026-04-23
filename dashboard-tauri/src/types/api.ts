/**
 * API contract — TypeScript is the source of truth.
 *
 * The Python FastAPI backend (living_world/web/server.py) serves JSON
 * matching these types. When sim core gets ported to TypeScript, this
 * file stays the same; only the implementation changes.
 *
 * Rule: ALL keys camelCase. Python pydantic uses alias_generator to
 * emit camelCase despite its snake_case field names internally.
 */

export interface WorldSnapshot {
  loaded: boolean;
  tick: number;
  packs: string[];
  agentsAlive: number;
  agentsTotal: number;
  eventsTotal: number;
  deaths: number;
  chapters: number;
  tiles: number;
  diversity: DiversitySummary | null;
  modelTier2: string;
  modelTier3: string;
}

export interface DiversitySummary {
  total: number;
  unique: number;
  top_kind: string | null;
  top_pct: number;
}

export interface Agent {
  id: string;
  name: string;
  pack: string;
  alignment: string;
  isHf: boolean;
  alive: boolean;
  tile: string;
  x: number;
  y: number;
  tags: string[];
  // Only present on GET /api/agent/{id}
  persona?: string;
  goal?: string | null;
  needs?: Record<string, number>;
  emotions?: Record<string, number>;
  attributes?: Record<string, number | string>;
  beliefs?: Record<string, string>;
  motivations?: string[] | null;
  weeklyPlan?: Record<string, string[]> | null;
  relationships?: Relationship[];
  recentEvents?: WorldEvent[];
}

export interface Relationship {
  target: string;
  kind: string;
  affinity: number;
}

export interface WorldEvent {
  id: string;
  tick: number;
  pack: string;
  tile: string;
  kind: string;
  outcome: "success" | "failure" | "neutral";
  importance: number;
  tier: number;
  isEmergent: boolean;
  participants: string[];
  narrative: string;
}

export interface Tile {
  id: string;
  name: string;
  pack: string;
  type: string;
  x: number;
  y: number;
}

export interface FeatureStatus {
  name: string;
  on: boolean;
  detail: string;
}

export interface Chapter {
  tick: number;
  pack_id: string;
  title: string;
  body: string;
  event_ids: string[];
}
