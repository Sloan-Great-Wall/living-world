/**
 * LibraryModal — codex of authored content + live chronicle.
 *
 * Tabs:
 *   - Characters: every persona authored in the loaded packs (not just spawned)
 *   - Stories:    every event template (yaml + LLM-promoted)
 *   - Tiles:      every location
 *   - Chronicle:  chapters written by the Chronicler agent
 */
import {
  Component, For, Show, createResource, createSignal,
  onMount, onCleanup,
} from "solid-js";
import { api } from "../api";
import { chapters } from "../stores/worldStore";

const PACK_DOT: Record<string, string> = {
  scp: "#d4a373", liaozhai: "#a87cd1", cthulhu: "#6ec4a0",
};

type Tab = "characters" | "stories" | "tiles" | "chronicle";

export const LibraryModal: Component<{ onClose: () => void }> = (props) => {
  const [tab, setTab] = createSignal<Tab>("characters");

  const [personas, { refetch: refPersonas }] = createResource(() => api.personas().catch(() => []));
  const [templates, { refetch: refTemplates }] = createResource(() => api.templates().catch(() => []));
  const [tiles, { refetch: refTiles }] = createResource(() => api.tiles().catch(() => []));

  // Live refresh while open: templates can grow (LLM-promoted) and tiles
  // can change if cross-pack bridge fires. Personas rarely change but no harm.
  let timer: number | undefined;
  onMount(() => {
    timer = window.setInterval(() => {
      refPersonas(); refTemplates(); refTiles();
    }, 3000);
  });
  onCleanup(() => { if (timer) clearInterval(timer); });

  const tabBtn = (id: Tab, label: string) => (
    <button
      onClick={() => setTab(id)}
      style={{
        background: tab() === id ? "rgba(232,197,106,0.12)" : "transparent",
        border: tab() === id ? "1px solid #e8c56a" : "1px solid rgba(232,197,106,0.18)",
        color: tab() === id ? "#f2f4f8" : "#cfd4dc",
        padding: "6px 14px", "border-radius": "3px", cursor: "pointer",
        "font-size": "12px",
      }}
    >
      {label}
    </button>
  );

  return (
    <div class="modal-backdrop" onClick={props.onClose}>
      <div class="modal" onClick={(e) => e.stopPropagation()}
           style="width:min(1100px,100%);height:min(800px,90vh)">
        <header class="modal-header">
          <h2>📚 Story Library</h2>
          <button class="modal-close" onClick={props.onClose}>✕</button>
        </header>

        <div style="padding:14px 22px 8px 22px;display:flex;gap:8px">
          {tabBtn("characters", `Characters (${personas()?.length ?? "…"})`)}
          {tabBtn("stories",    `Stories (${templates()?.length ?? "…"})`)}
          {tabBtn("tiles",      `Tiles (${tiles()?.length ?? "…"})`)}
          {tabBtn("chronicle",  `Chronicle (${chapters().length})`)}
        </div>

        <div class="modal-body">
          {/* Characters */}
          <Show when={tab() === "characters"}>
            <Show when={personas()} fallback={<div class="muted">Loading…</div>}>
              <div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(280px,1fr));gap:12px">
                <For each={personas()}>
                  {(p) => (
                    <div style="background:rgba(13,17,25,0.6);border:1px solid rgba(232,197,106,0.18);border-radius:4px;padding:12px">
                      <div style="display:flex;align-items:baseline;justify-content:space-between;gap:8px;margin-bottom:4px">
                        <div class="gold" style="font-weight:600;font-size:13px">
                          {p.isHf ? "★ " : ""}{p.name}
                        </div>
                        <span style={`width:8px;height:8px;border-radius:50%;background:${PACK_DOT[p.pack] ?? "#888"};flex-shrink:0`} />
                      </div>
                      <div class="mono muted" style="font-size:10px;margin-bottom:6px">
                        {p.pack} · {p.alignment}
                      </div>
                      <div style="font-size:11.5px;color:#cfd4dc;line-height:1.5;max-height:80px;overflow-y:auto">
                        {p.persona || "(no persona text)"}
                      </div>
                      <Show when={p.tags?.length}>
                        <div style="display:flex;flex-wrap:wrap;gap:3px;margin-top:8px">
                          <For each={p.tags.slice(0, 6)}>
                            {(t) => (
                              <span class="mono" style="font-size:9.5px;background:rgba(232,197,106,0.08);border:1px solid rgba(232,197,106,0.18);color:#cfd4dc;padding:1px 5px;border-radius:2px">{t}</span>
                            )}
                          </For>
                        </div>
                      </Show>
                    </div>
                  )}
                </For>
              </div>
            </Show>
          </Show>

          {/* Stories — event templates */}
          <Show when={tab() === "stories"}>
            <Show when={templates()} fallback={<div class="muted">Loading…</div>}>
              <table style="width:100%;border-collapse:collapse;font-size:12px">
                <thead>
                  <tr style="text-align:left;color:#8a8f9c;font-size:10px;letter-spacing:0.08em;border-bottom:1px solid rgba(232,197,106,0.18)">
                    <th style="padding:6px 8px">PACK</th>
                    <th style="padding:6px 8px">EVENT KIND</th>
                    <th style="padding:6px 8px">DESCRIPTION</th>
                    <th style="padding:6px 8px;text-align:right">IMP</th>
                    <th style="padding:6px 8px">SOURCE</th>
                  </tr>
                </thead>
                <tbody>
                  <For each={templates()}>
                    {(t) => (
                      <tr style="border-bottom:1px solid rgba(255,255,255,0.04)">
                        <td style="padding:5px 8px">
                          <span style={`display:inline-block;width:7px;height:7px;border-radius:50%;background:${PACK_DOT[t.pack] ?? "#888"};margin-right:5px`} />
                          <span class="mono" style="font-size:10.5px;color:#cfd4dc">{t.pack}</span>
                        </td>
                        <td style="padding:5px 8px" class="gold mono">{t.eventKind}</td>
                        <td style="padding:5px 8px;color:#cfd4dc;max-width:480px;overflow:hidden;text-overflow:ellipsis">{t.description}</td>
                        <td style="padding:5px 8px;text-align:right" class="mono muted">{t.baseImportance.toFixed(2)}</td>
                        <td style="padding:5px 8px" class="mono muted">{t.source}</td>
                      </tr>
                    )}
                  </For>
                </tbody>
              </table>
            </Show>
          </Show>

          {/* Tiles */}
          <Show when={tab() === "tiles"}>
            <Show when={tiles()} fallback={<div class="muted">Loading…</div>}>
              <div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(220px,1fr));gap:10px">
                <For each={tiles()}>
                  {(t) => (
                    <div style="background:rgba(13,17,25,0.6);border:1px solid rgba(232,197,106,0.18);border-radius:4px;padding:10px">
                      <div style="display:flex;align-items:center;gap:6px;margin-bottom:3px">
                        <span style={`width:8px;height:8px;border-radius:50%;background:${PACK_DOT[t.pack] ?? "#888"}`} />
                        <span class="gold" style="font-weight:600;font-size:12px">{t.name}</span>
                      </div>
                      <div class="mono muted" style="font-size:10px">{t.pack} · {t.type}</div>
                      <div class="mono" style="font-size:9.5px;color:#5a6070;margin-top:4px">{t.id}</div>
                    </div>
                  )}
                </For>
              </div>
            </Show>
          </Show>

          {/* Chronicle */}
          <Show when={tab() === "chronicle"}>
            <Show
              when={chapters().length > 0}
              fallback={<div class="muted">No chapters yet — chronicler runs every N ticks once enough events accumulate.</div>}
            >
              <For each={[...chapters()].reverse()}>
                {(ch) => (
                  <article style="margin-bottom:18px;padding-bottom:14px;border-bottom:1px solid rgba(232,197,106,0.18)">
                    <div style="display:flex;align-items:baseline;justify-content:space-between;margin-bottom:6px">
                      <h3 class="gold" style="margin:0;font-family:Cinzel,serif;font-size:15px">
                        {ch.title}
                      </h3>
                      <span class="mono muted" style="font-size:10.5px">
                        Day {ch.tick} · {ch.pack_id}
                      </span>
                    </div>
                    <div style="font-size:12.5px;color:#cfd4dc;line-height:1.65">
                      {ch.body}
                    </div>
                  </article>
                )}
              </For>
            </Show>
          </Show>
        </div>
      </div>
    </div>
  );
};
