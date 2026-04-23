/**
 * SocialPanel — first real consumer of @living-world/sim-core.
 *
 * Server returns a thin projection (`/api/social_graph`); this
 * component runs the metrics computation entirely client-side via the
 * TypeScript port, then renders the readout. No Python compute on the
 * hot path — proves the TS port is usable end-to-end and not just an
 * isomorphic re-implementation sitting unused.
 */
import {
  Component, For, Show, createMemo, createResource,
  onMount, onCleanup,
} from "solid-js";
import {
  computeSocialMetrics,
  type AgentForMetrics,
} from "@living-world/sim-core";
import { api } from "../api";

const PACK_DOT: Record<string, string> = {
  scp: "#d4a373", liaozhai: "#a87cd1", cthulhu: "#6ec4a0",
};

export const SocialPanel: Component = () => {
  // Pull the raw graph projection from the server. Refresh while open
  // so the panel keeps up with auto-play ticks.
  const [graph, { refetch }] = createResource(
    () => api.socialGraph().catch(() => ({ agents: [] as AgentForMetrics[] })),
  );

  let timer: number | undefined;
  onMount(() => {
    timer = window.setInterval(() => refetch(), 3000);
  });
  onCleanup(() => { if (timer) clearInterval(timer); });

  // Run the TypeScript sim-core computation here in the browser.
  // The whole point: this is the first real consumer of the port.
  const metrics = createMemo(() => {
    const g = graph();
    if (!g) return null;
    return computeSocialMetrics(g.agents, { minAbsAffinity: 30, topK: 8 });
  });

  // Group isolated by pack for slightly more useful display.
  const isolatedByPack = createMemo(() => {
    const m = metrics();
    const g = graph();
    if (!m || !g) return new Map<string, string[]>();
    const byId = new Map(g.agents.map((a) => [a.agentId, a.packId] as const));
    const out = new Map<string, string[]>();
    for (const id of m.isolated) {
      const pack = byId.get(id) ?? "?";
      const arr = out.get(pack) ?? [];
      arr.push(id);
      out.set(pack, arr);
    }
    return out;
  });

  return (
    <Show
      when={metrics()}
      fallback={<div class="muted">Loading social graph…</div>}
    >
      {(m) => (
        <div style="display:flex;flex-direction:column;gap:18px">
          {/* Headline numbers */}
          <div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(160px,1fr));gap:10px">
            <Stat label="agents (alive)" value={m().nAgents.toString()} />
            <Stat label="bonds (|affinity|≥30)" value={m().nEdges.toString()} />
            <Stat label="avg degree" value={m().avgDegree.toFixed(2)} />
            <Stat label="components" value={m().nComponents.toString()} />
            <Stat label="biggest component" value={m().biggestComponentSize.toString()} />
            <Stat label="isolated" value={m().isolated.length.toString()} />
            <Stat label="global clustering" value={m().clusteringGlobal.toFixed(3)} />
          </div>

          <div style="display:grid;grid-template-columns:1fr 1fr;gap:18px">
            {/* Top central */}
            <Card title="Most-connected agents">
              <Show
                when={m().topCentral.length > 0}
                fallback={<div class="muted">No bonds yet — try ticking the world a few days.</div>}
              >
                <table style="width:100%;border-collapse:collapse;font-size:12px">
                  <thead>
                    <tr style="text-align:left;color:#8a8f9c;font-size:10px;letter-spacing:0.08em;border-bottom:1px solid rgba(232,197,106,0.18)">
                      <th style="padding:5px 8px">AGENT</th>
                      <th style="padding:5px 8px;text-align:right">DEGREE</th>
                    </tr>
                  </thead>
                  <tbody>
                    <For each={m().topCentral}>
                      {([id, deg]) => (
                        <tr style="border-bottom:1px solid rgba(255,255,255,0.04)">
                          <td class="mono" style="padding:4px 8px;color:#cfd4dc">{id}</td>
                          <td class="mono gold" style="padding:4px 8px;text-align:right">{deg}</td>
                        </tr>
                      )}
                    </For>
                  </tbody>
                </table>
              </Show>
            </Card>

            {/* Components */}
            <Card title={`Connected components (${m().nComponents})`}>
              <Show
                when={m().components.length > 0}
                fallback={<div class="muted">No components — graph is empty.</div>}
              >
                <div style="display:flex;flex-direction:column;gap:6px;max-height:220px;overflow-y:auto">
                  <For each={m().components.slice(0, 8)}>
                    {(comp, i) => (
                      <div style="background:rgba(13,17,25,0.5);border:1px solid rgba(232,197,106,0.12);border-radius:3px;padding:6px 9px">
                        <div class="mono muted" style="font-size:10px;margin-bottom:3px">
                          #{i() + 1} · {comp.length} member{comp.length !== 1 ? "s" : ""}
                        </div>
                        <div style="font-size:11px;color:#cfd4dc;line-height:1.45">
                          {comp.slice(0, 12).join(", ")}
                          {comp.length > 12 ? ` … (+${comp.length - 12} more)` : ""}
                        </div>
                      </div>
                    )}
                  </For>
                </div>
              </Show>
            </Card>
          </div>

          {/* Isolated by pack */}
          <Show when={m().isolated.length > 0}>
            <Card title={`Isolated agents (${m().isolated.length})`}>
              <div style="display:flex;flex-direction:column;gap:6px">
                <For each={[...isolatedByPack().entries()]}>
                  {([pack, ids]) => (
                    <div style="display:flex;align-items:baseline;gap:8px;font-size:11.5px">
                      <span style={`width:7px;height:7px;border-radius:50%;background:${PACK_DOT[pack] ?? "#888"};flex-shrink:0`} />
                      <span class="mono muted" style="font-size:10px">{pack}</span>
                      <span class="mono" style="color:#cfd4dc;line-height:1.45">{ids.join(", ")}</span>
                    </div>
                  )}
                </For>
              </div>
            </Card>
          </Show>

          <div class="mono muted" style="font-size:9.5px;text-align:right">
            computed in-browser via @living-world/sim-core
          </div>
        </div>
      )}
    </Show>
  );
};

const Stat: Component<{ label: string; value: string }> = (p) => (
  <div style="background:rgba(13,17,25,0.6);border:1px solid rgba(232,197,106,0.18);border-radius:4px;padding:10px 12px">
    <div class="mono muted" style="font-size:9.5px;letter-spacing:0.08em;text-transform:uppercase;margin-bottom:4px">
      {p.label}
    </div>
    <div class="gold mono" style="font-size:18px;font-weight:600">{p.value}</div>
  </div>
);

const Card: Component<{ title: string; children: any }> = (p) => (
  <div style="background:rgba(13,17,25,0.5);border:1px solid rgba(232,197,106,0.18);border-radius:4px;padding:12px 14px">
    <div class="gold" style="font-family:Cinzel,serif;font-size:12px;letter-spacing:0.05em;margin-bottom:10px">
      {p.title}
    </div>
    {p.children}
  </div>
);
