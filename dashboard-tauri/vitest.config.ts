/// <reference types="vitest" />
import { defineConfig } from "vitest/config";
import solid from "vite-plugin-solid";

/**
 * vitest config — separate from vite.config.ts so the Tauri dev
 * server stays focused on app launch and isn't tangled with the
 * test runner's jsdom setup.
 *
 * jsdom provides DOM APIs (document, window) so Solid components can
 * actually render in tests. The `solid` plugin compiles JSX with the
 * runtime's reactive transform, the same way the dev server does.
 */
export default defineConfig({
  plugins: [solid()],
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./test/setup.ts"],
    include: ["test/**/*.test.{ts,tsx}"],
  },
  resolve: {
    // Solid's testing recommendation: prefer the development bundle
    // for tests so reactivity warnings surface clearly.
    conditions: ["development", "browser"],
  },
});
