/**
 * Dice resolver — TypeScript port of `living_world/rules/resolver.py`.
 *
 * Scope of this trial port: the *pure* parts only.
 *   - `scoreEventImportance`     ↔ `score_event_importance`
 *   - `environmentalModifiers`   ↔ `_environmental_modifiers`
 *   - `inventoryBonus`           ↔ `_inventory_bonus`
 *   - `outcomeForRoll`           ↔ pure outcome-from-roll-value branch of `_roll_outcome`
 *
 * Deliberately NOT ported: the `EventResolver` class itself (it owns
 * mutation of World/Agent state, which would mean porting the whole
 * data layer). The point of this trial is to prove that the
 * computational kernel is portable and parity-checkable.
 *
 * Parity strategy: identical float math + identical control flow.
 * We do NOT try to reproduce Python's `random.Random` byte-for-byte —
 * instead, parity tests pass an explicit roll value into
 * `outcomeForRoll`, separating the deterministic logic from the
 * non-portable RNG.
 */

// ── Types ────────────────────────────────────────────────────────────────

export type Outcome = "success" | "failure" | "neutral";

export interface AgentLite {
  agentId: string;
  displayName: string;
  attributes: Record<string, number>;
  isHistoricalFigure: boolean;
  beliefs?: Record<string, string>;
  weeklyPlan?: { seek?: string[]; goalsThisWeek?: string[]; avoid?: string[] };
  motivations?: string[];
  inventory?: ItemLite[];
}

export interface ItemLite {
  tags: string[];
  power: number;
}

export interface EventLite {
  eventKind: string;
  outcome: Outcome;
  tileId: string;
  relationshipChanges: unknown[];
}

export interface TemplateLite {
  eventKind: string;
  baseImportance: number;
  diceRoll?: { stat?: string; dc?: number; mod?: number };
  triggerConditions?: { requiredTags?: string[] };
}

export interface PriorEvent {
  tileId: string;
  eventKind: string;
}

// ── Importance scoring ──────────────────────────────────────────────────

export const SPOTLIGHT_EVENT_KINDS: ReadonlySet<string> = new Set([
  "containment-breach", "descent", "possession", "cult-ritual",
  "renlao-tryst", "karmic-return", "heart-swap", "yaksha-attack",
  "682-tests", "silver-key", "096-sighting-risk", "o5-memo",
]);

export interface ScoreOpts {
  tileHasActivePlayer?: boolean;
  baseImportance?: number;
}

/**
 * Mirrors `score_event_importance`. Pure float math — bit-exact parity
 * with the Python implementation.
 */
export function scoreEventImportance(
  event: EventLite,
  participants: ReadonlyArray<AgentLite>,
  opts: ScoreOpts = {},
): number {
  const baseImportance = opts.baseImportance ?? 0.1;
  const tileHasActivePlayer = opts.tileHasActivePlayer ?? false;

  let score = baseImportance;
  if (SPOTLIGHT_EVENT_KINDS.has(event.eventKind) && baseImportance >= 0.5) {
    score = Math.max(score, 0.7);
  }
  // Only 2+ HFs interacting is notable
  const hfCount = participants.reduce(
    (n, p) => n + (p.isHistoricalFigure ? 1 : 0), 0,
  );
  if (hfCount >= 2) score += 0.08;
  if (event.relationshipChanges.length >= 2) score += 0.05;
  if (tileHasActivePlayer) score += 0.35;
  if (event.outcome === "failure" && baseImportance >= 0.5) score += 0.1;
  return Math.min(1.0, Math.max(0.0, score));
}

// ── Environmental modifiers ─────────────────────────────────────────────

export interface ModifierContext {
  /** Current world tick. */
  currentTick: number;
  /** Event kinds in this tile within the lookup window. */
  priorsInWindow: ReadonlyArray<PriorEvent>;
  /** Window length in ticks (default 7, matches Python). */
  noveltyWindow?: number;
}

/**
 * Mirrors `_environmental_modifiers`. Returns a multiplier in [0.5, 1.5].
 * Inputs are pre-aggregated rather than walking the whole World — keeps
 * this side of the boundary stateless.
 */
export function environmentalModifiers(
  event: EventLite,
  participants: ReadonlyArray<AgentLite>,
  ctx: ModifierContext,
): number {
  let multiplier = 1.0;

  // Novelty decay
  const sameInWindow = ctx.priorsInWindow.filter(
    (p) => p.tileId === event.tileId && p.eventKind === event.eventKind,
  ).length;
  if (sameInWindow >= 1) {
    multiplier *= Math.pow(0.85, sameInWindow);
  }

  // Resonance with participant inner state
  if (participants.length >= 2) {
    const ids = new Set(participants.map((p) => p.agentId));
    const namesLower = new Set(participants.map((p) => p.displayName.toLowerCase()));
    for (const p of participants) {
      const others = new Set([...ids].filter((id) => id !== p.agentId));
      const beliefs = p.beliefs ?? {};
      if ([...others].some((o) => o in beliefs)) {
        multiplier *= 1.15;
        break;
      }
      const plan = p.weeklyPlan ?? {};
      const mots = p.motivations ?? [];
      const blob = [
        ...(plan.seek ?? []),
        ...(plan.goalsThisWeek ?? []),
        ...(plan.avoid ?? []),
        ...mots,
      ].map((x) => String(x).toLowerCase()).join(" ");
      const myName = p.displayName.toLowerCase();
      const hit = [...namesLower].some((n) => n !== myName && blob.includes(n));
      if (hit) {
        multiplier *= 1.15;
        break;
      }
    }
  }

  return Math.max(0.5, Math.min(1.5, multiplier));
}

// ── Roll mechanics ──────────────────────────────────────────────────────

/**
 * Mirrors `_inventory_bonus`. Sum of item powers for items whose tags
 * overlap the event template's `requiredTags` or `eventKind`.
 */
export function inventoryBonus(
  participant: AgentLite,
  template: TemplateLite,
): number {
  if (!participant.inventory || participant.inventory.length === 0) return 0;
  const kindLower = template.eventKind.toLowerCase();
  const req = template.triggerConditions?.requiredTags ?? [];
  const relevant = new Set<string>([kindLower, ...req.map((t) => t.toLowerCase())]);
  let bonus = 0;
  for (const item of participant.inventory) {
    const itemTerms = new Set<string>([
      kindLower,
      ...item.tags.map((t) => t.toLowerCase()),
    ]);
    // Set intersection — same exact-overlap semantics as Python
    for (const term of itemTerms) {
      if (relevant.has(term)) {
        bonus += item.power;
        break;
      }
    }
  }
  return bonus;
}

/**
 * Highest participant-slot index referenced by a template string
 * (a→1, b→2, c→3). Returns 0 if no slots are referenced.
 *
 * Mirrors `EventResolver._required_slots`. Callers use this to drop a
 * template whose narrative references more participants than were
 * eligible — preventing "?"-leaking placeholders from reaching the
 * narrative layer (regression: 2026-04-22 ?-bug).
 */
export function requiredSlots(templateStr: string): number {
  if (!templateStr) return 0;
  const slots: Array<[string, number]> = [
    ["$a", 1], ["$b", 2], ["$c", 3],
    ["${a}", 1], ["${b}", 2], ["${c}", 3],
  ];
  let needs = 0;
  for (const [token, n] of slots) {
    if (templateStr.includes(token)) needs = Math.max(needs, n);
  }
  return needs;
}

/**
 * Pure outcome-from-roll branch of `_roll_outcome`. Caller supplies the
 * raw d20 roll; we add stat-modifier + template `mod` + inventory cap
 * and compare to DC. Separating roll value from logic is what makes
 * the TS port parity-checkable without a Python-compatible RNG.
 */
export function outcomeForRoll(
  template: TemplateLite,
  participants: ReadonlyArray<AgentLite>,
  rawD20: number,
): Outcome {
  const cfg = template.diceRoll ?? {};
  if (!cfg || (cfg.stat === undefined && cfg.dc === undefined && cfg.mod === undefined)) {
    return "neutral";
  }
  const dc = cfg.dc ?? 12;
  const stat = cfg.stat;
  const mod = cfg.mod ?? 0;

  let bonus = 0;
  let invBonus = 0;
  if (participants.length > 0) {
    if (stat) {
      const bonuses: number[] = [];
      for (const p of participants) {
        const v = p.attributes[stat];
        if (typeof v === "number" && Number.isFinite(v)) {
          // D&D-style: floor((v - 10) / 2)
          bonuses.push(Math.trunc((v - 10) / 2));
        }
      }
      if (bonuses.length > 0) bonus = Math.max(...bonuses);
    }
    const invBonuses = participants.map((p) => inventoryBonus(p, template));
    if (invBonuses.length > 0) {
      invBonus = Math.min(5, Math.max(...invBonuses));
    }
  }
  const total = rawD20 + bonus + mod + invBonus;
  if (total >= dc) return "success";
  if (total <= Math.max(1, dc - 10)) return "failure";
  return "neutral";
}
