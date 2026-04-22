/**
 * BottomCard — composable container.
 *
 * Top row: play controls + status.
 * Body:    WorldPanel (always) + AgentPanel (when an agent is selected).
 *
 * The split:
 *   - no agent: WorldPanel takes full width
 *   - agent:    WorldPanel left, AgentPanel right (50/50)
 */
import { Component, Show, For } from "solid-js";
import {
  worldSnapshot, selectedPacks, togglePack,
  bootstrap, tick, play, pause, reset,
  playing, playSpeedMs, setPlaySpeedMs,
  isLoaded, busy, errorMsg,
} from "../stores/worldStore";
import { WorldPanel } from "./WorldPanel";
import { AgentPanel } from "./AgentPanel";

export const BottomCard: Component = () => {
  const snap = worldSnapshot;

  return (
    <div class="bottom-card">
      <div class="action-row">
        <Show when={!isLoaded()}>
          <span class="muted" style="margin-right:8px">Worlds:</span>
          <For each={["scp", "liaozhai", "cthulhu"]}>
            {(pid) => (
              <label
                class={`pack-toggle ${selectedPacks().includes(pid) ? "active" : ""}`}
                onClick={() => togglePack(pid)}
              >
                {pid}
              </label>
            )}
          </For>
          <div class="divider-v" />
          <button
            class="btn primary"
            disabled={selectedPacks().length === 0 || busy()}
            onClick={() => bootstrap()}
          >
            {busy() ? "Starting…" : "▶ Simulate"}
          </button>
        </Show>

        <Show when={isLoaded()}>
          <Show
            when={playing()}
            fallback={
              <button class="btn primary" disabled={busy()} onClick={play}>
                {busy() ? "…" : "▶ Play"}
              </button>
            }
          >
            <button class="btn primary" onClick={pause}>⏸ Pause</button>
          </Show>

          <button class="btn" disabled={busy() || playing()} onClick={() => tick(1)}>+1</button>
          <button class="btn" disabled={busy() || playing()} onClick={() => tick(7)}>+7</button>
          <button class="btn" disabled={busy() || playing()} onClick={() => tick(30)}>+30</button>

          <div class="divider-v" />

          <label class="muted" style="font-size:11px;display:flex;align-items:center;gap:6px">
            speed
            <select
              class="mono"
              style="background:rgba(13,17,25,0.7);color:#cfd4dc;border:1px solid rgba(232,197,106,0.18);border-radius:3px;padding:3px 6px;font-size:11px"
              value={playSpeedMs()}
              onChange={(e) => setPlaySpeedMs(parseInt(e.currentTarget.value))}
            >
              <option value={3000}>slow (3s)</option>
              <option value={1500}>normal (1.5s)</option>
              <option value={500}>fast (0.5s)</option>
            </select>
          </label>

          <div class="divider-v" />

          <button class="btn danger" onClick={reset}>↻ Reset</button>

          <span class="muted mono" style="font-size:11.5px;margin-left:auto;display:flex;align-items:center;gap:10px">
            <span style={{
              color: playing() ? "#6ec46e" : "#e8c56a",
              "font-weight": "600",
            }}>
              {playing() ? "▶ playing" : "⏸ paused"}
            </span>
            <span>
              Day {snap().tick} · {snap().eventsTotal} events ·
              {" "}{snap().agentsAlive}/{snap().agentsTotal} alive ·
              {" "}{snap().deaths} dead
            </span>
          </span>
        </Show>

        <Show when={errorMsg()}>
          <span style="color:#d88080;margin-left:auto;font-size:12px">
            {errorMsg()}
          </span>
        </Show>
      </div>

      <div class="card-divider" />

      <div class="info-row" style="display:flex;gap:18px;align-items:flex-start">
        <Show
          when={isLoaded()}
          fallback={
            <div class="info-empty" style="flex:1">
              Pick worlds above and press Simulate to begin.
            </div>
          }
        >
          {/* WorldPanel takes flex:1 1 0 always; if AgentPanel renders
              (Show>when in AgentPanel.tsx), they share 50/50. Otherwise
              World takes full width naturally. */}
          <WorldPanel />
          <AgentPanel />
        </Show>
      </div>
    </div>
  );
};
