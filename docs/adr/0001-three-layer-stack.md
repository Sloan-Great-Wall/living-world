# ADR 0001 · Three-layer T-shape (Python + Rust + TypeScript)

| Status | Accepted (retroactive — codified 2026-04-26) |
|---|---|
| Deciders | sloan + Claude |
| Supersedes | — |

## Context

Early Living World ran as a single Python program: Streamlit UI in the
same process as the sim engine. By Phase 1 (2026-04-26) we had:

- A non-trivial sim core (~10k LoC Python: phases, agents, LLM,
  memory, rules)
- A growing UI (Streamlit dashboard, ~1.6k LoC of mixed render + state)
- A roadmap toward desktop distribution and offline replay

The question we kept circling: **should this stay all-Python? go
all-TypeScript? something else?**

## Decision

Three layers, three languages. T-shape:

```
TS (UI + browser-side compute)         ← arms
Rust (Tauri shell + lifecycle)         ← spine
Python (sim engine + LLM + analysis)   ← arms
```

Each language is chosen for what it is **irreplaceable** at, not for
preference:

- **Python** owns simulation orchestration + LLM ecosystem (Ollama
  client, huggingface, langchain-family, marimo). The 18-month gap to
  the JS LLM ecosystem makes this the cheapest seat.
- **TypeScript** owns UI and any compute that benefits from running in
  the browser/webview. tsc strict mode + Solid + Vite is the best AI-
  coding training-data density available.
- **Rust** owns the Tauri shell. Rust is reserved for the spine — IPC
  schemas, process lifecycle, future hot-loop WASM compute. Today the
  shell carries only the sidecar spawn logic; that is sufficient
  reason to keep the slot.

## Alternatives considered

### A · All-Python (Streamlit / Reflex / Gradio)
- **Pro**: smallest stack, single language for everyone
- **Con**: Streamlit re-renders the whole page on every interaction;
  no path to bundled desktop distribution; UI feels 5 years old
- **Verdict**: rejected. UX would be the bottleneck for everything
  else. (Streamlit dashboard was deleted in Phase 1.)

### B · All-TypeScript (port the sim too)
- **Pro**: single language, compiler-strict end to end, native browser
  + Tauri reach, bundled .app/.exe distribution easy
- **Con**: TS LLM ecosystem (Vercel AI SDK, Mastra, LangGraph.js) is
  catching up but still 12-18 months behind Python for advanced agent
  workflows. Marimo has no TS equivalent. A full sim port is months
  of work.
- **Verdict**: rejected for **now**, but Phase 3 set up a path: ports
  pure-function modules selectively (`packages/sim-core/`). When the
  TS LLM ecosystem closes the gap AND when ≥80% of the sim's pure-
  function surface is in TS, this becomes feasible.

### C · All-Rust (Leptos UI + Rust sim)
- **Pro**: maximally type-safe, fastest hot path, single language,
  best memory safety guarantees
- **Con**: Rust LLM ecosystem is the smallest of the three. AI-coding
  iteration on Rust UI work is slow (compile times, complex error
  messages on first attempt). For UI tweaks specifically, the
  AI-assisted productivity gap vs TS is ~3-5×.
- **Verdict**: rejected. We had a brief 2026-04-22 plan for full-Rust
  Leptos + WGPU + Rust-cored sim; walked it back to Solid + TS within
  Tauri's Rust shell. See `HISTORY.md` "Web stack: Rust/Leptos →
  reverted to TS/Solid" for the rationale.

### D · pyo3 (embed Python in Rust)
- **Pro**: one process, no IPC, no JSON serialization, no port
  management
- **Con**: 100+ pyo3 binding declarations; loses Python independent
  debug story; cross-platform pyo3 packaging has rough edges
- **Verdict**: rejected. Pure-function port (Path B) gets most of
  the benefit at a fraction of the cost.

## Consequences

**Positive**:
- Each layer can iterate in its native idiom
- Cross-boundary contracts are explicit (Pydantic → OpenAPI → TS),
  caught at compile time
- The sim can be debugged headless without UI; the UI can be developed
  against a stub backend

**Negative**:
- Three build chains (uv + cargo + npm); contributors need to know all
  three or accept they only work in one layer
- Two test frameworks (pytest + vitest) with parity-fixture protocol
  to keep them in sync
- A bug surfaces at one layer requires reasoning in two languages
  often (e.g. SCP-as-participant landed in Python validator + TS
  rendering both)

**Neutral**:
- Rust's role is "reserved capacity" — today minimal, designed to
  expand into IPC marshaling + WASM hot-path compute as needed

## Validation criteria

Decision should be revisited if:
1. TS LLM ecosystem reaches Python parity for agent frameworks
   (Vercel AI SDK + Mastra + LangGraph.js close the 12-18-month gap)
2. Pure-function port surface in `packages/sim-core/` exceeds 80% of
   the sim's deterministic logic
3. Rust shell stays empty (zero IPC schema work, zero WASM compute)
   for 12+ months
4. A team member who knows only one language consistently can't
   contribute outside that layer

If 1 + 2 hold simultaneously: consider migration to all-TS (Path B).
If 3 alone: consider dropping Tauri for plain-browser web app.
