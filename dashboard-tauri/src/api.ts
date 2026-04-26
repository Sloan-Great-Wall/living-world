/**
 * REST client for the Python sim API (living_world/web/server.py).
 *
 * Base-URL resolution (single-click app launch):
 *   1. Inside Tauri  → `invoke('get_api_base')` returns the URL of the
 *      sidecar Python process that Tauri spawned at startup. The user
 *      ran ONE command (`npm run tauri dev` / double-click .app) and
 *      didn't have to start `lw serve` themselves.
 *   2. In browser dev (vite at :1420 with no Tauri shell) → fall back
 *      to the legacy `localhost:8000` so `lw serve` still works for
 *      power users who want headless API debugging.
 *
 * The base URL resolves lazily on the first `j()` call. Components
 * call `api.world()` etc. without knowing or caring which mode is
 * active.
 */
import type { AgentForMetrics } from "@living-world/sim-core";
import type {
  Agent, Chapter, FeatureStatus, Tile, WorldEvent, WorldSnapshot,
} from "./types/api";

const FALLBACK_BASE = "http://127.0.0.1:8000";

let resolvedBase: string | null = null;

async function resolveBase(): Promise<string> {
  if (resolvedBase) return resolvedBase;

  // Are we running inside a Tauri shell? __TAURI_INTERNALS__ is set by
  // the runtime; absent in pure-browser dev (vite preview / chrome).
  const isTauri = typeof window !== "undefined"
    && (window as unknown as { __TAURI_INTERNALS__?: unknown }).__TAURI_INTERNALS__ !== undefined;

  if (isTauri) {
    try {
      const { invoke } = await import("@tauri-apps/api/core");
      // Sidecar may still be starting up. Poll a few times before falling back.
      for (let i = 0; i < 40; i++) {
        const base = await invoke<string | null>("get_api_base");
        if (base) {
          resolvedBase = base;
          return base;
        }
        await new Promise((r) => setTimeout(r, 250));
      }
      console.warn("[api] sidecar didn't expose a base URL after 10s; falling back");
    } catch (e) {
      console.warn("[api] tauri invoke failed; falling back:", e);
    }
  }

  resolvedBase = FALLBACK_BASE;
  return FALLBACK_BASE;
}

async function j<T>(path: string, init?: RequestInit): Promise<T> {
  const base = await resolveBase();
  const r = await fetch(base + path, {
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
  socialGraph:  () => j<{ agents: AgentForMetrics[] }>("/api/social_graph"),
  events:       (since = 1, limit = 80) =>
                 j<WorldEvent[]>(`/api/events?since=${since}&limit=${limit}`),
  chronicle:    () => j<Chapter[]>("/api/chronicle"),
  // Removed in 2026-04-26 simplification audit:
  //   chronicleMd / eventKinds  → compute client-side via
  //   @living-world/sim-core (exportChronicleMarkdown / eventKindDistribution)
  //   from /api/chronicle + /api/events. Kills two HTTP routes.
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
