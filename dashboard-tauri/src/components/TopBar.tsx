/**
 * TopBar — single transparent horizontal strip floating over the map.
 * Brand on the left, live world stats inline, two buttons on the right.
 */
import { Component, For, Show, createMemo } from "solid-js";
import { diversitySummary } from "@living-world/sim-core";
import { worldSnapshot, recentEvents, apiOnline } from "../stores/worldStore";

type StatPillProps = { label: string; value: string | number };
const StatPill: Component<StatPillProps> = (p) => (
  <div class="stat-pill" title={`${p.label}: ${p.value}`}>
    <span class="stat-label">{p.label}</span>
    <span class="stat-val">{p.value}</span>
  </div>
);

type Props = {
  onOpenLibrary: () => void;
  onOpenSettings: () => void;
};

export const TopBar: Component<Props> = (props) => {
  const snap = worldSnapshot;
  // Diversity used to come from the server in WorldSnapshot.diversity.
  // After the 2026-04-26 simplification audit, we compute it client-side
  // from the recent-events list — fewer fields on the wire, same UX.
  const diversity = createMemo(() =>
    diversitySummary(
      recentEvents().map((e) => ({
        eventId: e.id,
        tick: e.tick,
        packId: e.pack,
        tileId: e.tile,
        eventKind: e.kind,
        outcome: e.outcome,
        importance: e.importance,
        tierUsed: e.tier,
        isEmergent: e.isEmergent,
        participants: e.participants,
      })),
    ),
  );

  return (
    <header class="topbar">
      <div class="topbar-left">
        <div class="brand">
          <span class="brand-mark">⌬</span>
          <span class="brand-text">Living World</span>
          <span class="brand-tag">α</span>
        </div>

        <div class="stats">
          <For each={[
            { label: "Day",      value: snap().tick },
            { label: "Events",   value: snap().eventsTotal },
            { label: "Alive",    value: snap().agentsAlive },
            { label: "Deaths",   value: snap().deaths },
            { label: "Chapters", value: snap().chapters },
            { label: "T2",       value: snap().modelTier2 },
            { label: "T3",       value: snap().modelTier3 },
          ]}>
            {(s) => <StatPill label={s.label} value={s.value as any} />}
          </For>

          <div class="stat-pill" title={apiOnline() ? "API connected" : "API offline"}>
            <span class="stat-label">API</span>
            <span class="stat-val" style={{ color: apiOnline() ? "#6ec46e" : "#c85050" }}>
              {apiOnline() ? "●" : "○"}
            </span>
          </div>

          <Show when={diversity().total > 0}>
            <div class="stat-pill" title="Top event kind + share (computed client-side)">
              <span class="stat-label">Top</span>
              <span class="stat-val">
                {diversity().top_kind ?? "—"} ({diversity().top_pct.toFixed(1)}%)
              </span>
            </div>
          </Show>
        </div>
      </div>

      <div class="topbar-right">
        <button class="topbar-btn" onClick={props.onOpenLibrary} title="Story Library">
          <span>📚</span><span>Library</span>
        </button>
        <button class="topbar-btn" onClick={props.onOpenSettings} title="Settings">
          <span>⚙</span><span>Settings</span>
        </button>
      </div>
    </header>
  );
};
