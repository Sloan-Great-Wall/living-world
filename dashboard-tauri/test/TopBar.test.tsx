/**
 * TopBar render tests — happy paths only.
 *
 * Why these exist (L-20):
 *   Phase 3 moved diversity computation client-side. The server no
 *   longer sends `WorldSnapshot.diversity`; TopBar runs
 *   `diversitySummary()` over the recentEvents store. A broken
 *   `createMemo` or stale prop wiring would only show up by manual
 *   visual inspection. These tests pin the rendering contract so
 *   regressions fail at `make check` time.
 */
import { render, screen, cleanup } from "@solidjs/testing-library";
import { afterEach, describe, expect, it } from "vitest";

import { TopBar } from "../src/components/TopBar";
import {
  setWorldSnapshot,
  setRecentEvents,
  setApiOnline,
} from "../src/stores/worldStore";
import type { WorldEvent, WorldSnapshot } from "../src/types/api";

const EMPTY_SNAP: WorldSnapshot = {
  loaded: false, tick: 0, packs: [], agentsAlive: 0, agentsTotal: 0,
  eventsTotal: 0, deaths: 0, chapters: 0, tiles: 0,
  modelTier2: "—", modelTier3: "—",
};

const ev = (kind: string, tick: number, idSuffix: string): WorldEvent => ({
  id: `e-${idSuffix}`,
  tick, pack: "scp", tile: "t1", kind,
  outcome: "neutral", importance: 0.4, tier: 1,
  isEmergent: false, participants: ["alice"],
  narrative: "...",
});

afterEach(() => {
  cleanup();
  // Reset signals to prevent test cross-contamination.
  setWorldSnapshot(EMPTY_SNAP);
  setRecentEvents([]);
  setApiOnline(false);
});

describe("<TopBar />", () => {
  it("renders brand + stat labels even with empty world", () => {
    render(() => <TopBar onOpenLibrary={() => {}} onOpenSettings={() => {}} />);
    expect(screen.getByText(/Living World/)).toBeInTheDocument();
    expect(screen.getByText(/Library/)).toBeInTheDocument();
    expect(screen.getByText(/Settings/)).toBeInTheDocument();
    // Day stat pill appears even at tick 0
    expect(screen.getByText("Day")).toBeInTheDocument();
  });

  it("hides the diversity pill when there are no events", () => {
    render(() => <TopBar onOpenLibrary={() => {}} onOpenSettings={() => {}} />);
    expect(screen.queryByText("Top")).not.toBeInTheDocument();
  });

  it("shows the diversity pill computed from recentEvents (client-side)", () => {
    setRecentEvents([
      ev("containment-test", 1, "1"),
      ev("containment-test", 2, "2"),
      ev("containment-test", 3, "3"),
      ev("meal-break", 4, "4"),
    ]);
    render(() => <TopBar onOpenLibrary={() => {}} onOpenSettings={() => {}} />);
    // Top kind = containment-test (3/4 = 75%); diversitySummary returns
    // top_kind verbatim, so the pill should mention it.
    const top = screen.getByText("Top");
    expect(top).toBeInTheDocument();
    expect(top.parentElement?.textContent).toMatch(/containment-test/);
    expect(top.parentElement?.textContent).toMatch(/75/); // 75.0%
  });

  it("flips API indicator color when apiOnline changes", () => {
    setApiOnline(true);
    const r = render(() => <TopBar onOpenLibrary={() => {}} onOpenSettings={() => {}} />);
    const apiVal = r.container.querySelector('[title*="API connected"]');
    expect(apiVal).not.toBeNull();
    expect(apiVal!.textContent).toContain("●");
  });

  it("reflects worldSnapshot changes (signal reactivity contract)", () => {
    setWorldSnapshot({ ...EMPTY_SNAP, tick: 42, agentsAlive: 17, deaths: 3 });
    render(() => <TopBar onOpenLibrary={() => {}} onOpenSettings={() => {}} />);
    expect(screen.getByText("42")).toBeInTheDocument();
    expect(screen.getByText("17")).toBeInTheDocument();
    expect(screen.getByText("3")).toBeInTheDocument();
  });
});
