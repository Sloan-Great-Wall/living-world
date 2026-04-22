/**
 * SettingsModal — every tunable, editable. Auto-derived from
 * /api/settings (the pydantic Settings dump).
 *
 * Strategy: render every field with a type-appropriate input
 * (toggle for bool, number input for number, text input for string,
 * JSON textarea for object/array). Save patches the live settings
 * via POST /api/settings; most changes only take effect on next
 * Reset → Simulate.
 */
import { Component, For, Show, createResource, createSignal } from "solid-js";
import { api } from "../api";

const SECTION_LABELS: Record<string, string> = {
  llm: "LLM (tier 2/3 + per-module overrides + feature flags)",
  budget: "Token Budget",
  importance: "Importance Routing",
  historical_figures: "Historical Figure promotion / demotion",
  storyteller: "Storyteller",
  simulation: "Simulation Defaults",
  memory: "Memory + Reflection",
  display: "Display / locale",
  persistence: "Persistence (snapshots)",
  dashboard: "Dashboard (legacy Streamlit)",
};

type Patch = Record<string, Record<string, unknown>>;

const FieldInput: Component<{
  section: string;
  fieldKey: string;
  value: unknown;
  onChange: (v: unknown) => void;
}> = (p) => {
  if (typeof p.value === "boolean") {
    return (
      <label style="display:inline-flex;align-items:center;gap:6px;cursor:pointer">
        <input
          type="checkbox"
          checked={p.value}
          onChange={(e) => p.onChange(e.currentTarget.checked)}
          style="accent-color:#e8c56a"
        />
        <span class="mono" style={`color:${p.value ? "#6ec46e" : "#8a8f9c"};font-size:11px`}>
          {p.value ? "on" : "off"}
        </span>
      </label>
    );
  }
  if (typeof p.value === "number") {
    return (
      <input
        type="number"
        step="any"
        value={p.value}
        onChange={(e) => p.onChange(parseFloat(e.currentTarget.value))}
        style="background:rgba(13,17,25,0.7);border:1px solid rgba(232,197,106,0.18);color:#e8c56a;padding:3px 7px;border-radius:3px;font-family:'JetBrains Mono',monospace;font-size:11px;width:130px"
      />
    );
  }
  if (typeof p.value === "string") {
    return (
      <input
        type="text"
        value={p.value}
        onChange={(e) => p.onChange(e.currentTarget.value)}
        style="background:rgba(13,17,25,0.7);border:1px solid rgba(232,197,106,0.18);color:#cfd4dc;padding:3px 7px;border-radius:3px;font-family:'JetBrains Mono',monospace;font-size:11px;min-width:240px"
      />
    );
  }
  if (p.value === null || p.value === undefined) {
    return (
      <input
        type="text"
        placeholder="(null)"
        onChange={(e) => p.onChange(e.currentTarget.value || null)}
        style="background:rgba(13,17,25,0.7);border:1px solid rgba(232,197,106,0.18);color:#cfd4dc;padding:3px 7px;border-radius:3px;font-family:'JetBrains Mono',monospace;font-size:11px;min-width:240px"
      />
    );
  }
  // arrays / objects → JSON textarea
  return (
    <textarea
      value={JSON.stringify(p.value, null, 2)}
      onChange={(e) => {
        try { p.onChange(JSON.parse(e.currentTarget.value)); } catch {}
      }}
      style="background:rgba(13,17,25,0.7);border:1px solid rgba(232,197,106,0.18);color:#cfd4dc;padding:5px 7px;border-radius:3px;font-family:'JetBrains Mono',monospace;font-size:10.5px;width:100%;min-height:50px;resize:vertical"
    />
  );
};

export const SettingsModal: Component<{ onClose: () => void }> = (props) => {
  const [settings, { refetch }] = createResource(() => api.settings().catch(() => null));
  const [patch, setPatch] = createSignal<Patch>({});
  const [savingMsg, setSavingMsg] = createSignal<string | null>(null);

  const updateField = (section: string, key: string, val: unknown) => {
    setPatch((p) => ({
      ...p,
      [section]: { ...(p[section] ?? {}), [key]: val },
    }));
  };

  const merged = (section: string, key: string): unknown => {
    const overlay = patch()[section]?.[key];
    if (overlay !== undefined) return overlay;
    const base = (settings()?.[section] as Record<string, unknown> | undefined)?.[key];
    return base;
  };

  const dirtyCount = () =>
    Object.values(patch()).reduce((acc, sec) => acc + Object.keys(sec).length, 0);

  const save = async () => {
    setSavingMsg("Saving…");
    try {
      await api.saveSettings(patch() as unknown as Record<string, unknown>);
      setPatch({});
      setSavingMsg("Saved · Reset & Simulate to apply most changes");
      refetch();
      setTimeout(() => setSavingMsg(null), 4000);
    } catch (e) {
      setSavingMsg(`Save failed: ${(e as Error).message}`);
    }
  };

  return (
    <div class="modal-backdrop" onClick={props.onClose}>
      <div class="modal" onClick={(e) => e.stopPropagation()}
           style="width:min(960px,100%);height:min(820px,90vh)">
        <header class="modal-header">
          <h2>⚙ Settings</h2>
          <div style="display:flex;gap:10px;align-items:center">
            <Show when={savingMsg()}>
              <span class="mono muted" style="font-size:11px">{savingMsg()}</span>
            </Show>
            <button
              class="btn primary"
              disabled={dirtyCount() === 0}
              onClick={save}
              style="padding:5px 12px;font-size:12px"
            >
              Save{dirtyCount() ? ` (${dirtyCount()})` : ""}
            </button>
            <button class="modal-close" onClick={props.onClose}>✕</button>
          </div>
        </header>

        <div class="modal-body">
          <p class="muted" style="font-size:11.5px;margin-top:0">
            Every value from <span class="mono">settings.yaml</span>. Edit
            inline; click <b>Save</b> to persist. Most changes only take
            effect on next ↻ Reset → ▶ Simulate.
          </p>

          <Show when={settings()} fallback={<div class="muted">Loading settings…</div>}>
            <For each={Object.entries(settings()!)}>
              {([section, fields]) => (
                <Show
                  when={typeof fields === "object" && fields !== null && !Array.isArray(fields)}
                  fallback={
                    <div style="padding:6px 0">
                      <span class="mono muted">{section}</span>
                    </div>
                  }
                >
                  <section style="margin:18px 0 4px 0">
                    <h3 class="gold" style="font-family:Cinzel,serif;font-size:13px;letter-spacing:0.04em;margin:0 0 6px 0;padding-bottom:4px;border-bottom:1px solid rgba(232,197,106,0.18)">
                      {SECTION_LABELS[section] ?? section}
                    </h3>
                    <table style="width:100%;border-collapse:collapse;font-size:11.5px">
                      <tbody>
                        <For each={Object.entries(fields as Record<string, unknown>)}>
                          {([key]) => (
                            <tr style="border-bottom:1px solid rgba(255,255,255,0.04)">
                              <td class="mono muted" style="padding:5px 8px;width:38%;vertical-align:top">
                                {key}
                              </td>
                              <td style="padding:5px 8px">
                                <FieldInput
                                  section={section}
                                  fieldKey={key}
                                  value={merged(section, key)}
                                  onChange={(v) => updateField(section, key, v)}
                                />
                              </td>
                            </tr>
                          )}
                        </For>
                      </tbody>
                    </table>
                  </section>
                </Show>
              )}
            </For>
          </Show>
        </div>
      </div>
    </div>
  );
};
