/**
 * api.ts base-URL resolution test (L-20).
 *
 * Specifically pins the contract that matters for "browser dev still
 * works after Tauri sidecar landed": when there's no Tauri shell
 * (no __TAURI_INTERNALS__ on window), the API client must fall back
 * to the legacy localhost:8000 so a manual `lw serve` still drives
 * the dashboard.
 *
 * In Tauri-shell mode the resolution path goes through invoke() which
 * we can't exercise here without the runtime; that path is covered by
 * the smoke-launch in `make check` once L-21 lands.
 */
import { describe, expect, it } from "vitest";

import { api } from "../src/api";

describe("api — base URL resolution", () => {
  it("falls back to localhost:8000 in plain-browser dev (no Tauri shell)", async () => {
    // The vitest jsdom environment has no __TAURI_INTERNALS__, so
    // resolveBase() takes the FALLBACK_BASE branch on the first call.
    let receivedUrl = "";
    const origFetch = globalThis.fetch;
    globalThis.fetch = ((input: RequestInfo | URL) => {
      receivedUrl = String(input);
      // Return a resolved Response so j<T>() doesn't throw.
      return Promise.resolve(
        new Response(JSON.stringify({ ok: true, loaded: false }), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        }),
      );
    }) as typeof fetch;

    try {
      await api.health();
      expect(receivedUrl).toMatch(/^http:\/\/127\.0\.0\.1:8000\//);
      expect(receivedUrl).toContain("/api/health");
    } finally {
      globalThis.fetch = origFetch;
    }
  });
});
