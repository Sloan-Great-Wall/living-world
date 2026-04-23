/**
 * Tiny Result<T, E> — typed errors for the dashboard's API + IPC boundary.
 *
 * Mirror of the Python `LLMError` discipline (AI-Native criterion B):
 * every failure is a typed value the caller can match on, not a string
 * to regex or an Error subclass to instanceof-chain through stack frames.
 *
 * Why no `neverthrow` dep:
 *   This file is ~30 LoC; pulling a 4 KB lib for that loses bundle
 *   simplicity. The shape is simple enough to inline.
 *
 * Usage:
 *
 *   async function fetchAgents(): Promise<Result<Agent[], ApiError>> {
 *     try {
 *       const r = await fetch(...);
 *       if (!r.ok) return err({ kind: "http", status: r.status });
 *       return ok(await r.json());
 *     } catch (e) {
 *       return err({ kind: "network", message: String(e) });
 *     }
 *   }
 *
 *   const r = await fetchAgents();
 *   if (!r.ok) {
 *     // r.error.kind is narrowed; AI logs see structured tag
 *     console.warn(`api failure: ${r.error.kind}`);
 *     return;
 *   }
 *   r.value.forEach(...);
 */

export type Ok<T>  = { readonly ok: true;  readonly value: T };
export type Err<E> = { readonly ok: false; readonly error: E };
export type Result<T, E> = Ok<T> | Err<E>;

export const ok  = <T>(value: T): Ok<T>  => ({ ok: true,  value });
export const err = <E>(error: E): Err<E> => ({ ok: false, error });

// ── ApiError taxonomy (mirrors Python LLMError families) ─────────────────

export type ApiError =
  | { kind: "network";       message: string }   // fetch threw, daemon down
  | { kind: "timeout";       message: string }   // request exceeded budget
  | { kind: "http";          status: number; body?: string }  // 4xx / 5xx
  | { kind: "bad_response";  message: string }   // JSON parse / shape wrong
  | { kind: "engine_unloaded" }                  // 409 from `_need_engine`
  | { kind: "unknown";       message: string };

export function classifyHttpError(status: number, body?: string): ApiError {
  if (status === 409) return { kind: "engine_unloaded" };
  if (status >= 500)  return { kind: "http", status, body };
  if (status === 408 || status === 504) return { kind: "timeout", message: `HTTP ${status}` };
  return { kind: "http", status, body };
}

/** Map a thrown JS error to ApiError. Network failures most commonly land here. */
export function classifyThrown(e: unknown): ApiError {
  const msg = e instanceof Error ? e.message : String(e);
  if (/timeout|aborted/i.test(msg)) return { kind: "timeout", message: msg };
  if (/network|fetch|refused|disconnect/i.test(msg)) return { kind: "network", message: msg };
  return { kind: "unknown", message: msg };
}
