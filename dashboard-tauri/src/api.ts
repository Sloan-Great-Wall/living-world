/**
 * REST client for the Python sim API (living_world/web/server.py).
 *
 * Isolated here so the eventual TypeScript sim port can swap this
 * module for in-process calls (Tauri invoke or direct function calls)
 * without touching any component.
 */
import type {
  Agent, Chapter, FeatureStatus, Tile, WorldEvent, WorldSnapshot,
} from "./types/api";

const BASE = "http://127.0.0.1:8000";

async function j<T>(path: string, init?: RequestInit): Promise<T> {
  const r = await fetch(BASE + path, {
    ...init,
    headers: { "Content-Type": "application/json", ...init?.headers },
  });
  if (!r.ok) {
    const txt = await r.text().catch(() => "");
    throw new Error(`${init?.method || "GET"} ${path} → ${r.status}: ${txt}`);
  }
  return r.json();
}

export const api = {
  health:       () => j<{ ok: boolean; loaded: boolean }>("/api/health"),
  packsAvail:   () => j<string[]>("/api/packs_available"),
  world:        () => j<WorldSnapshot>("/api/world"),
  features:     () => j<FeatureStatus[]>("/api/feature_status"),
  agents:       () => j<Agent[]>("/api/agents"),
  agent:        (id: string) => j<Agent>(`/api/agent/${encodeURIComponent(id)}`),
  tiles:        () => j<Tile[]>("/api/tiles"),
  events:       (since = 1, limit = 80) =>
                 j<WorldEvent[]>(`/api/events?since=${since}&limit=${limit}`),
  chronicle:    () => j<Chapter[]>("/api/chronicle"),
  chronicleMd:  () => j<{ markdown: string }>("/api/chronicle.md"),
  eventKinds:   (topK = 10) => j<[string, number][]>(`/api/event_kinds?top_k=${topK}`),
  settings:     () => j<Record<string, unknown>>("/api/settings"),
  saveSettings: (patch: Record<string, unknown>) =>
                 j<Record<string, unknown>>("/api/settings", {
                   method: "POST",
                   body: JSON.stringify(patch),
                 }),
  resetWorld:   () => j<{ ok: boolean }>("/api/reset", { method: "POST" }),
  templates:    () => j<{
                   pack: string; eventKind: string;
                   description: string; baseImportance: number; source: string;
                 }[]>("/api/templates"),
  personas:     () => j<{
                   id: string; name: string; pack: string; alignment: string;
                   isHf: boolean; tags: string[]; persona: string;
                 }[]>("/api/personas"),
  bootstrap:    (packs: string[], seed = 42) =>
                 j<WorldSnapshot>("/api/bootstrap", {
                   method: "POST",
                   body: JSON.stringify({ packs, seed }),
                 }),
  tick:         (n = 1) =>
                 j<WorldSnapshot>("/api/tick", {
                   method: "POST",
                   body: JSON.stringify({ n }),
                 }),
};
