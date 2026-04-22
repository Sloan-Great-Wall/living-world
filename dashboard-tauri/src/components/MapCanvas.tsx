/**
 * MapCanvas — fullscreen canvas showing pack clusters, tile nodes,
 * and agents that MOVE when the sim ticks.
 *
 * Layout model:
 *   pack cluster center = angular position around world center
 *   tile position       = deterministic offset from its pack center
 *                         (stable per run — hash(tile_id))
 *   agent position      = its current tile's position + small jitter
 *                         (jitter stable per agent so siblings at same
 *                          tile don't stack; jitter is NOT recomputed
 *                          on tick so the dot only jumps if tile changes)
 *
 * Animation: when an agent's tile changes between frames, its dot
 * interpolates from the old position to the new over ~400ms. This is
 * what the user reads as "agent movement".
 */
import { Component, onMount, onCleanup } from "solid-js";
import {
  agents, tiles, worldSnapshot, isLoaded,
  selectedAgent, setSelectedAgent,
} from "../stores/worldStore";
import type { Agent, Tile } from "../types/api";

const PACK_COLORS: Record<string, { accent: string; text: string }> = {
  scp:      { accent: "#d4a373", text: "#f0d9b8" },
  liaozhai: { accent: "#a87cd1", text: "#e0c8f0" },
  cthulhu:  { accent: "#6ec4a0", text: "#c0f0d8" },
};
const DEFAULT_COLOR = { accent: "#e8c56a", text: "#f2f4f8" };

type Vec2 = { x: number; y: number };

// Animated agent position (screen coords). live = target; drawn = current.
type AgentAnim = { drawn: Vec2; target: Vec2; tile: string };

function simpleHash(s: string): number {
  let h = 2166136261;
  for (let i = 0; i < s.length; i++) {
    h ^= s.charCodeAt(i);
    h = Math.imul(h, 16777619);
  }
  return Math.abs(h);
}

export const MapCanvas: Component = () => {
  let canvas: HTMLCanvasElement | undefined;
  let raf = 0;
  let dpr = 1;
  let mouseX = -1;
  let mouseY = -1;
  const agentScreen = new Map<string, { sx: number; sy: number }>();
  const anim = new Map<string, AgentAnim>();
  let lastTime = performance.now();

  const resize = () => {
    if (!canvas) return;
    dpr = window.devicePixelRatio || 1;
    canvas.width = window.innerWidth * dpr;
    canvas.height = window.innerHeight * dpr;
    canvas.style.width = `${window.innerWidth}px`;
    canvas.style.height = `${window.innerHeight}px`;
  };

  // ── Pack cluster centers (angular layout) ──
  const packCenter = (_pid: string, idx: number, total: number): Vec2 => {
    const cx = (canvas?.width ?? 0) / 2;
    const cy = (canvas?.height ?? 0) / 2;
    const r = Math.min(canvas?.width ?? 1, canvas?.height ?? 1) * 0.27;
    const angle = (idx / total) * Math.PI * 2 - Math.PI / 2;
    return { x: cx + Math.cos(angle) * r, y: cy + Math.sin(angle) * r };
  };

  // ── Tile position: cluster-center + deterministic offset ──
  const tilePosition = (
    tile: Tile, packCenters: Record<string, Vec2>,
  ): Vec2 => {
    const center = packCenters[tile.pack] ?? {
      x: (canvas?.width ?? 0) / 2,
      y: (canvas?.height ?? 0) / 2,
    };
    const h = simpleHash(tile.id);
    const theta = ((h % 1000) / 1000) * Math.PI * 2;
    const ring = 85 * dpr + ((h >> 10) % 100) / 100 * 45 * dpr;
    return { x: center.x + Math.cos(theta) * ring, y: center.y + Math.sin(theta) * ring };
  };

  // ── Agent target position: its tile + per-agent jitter ──
  const agentTarget = (
    ag: Agent, tilesById: Record<string, Tile>,
    packCenters: Record<string, Vec2>,
  ): Vec2 => {
    const tile = tilesById[ag.tile];
    const base = tile
      ? tilePosition(tile, packCenters)
      : (packCenters[ag.pack] ?? { x: 0, y: 0 });
    const h = simpleHash(ag.id);
    const jx = (((h >> 2) % 200) - 100) / 100 * 14 * dpr;
    const jy = (((h >> 10) % 200) - 100) / 100 * 14 * dpr;
    return { x: base.x + jx, y: base.y + jy };
  };

  const draw = (t: number) => {
    if (!canvas) return;
    const dt = Math.min(0.1, (t - lastTime) / 1000);
    lastTime = t;

    const ctx = canvas.getContext("2d")!;
    const w = canvas.width;
    const h = canvas.height;

    ctx.fillStyle = "#07090e";
    ctx.fillRect(0, 0, w, h);

    // ── Ambient grid ──
    ctx.fillStyle = "rgba(232, 197, 106, 0.04)";
    const step = 48 * dpr;
    for (let x = (t / 80) % step; x < w; x += step) {
      for (let y = (t / 130) % step; y < h; y += step) {
        ctx.beginPath();
        ctx.arc(x, y, 0.8 * dpr, 0, Math.PI * 2);
        ctx.fill();
      }
    }

    // ── Pack centers ──
    const packsLoaded = worldSnapshot().packs.length
      ? worldSnapshot().packs
      : ["scp", "liaozhai", "cthulhu"];
    const packCenters: Record<string, Vec2> = {};
    packsLoaded.forEach((p, i) => {
      packCenters[p] = packCenter(p, i, packsLoaded.length);
    });

    // ── Tile index ──
    const tilesById: Record<string, Tile> = {};
    for (const t of tiles()) tilesById[t.id] = t;

    // ── Pack halos + labels ──
    packsLoaded.forEach((pid, idx) => {
      const color = PACK_COLORS[pid] || DEFAULT_COLOR;
      const pulse = 1 + Math.sin(t / 900 + idx) * 0.06;
      const c = packCenters[pid];
      const grad = ctx.createRadialGradient(c.x, c.y, 0, c.x, c.y, 180 * dpr * pulse);
      grad.addColorStop(0, `${color.accent}26`);
      grad.addColorStop(1, `${color.accent}00`);
      ctx.fillStyle = grad;
      ctx.fillRect(c.x - 180 * dpr, c.y - 180 * dpr, 360 * dpr, 360 * dpr);

      ctx.fillStyle = color.text;
      ctx.font = `${13 * dpr}px Cinzel, serif`;
      ctx.textAlign = "center";
      ctx.fillText(pid.toUpperCase(), c.x, c.y - 160 * dpr);
    });

    // ── Tile nodes (small tick marks so user sees the graph) ──
    for (const t of tiles()) {
      const p = tilePosition(t, packCenters);
      ctx.beginPath();
      ctx.arc(p.x, p.y, 1.8 * dpr, 0, Math.PI * 2);
      ctx.fillStyle = "rgba(232, 197, 106, 0.28)";
      ctx.fill();
    }

    // ── Agent anim update + render ──
    agentScreen.clear();
    const agentList: Agent[] = agents();

    // Ensure every current agent has an anim slot; update targets.
    for (const ag of agentList) {
      const target = agentTarget(ag, tilesById, packCenters);
      const existing = anim.get(ag.id);
      if (!existing) {
        anim.set(ag.id, { drawn: { ...target }, target, tile: ag.tile });
      } else {
        if (existing.tile !== ag.tile) {
          existing.target = target;
          existing.tile = ag.tile;
        } else {
          // Tile unchanged but screen may have resized → nudge target
          existing.target = target;
        }
      }
    }

    // Remove anims for agents that no longer exist (unlikely but safe)
    const alive = new Set(agentList.map((a) => a.id));
    for (const id of anim.keys()) if (!alive.has(id)) anim.delete(id);

    // Interpolate drawn → target (exp ease, ~400ms half-life)
    const easeK = 1 - Math.pow(0.001, dt * 3); // ~smooth approach
    for (const a of anim.values()) {
      a.drawn.x += (a.target.x - a.drawn.x) * easeK;
      a.drawn.y += (a.target.y - a.drawn.y) * easeK;
    }

    // Draw agents
    for (const ag of agentList) {
      const a = anim.get(ag.id)!;
      const color = PACK_COLORS[ag.pack] || DEFAULT_COLOR;
      agentScreen.set(ag.id, { sx: a.drawn.x, sy: a.drawn.y });

      const selected = selectedAgent() === ag.id;
      const hovered = nearestAgentId(mouseX * dpr, mouseY * dpr) === ag.id;

      // Halo
      if (ag.isHf || selected || hovered) {
        const haloR = selected ? 18 * dpr : hovered ? 13 * dpr : 10 * dpr;
        const hg = ctx.createRadialGradient(a.drawn.x, a.drawn.y, 0, a.drawn.x, a.drawn.y, haloR);
        hg.addColorStop(0, `${color.accent}55`);
        hg.addColorStop(1, `${color.accent}00`);
        ctx.fillStyle = hg;
        ctx.fillRect(a.drawn.x - haloR, a.drawn.y - haloR, haloR * 2, haloR * 2);
      }

      // Core dot
      ctx.beginPath();
      const size = (ag.isHf ? 4.8 : 3.2) * dpr;
      ctx.arc(a.drawn.x, a.drawn.y, size, 0, Math.PI * 2);
      ctx.fillStyle = ag.alive ? color.accent : "rgba(120, 120, 130, 0.5)";
      ctx.fill();

      // Selection ring
      if (selected) {
        ctx.beginPath();
        ctx.arc(a.drawn.x, a.drawn.y, size + 3 * dpr, 0, Math.PI * 2);
        ctx.strokeStyle = "#e8c56a";
        ctx.lineWidth = 1.5 * dpr;
        ctx.stroke();
      }
    }

    // Hovered label on top
    const hovId = nearestAgentId(mouseX * dpr, mouseY * dpr);
    if (hovId) {
      const ag = agentList.find((x) => x.id === hovId);
      const pos = agentScreen.get(hovId);
      if (ag && pos) {
        ctx.fillStyle = "rgba(0, 0, 0, 0.78)";
        ctx.font = `${12 * dpr}px Inter, sans-serif`;
        ctx.textAlign = "left";
        const label = `${ag.isHf ? "★ " : ""}${ag.name}`;
        const metrics = ctx.measureText(label);
        const pad = 5 * dpr;
        ctx.fillRect(pos.sx + 10 * dpr, pos.sy - 9 * dpr, metrics.width + pad * 2, 20 * dpr);
        ctx.fillStyle = "#f2f4f8";
        ctx.fillText(label, pos.sx + 10 * dpr + pad, pos.sy + 5 * dpr);
      }
    }

    // Empty state
    if (!isLoaded()) {
      const cx = w / 2, cy = h / 2;
      ctx.fillStyle = "rgba(232, 197, 106, 0.85)";
      ctx.font = `${24 * dpr}px Cinzel, serif`;
      ctx.textAlign = "center";
      ctx.fillText("A world waits.", cx, cy - 20 * dpr);
      ctx.fillStyle = "rgba(207, 212, 220, 0.6)";
      ctx.font = `${13 * dpr}px Inter, sans-serif`;
      ctx.fillText("Pick worlds below, then press Simulate.", cx, cy + 14 * dpr);
    }

    raf = requestAnimationFrame(draw);
  };

  function nearestAgentId(px: number, py: number): string | null {
    let bestId: string | null = null;
    let bestD2 = Infinity;
    agentScreen.forEach(({ sx, sy }, id) => {
      const d2 = (sx - px) ** 2 + (sy - py) ** 2;
      if (d2 < bestD2) { bestD2 = d2; bestId = id; }
    });
    if (bestId && bestD2 < (14 * dpr) ** 2) return bestId;
    return null;
  }

  const handleClick = (ev: MouseEvent) => {
    const rect = canvas!.getBoundingClientRect();
    const px = (ev.clientX - rect.left) * dpr;
    const py = (ev.clientY - rect.top) * dpr;
    const id = nearestAgentId(px, py);
    setSelectedAgent(id);
  };
  const handleMove = (ev: MouseEvent) => {
    const rect = canvas!.getBoundingClientRect();
    mouseX = ev.clientX - rect.left;
    mouseY = ev.clientY - rect.top;
  };
  const handleLeave = () => { mouseX = -1; mouseY = -1; };

  onMount(() => {
    resize();
    window.addEventListener("resize", resize);
    canvas?.addEventListener("click", handleClick);
    canvas?.addEventListener("mousemove", handleMove);
    canvas?.addEventListener("mouseleave", handleLeave);
    raf = requestAnimationFrame(draw);
  });

  onCleanup(() => {
    cancelAnimationFrame(raf);
    window.removeEventListener("resize", resize);
  });

  return <canvas class="map-canvas" ref={(el) => (canvas = el)} />;
};
