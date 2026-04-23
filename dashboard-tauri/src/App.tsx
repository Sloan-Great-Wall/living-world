/**
 * Living World — Game-aesthetic dashboard (Tauri + Solid + TS).
 *
 * Three-zone layout:
 *   - TopBar:     single transparent strip, brand + live stats + buttons
 *   - MapCanvas:  fullscreen canvas with pack clusters + agent dots
 *   - BottomCard: floating blur panel with play controls + agent inspect
 *
 * State all lives in stores/worldStore.ts. Modals use local signals here.
 */
import { createSignal, onMount, Show } from "solid-js";
import { TopBar } from "./components/TopBar";
import { BottomCard } from "./components/BottomCard";
import { MapCanvas } from "./components/MapCanvas";
import { LibraryModal } from "./components/LibraryModal";
import { SettingsModal } from "./components/SettingsModal";
import { probeApi } from "./stores/worldStore";
import "./styles/theme.css";

function App() {
  const [showLibrary, setShowLibrary] = createSignal(false);
  const [showSettings, setShowSettings] = createSignal(false);

  onMount(() => {
    // Check API health on load + hydrate if world already exists on the server
    probeApi();
  });

  return (
    <>
      <MapCanvas />
      <div class="vignette" />
      <TopBar
        onOpenLibrary={() => setShowLibrary(true)}
        onOpenSettings={() => setShowSettings(true)}
      />
      <BottomCard />

      <Show when={showLibrary()}>
        <LibraryModal onClose={() => setShowLibrary(false)} />
      </Show>

      <Show when={showSettings()}>
        <SettingsModal onClose={() => setShowSettings(false)} />
      </Show>
    </>
  );
}

export default App;
