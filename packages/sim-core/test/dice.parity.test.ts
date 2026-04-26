/**
 * Parity tests: every fixture in test/fixtures/dice_*.json was produced
 * by the Python implementation. This file asserts the TypeScript port
 * returns the same value.
 *
 * If a fixture fails after a deliberate change, regen with:
 *   npm run regen-fixtures
 * and review the diff.
 */
import { describe, it, expect } from "vitest";

import importanceFixtures from "./fixtures/dice_importance.json" with { type: "json" };
import outcomeFixtures from "./fixtures/dice_outcome.json" with { type: "json" };
import modifierFixtures from "./fixtures/dice_modifiers.json" with { type: "json" };

import {
  scoreEventImportance,
  outcomeForRoll,
  environmentalModifiers,
  requiredSlots,
  type AgentLite,
  type EventLite,
  type TemplateLite,
  type Outcome,
} from "../src/dice.js";

describe("dice.scoreEventImportance — parity", () => {
  for (const c of importanceFixtures as Array<{
    name: string;
    event: EventLite;
    participants: AgentLite[];
    opts: { baseImportance?: number; tileHasActivePlayer?: boolean };
    expected: number;
  }>) {
    it(c.name, () => {
      const got = scoreEventImportance(c.event, c.participants, c.opts);
      expect(got).toBeCloseTo(c.expected, 10);
    });
  }
});

describe("dice.outcomeForRoll — parity", () => {
  for (const c of outcomeFixtures as Array<{
    name: string;
    template: TemplateLite;
    participants: AgentLite[];
    rawD20: number;
    expected: Outcome;
  }>) {
    it(c.name, () => {
      const got = outcomeForRoll(c.template, c.participants, c.rawD20);
      expect(got).toBe(c.expected);
    });
  }
});

describe("dice.environmentalModifiers — parity", () => {
  for (const c of modifierFixtures as Array<{
    name: string;
    event: EventLite;
    participants: AgentLite[];
    ctx: { currentTick: number; priorsInWindow: Array<{ tileId: string; eventKind: string }> };
    expected: number;
  }>) {
    it(c.name, () => {
      const got = environmentalModifiers(c.event, c.participants, c.ctx);
      expect(got).toBeCloseTo(c.expected, 10);
    });
  }
});

describe("dice.requiredSlots — Phase 3 port (?-leak guard)", () => {
  it("returns 0 for templates with no slots", () => {
    expect(requiredSlots("plain text")).toBe(0);
    expect(requiredSlots("")).toBe(0);
  });
  it("detects $a slot", () => {
    expect(requiredSlots("[$tile] $a does X.")).toBe(1);
  });
  it("detects ${b} slot (highest = 2)", () => {
    expect(requiredSlots("[$tile] ${a} meets ${b}")).toBe(2);
  });
  it("detects all three slots", () => {
    expect(requiredSlots("$a, $b and $c attend")).toBe(3);
  });
  it("returns highest slot, not count", () => {
    expect(requiredSlots("$a and $a and $a")).toBe(1);
  });
});

describe("dice — additional unit tests (TS-side invariants)", () => {
  it("scoreEventImportance is bounded to [0, 1]", () => {
    const event: EventLite = {
      eventKind: "containment-breach",
      outcome: "failure",
      tileId: "t1",
      relationshipChanges: [{}, {}, {}],
    };
    const hf = (id: string): AgentLite => ({
      agentId: id, displayName: id, attributes: {},
      isHistoricalFigure: true,
    });
    const r = scoreEventImportance(event, [hf("a"), hf("b"), hf("c")], {
      baseImportance: 0.9,
      tileHasActivePlayer: true,
    });
    expect(r).toBeLessThanOrEqual(1.0);
    expect(r).toBeGreaterThanOrEqual(0.0);
  });

  it("environmentalModifiers clamps to [0.5, 1.5]", () => {
    const event: EventLite = {
      eventKind: "x", outcome: "neutral", tileId: "t1",
      relationshipChanges: [],
    };
    // 20 same-kind priors would push way below 0.5 without clamp
    const priors = Array.from({ length: 20 }, () => ({
      tileId: "t1", eventKind: "x",
    }));
    const r = environmentalModifiers(event, [], {
      currentTick: 100, priorsInWindow: priors,
    });
    expect(r).toBeGreaterThanOrEqual(0.5);
    expect(r).toBeLessThanOrEqual(1.5);
  });
});
