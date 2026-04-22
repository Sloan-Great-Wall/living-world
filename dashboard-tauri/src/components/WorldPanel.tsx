/**
 * WorldPanel — always-on event log + recent chapter (世界视角).
 *
 * Shown in the bottom card whether or not an agent is selected. Pairs
 * with AgentPanel when an agent IS selected (side-by-side composition).
 */
import { Component, For, Show } from "solid-js";
import { recentEvents, chapters, worldSnapshot } from "../stores/worldStore";
import type { WorldEvent } from "../types/api";

const PACK_DOT: Record<string, string> = {
  scp: "#d4a373", liaozhai: "#a87cd1", cthulhu: "#6ec4a0",
};

const tierGlyph = (tier: number) =>
  tier >= 3 ? "●●●" : tier === 2 ? "●●" : "●";
const tierColor = (tier: number) =>
  tier >= 3 ? "#b091d1" : tier === 2 ? "#d4a373" : "#5a6270";

const EventRow: Component<{ e: WorldEvent }> = (p) => (
  <div style="display:flex;gap:8px;align-items:flex-start;padding:5px 0;border-bottom:1px solid rgba(255,255,255,0.04)">
    <span
      class="mono"
      style={`color:${tierColor(p.e.tier)};font-size:9.5px;width:24px;flex-shrink:0;padding-top:2px`}
      title={`tier ${p.e.tier} · importance ${p.e.importance.toFixed(2)}`}
    >
      {tierGlyph(p.e.tier)}
    </span>
    <span
      class="mono muted"
      style="font-size:10px;width:40px;flex-shrink:0;padding-top:2px"
    >
      d{String(p.e.tick).padStart(3, "0")}
    </span>
    <span
      style={`width:8px;height:8px;border-radius:50%;background:${PACK_DOT[p.e.pack] ?? "#888"};flex-shrink:0;margin-top:6px`}
      title={p.e.pack}
    />
    <div style="flex:1;min-width:0">
      <div style="font-size:11.5px;color:#cfd4dc;line-height:1.45">
        {p.e.narrative || `[${p.e.kind}]`}
      </div>
      <div class="mono muted" style="font-size:10px;margin-top:1px">
        {p.e.kind} · {p.e.outcome}
        {p.e.isEmergent ? " · emergent" : ""}
      </div>
    </div>
  </div>
);

export const WorldPanel: Component = () => {
  const events = () => {
    // Newest first, capped to 50 for the scroll list
    const all = recentEvents();
    return [...all].sort((a, b) => b.tick - a.tick).slice(0, 50);
  };
  const lastChapter = () => {
    const cs = chapters();
    return cs.length ? cs[cs.length - 1] : null;
  };

  return (
    <div style="flex:1 1 0;min-width:0">
      <div style="display:flex;align-items:baseline;justify-content:space-between;margin-bottom:6px">
        <div class="muted" style="font-size:10.5px;letter-spacing:0.08em">
          WORLD · {worldSnapshot().eventsTotal} events · {worldSnapshot().chapters} chapters
        </div>
        <Show when={lastChapter()}>
          {(ch) => (
            <div
              class="gold"
              style="font-size:10.5px;font-style:italic;max-width:280px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap"
              title={ch().body}
            >
              📜 {ch().title}
            </div>
          )}
        </Show>
      </div>
      <div style="max-height:170px;overflow-y:auto;padding-right:6px">
        <Show
          when={events().length > 0}
          fallback={
            <div class="muted" style="font-size:11.5px;padding:8px 0">
              No events yet — press <span class="gold">▶ Play</span> or
              <span class="gold"> +1</span>. The first events appear within
              1-2 ticks.
            </div>
          }
        >
          <For each={events()}>{(e) => <EventRow e={e} />}</For>
        </Show>
      </div>
    </div>
  );
};
