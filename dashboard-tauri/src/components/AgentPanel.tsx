/**
 * AgentPanel — appears when an agent is selected.
 * Shows: identity / inner state / beliefs / weekly plan / recent events
 * the agent participated in.
 */
import { Component, For, Show, createResource, createMemo } from "solid-js";
import { selectedAgent, setSelectedAgent } from "../stores/worldStore";
import { api } from "../api";
import type { Agent } from "../types/api";

export const AgentPanel: Component = () => {
  const [resource] = createResource<Agent | null, string | null>(
    selectedAgent,
    async (id) => {
      if (!id) return null;
      try { return await api.agent(id); } catch { return null; }
    },
  );
  // Clear immediately when selectedAgent goes null — don't wait for resource
  const a = createMemo(() => {
    if (!selectedAgent()) return null;
    return resource() ?? null;
  });

  return (
    <Show when={a()}>
      <div style="flex:1 1 0;min-width:0;border-left:1px solid rgba(232,197,106,0.18);padding-left:18px;position:relative">
        <button
          onClick={() => setSelectedAgent(null)}
          title="Close"
          style="position:absolute;top:-2px;right:0;background:transparent;border:none;color:#8a8f9c;cursor:pointer;font-size:14px;padding:2px 6px;border-radius:2px"
        >
          ✕
        </button>
        <div style="display:flex;align-items:baseline;justify-content:space-between;margin-bottom:6px;padding-right:18px">
          <div class="gold" style="font-weight:600;font-size:14px">
            {a()!.isHf ? "★ " : ""}{a()!.name}
          </div>
          <div class="mono muted" style="font-size:10px">
            {a()!.pack} · {a()!.alignment} · {a()!.alive ? "alive" : "✝ deceased"}
          </div>
        </div>

        <Show when={a()!.goal}>
          <div style="font-size:11.5px;margin-bottom:8px">
            <span class="muted">goal: </span>
            <span style="color:#cfd4dc">{a()!.goal}</span>
          </div>
        </Show>

        <div style="display:grid;grid-template-columns:1fr 1fr;gap:14px">
          {/* LEFT: needs / emotions / attributes */}
          <div>
            <div class="muted" style="font-size:10px;letter-spacing:0.08em;margin-bottom:3px">INNER STATE</div>
            <Show when={a()!.needs}>
              <div class="mono" style="font-size:10.5px;color:#cfd4dc">
                hunger {Math.round(a()!.needs!.hunger || 0)} ·
                {" "}safety {Math.round(a()!.needs!.safety || 0)}
              </div>
            </Show>
            <Show when={a()!.emotions}>
              <div class="mono" style="font-size:10.5px;color:#cfd4dc">
                fear {Math.round(a()!.emotions!.fear || 0)} ·
                {" "}joy {Math.round(a()!.emotions!.joy || 0)} ·
                {" "}anger {Math.round(a()!.emotions!.anger || 0)}
              </div>
            </Show>
            <Show when={a()!.attributes && Object.keys(a()!.attributes!).length}>
              <div class="muted" style="font-size:10px;letter-spacing:0.08em;margin-top:8px;margin-bottom:3px">ATTRIBUTES</div>
              <div class="mono" style="font-size:10.5px;color:#cfd4dc;display:flex;flex-wrap:wrap;gap:4px 10px">
                <For each={Object.entries(a()!.attributes!).slice(0, 8)}>
                  {([k, v]) => <span><span class="muted">{k}</span> {v}</span>}
                </For>
              </div>
            </Show>
            <Show when={a()!.tags?.length}>
              <div class="muted" style="font-size:10px;letter-spacing:0.08em;margin-top:8px;margin-bottom:3px">TAGS</div>
              <div style="display:flex;flex-wrap:wrap;gap:4px">
                <For each={a()!.tags}>
                  {(t) => (
                    <span class="mono" style="font-size:9.5px;background:rgba(232,197,106,0.08);border:1px solid rgba(232,197,106,0.18);color:#cfd4dc;padding:1px 5px;border-radius:2px">
                      {t}
                    </span>
                  )}
                </For>
              </div>
            </Show>
          </div>

          {/* RIGHT: beliefs / plan / recent events */}
          <div>
            <div class="muted" style="font-size:10px;letter-spacing:0.08em;margin-bottom:3px">BELIEFS</div>
            <Show
              when={a()!.beliefs && Object.keys(a()!.beliefs!).length > 0}
              fallback={<div class="muted" style="font-size:10.5px">(none yet)</div>}
            >
              <div style="max-height:60px;overflow-y:auto;padding-right:4px">
                <For each={Object.entries(a()!.beliefs!).slice(0, 5)}>
                  {([topic, belief]) => (
                    <div style="margin-bottom:3px;font-size:10.5px;line-height:1.4">
                      <span class="mono gold" style="font-size:9.5px">[{topic}]</span>
                      {" "}<span style="color:#cfd4dc">{belief}</span>
                    </div>
                  )}
                </For>
              </div>
            </Show>

            <Show when={a()!.weeklyPlan && Object.keys(a()!.weeklyPlan!).length}>
              <div class="muted" style="font-size:10px;letter-spacing:0.08em;margin-top:8px;margin-bottom:3px">WEEKLY PLAN</div>
              <For each={Object.entries(a()!.weeklyPlan!).slice(0, 3)}>
                {([key, items]) => (
                  <div style="font-size:10.5px;color:#cfd4dc">
                    <span class="muted">{key}: </span>
                    {Array.isArray(items) ? items.slice(0, 3).join(" · ") : String(items)}
                  </div>
                )}
              </For>
            </Show>

            <Show when={a()!.recentEvents?.length}>
              <div class="muted" style="font-size:10px;letter-spacing:0.08em;margin-top:8px;margin-bottom:3px">
                RECENT EVENTS · {a()!.recentEvents!.length}
              </div>
              <div style="max-height:80px;overflow-y:auto;padding-right:4px">
                <For each={[...a()!.recentEvents!].reverse().slice(0, 6)}>
                  {(e) => (
                    <div style="font-size:10.5px;color:#cfd4dc;line-height:1.4;margin-bottom:3px">
                      <span class="mono muted" style="font-size:9.5px">d{String(e.tick).padStart(3, "0")}</span>
                      {" "}{e.narrative || `[${e.kind}]`}
                    </div>
                  )}
                </For>
              </div>
            </Show>
          </div>
        </div>
      </div>
    </Show>
  );
};
