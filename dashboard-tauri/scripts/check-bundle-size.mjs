#!/usr/bin/env node
/**
 * Bundle-size budget check for @living-world/sim-core consumption.
 *
 * Strategy: build a tiny entry that imports ONLY the public surface of
 * sim-core (no Solid, no app code), then measure the produced JS chunk.
 * That isolates "what does sim-core add to the dashboard bundle" from
 * the noise of Solid + framework runtime.
 *
 * Budget: 50 KB minified (raw, not gzipped). The TS port is two pure-
 * function modules — anything bigger means we accidentally pulled in
 * a runtime dep.
 *
 * Run: npm run bundle:check  (from dashboard-tauri/)
 */
import { build } from "vite";
import { mkdtempSync, rmSync, writeFileSync, readdirSync, statSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import { dirname } from "node:path";

const __dirname = dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = join(__dirname, "..", "..");
const BUDGET_KB = 50;

// 1. Stage a tiny entry that touches the entire sim-core public API.
const stage = mkdtempSync(join(tmpdir(), "sim-core-bundle-"));
writeFileSync(
  join(stage, "entry.ts"),
  `
import {
  scoreEventImportance,
  outcomeForRoll,
  environmentalModifiers,
  inventoryBonus,
  computeSocialMetrics,
  affinityGraph,
  SPOTLIGHT_EVENT_KINDS,
} from "@living-world/sim-core";

// Force the bundler to keep all references live. (Tree-shaker would
// otherwise drop unused exports and under-report the real footprint.)
globalThis.__simCoreSurface = {
  scoreEventImportance, outcomeForRoll, environmentalModifiers,
  inventoryBonus, computeSocialMetrics, affinityGraph,
  SPOTLIGHT_EVENT_KINDS,
};
`,
);

// 2. Build with the same toolchain the dashboard uses.
process.chdir(stage);
try {
  await build({
    root: stage,
    logLevel: "warn",
    resolve: {
      alias: {
        "@living-world/sim-core": join(
          REPO_ROOT, "packages", "sim-core", "src", "index.ts",
        ),
      },
    },
    build: {
      target: "es2022",
      minify: "esbuild",
      outDir: join(stage, "dist"),
      emptyOutDir: true,
      reportCompressedSize: false,
      rollupOptions: {
        input: join(stage, "entry.ts"),
        // Inline EVERYTHING — no externals — so the chunk size on disk
        // truly equals what sim-core costs the dashboard bundle.
        external: [],
        output: {
          format: "esm",
          entryFileNames: "sim-core-bundle.js",
          inlineDynamicImports: true,
        },
      },
    },
  });

  // 3. Measure. Walk recursively in case Vite emits to subdirs.
  function walk(dir) {
    const out = [];
    for (const name of readdirSync(dir)) {
      const p = join(dir, name);
      const s = statSync(p);
      if (s.isDirectory()) out.push(...walk(p));
      else if (name.endsWith(".js") || name.endsWith(".mjs")) out.push(p);
    }
    return out;
  }
  const outDir = join(stage, "dist");
  const files = walk(outDir);
  if (files.length === 0) {
    console.error(`✗ no JS chunks emitted to ${outDir}`);
    console.error(`  contents: ${readdirSync(outDir).join(", ") || "(empty)"}`);
    process.exit(1);
  }
  let totalBytes = 0;
  for (const f of files) totalBytes += statSync(f).size;
  const totalKb = totalBytes / 1024;

  const status = totalKb <= BUDGET_KB ? "PASS" : "FAIL";
  console.log("");
  console.log(`sim-core bundle:  ${totalBytes.toLocaleString()} bytes  (${totalKb.toFixed(2)} KB)`);
  console.log(`budget:           ${BUDGET_KB} KB`);
  console.log(`status:           ${status}`);
  console.log("");
  for (const f of files) {
    const sz = statSync(f).size;
    console.log(`  ${f.slice(outDir.length + 1)}  ${(sz / 1024).toFixed(2)} KB`);
  }

  if (totalKb > BUDGET_KB) {
    console.error(`\n✗ sim-core bundle exceeds ${BUDGET_KB} KB budget`);
    process.exit(1);
  } else {
    console.log(`\n✓ sim-core bundle under budget (${(BUDGET_KB - totalKb).toFixed(1)} KB headroom)`);
  }
} finally {
  rmSync(stage, { recursive: true, force: true });
}
