/**
 * worldStore — live sim state, fetched from the Python REST API.
 *
 * Three primary signals:
 *   - worldSnapshot: top-bar stats + pack list
 *   - agents:        map renders from this
 *   - tiles:         per-tile positions for stable dot placement
 *
 * Auto-play: optional interval that ticks +1 day every N ms. The user
 * can Play / Pause / Reset. Reset calls the API to re-bootstrap with
 * the same packs.
 */
import { createSignal } from "solid-js";
import { api } from "../api";
import type { Agent, Chapter, Tile, WorldEvent, WorldSnapshot } from "../types/api";

const EMPTY_SNAP: WorldSnapshot = {
  loaded: false, tick: 0, packs: [], agentsAlive: 0, agentsTotal: 0,
  eventsTotal: 0, deaths: 0, chapters: 0, tiles: 0,
  modelTier2: "—", modelTier3: "—",
};

export const [worldSnapshot, setWorldSnapshot] =
  createSignal<WorldSnapshot>(EMPTY_SNAP);
export const [agents, setAgents] = createSignal<Agent[]>([]);
export const [tiles, setTiles] = createSignal<Tile[]>([]);
export const [recentEvents, setRecentEvents] = createSignal<WorldEvent[]>([]);
export const [chapters, setChapters] = createSignal<Chapter[]>([]);
export const [apiOnline, setApiOnline] = createSignal(false);
export const [busy, setBusy] = createSignal(false);
export const [errorMsg, setErrorMsg] = createSignal<string | null>(null);

export const [selectedPacks, setSelectedPacks] = createSignal<string[]>([
  "scp", "liaozhai", "cthulhu",
]);
export const [selectedAgent, setSelectedAgent] = createSignal<string | null>(null);

// Auto-play
export const [playing, setPlaying] = createSignal(false);
export const [playSpeedMs, setPlaySpeedMs] = createSignal(1500);
let playTimer: number | null = null;

export const isLoaded = () => worldSnapshot().loaded;

export function togglePack(pid: string) {
  const cur = selectedPacks();
  setSelectedPacks(
    cur.includes(pid) ? cur.filter((p) => p !== pid) : [...cur, pid],
  );
}

async function refreshWorldAndAgents() {
  try {
    const [snap, ags, tls, evs, chs] = await Promise.all([
      api.world(), api.agents(), api.tiles(),
      api.events(1, 200).catch(() => [] as WorldEvent[]),
      api.chronicle().catch(() => [] as Chapter[]),
    ]);
    setWorldSnapshot(snap);
    setAgents(ags);
    setTiles(tls);
    setRecentEvents(evs);
    setChapters(chs);
  } catch (e) {
    console.warn("refresh failed", e);
  }
}

export async function bootstrap() {
  setBusy(true);
  setErrorMsg(null);
  try {
    await api.bootstrap(selectedPacks());
    await refreshWorldAndAgents();
  } catch (e) {
    setErrorMsg(`Bootstrap failed: ${(e as Error).message}`);
  } finally {
    setBusy(false);
  }
}

export async function tick(n = 1) {
  if (busy()) return;
  setBusy(true);
  setErrorMsg(null);
  try {
    await api.tick(n);
    await refreshWorldAndAgents();
  } catch (e) {
    setErrorMsg(`Tick failed: ${(e as Error).message}`);
  } finally {
    setBusy(false);
  }
}

export function play() {
  if (playing()) return;
  setPlaying(true);
  const loop = async () => {
    if (!playing()) return;
    await tick(1);
    if (playing()) {
      playTimer = window.setTimeout(loop, playSpeedMs());
    }
  };
  loop();
}

export function pause() {
  setPlaying(false);
  if (playTimer !== null) {
    clearTimeout(playTimer);
    playTimer = null;
  }
}

export async function reset() {
  pause();
  setSelectedAgent(null);
  try { await api.resetWorld(); } catch {}
  setWorldSnapshot(EMPTY_SNAP);
  setAgents([]);
  setTiles([]);
  setRecentEvents([]);
  setChapters([]);
}

export async function probeApi() {
  try {
    const h = await api.health();
    setApiOnline(h.ok);
    if (h.loaded) {
      await refreshWorldAndAgents();
    }
  } catch {
    setApiOnline(false);
  }
}
