/**
 * API types — friendly aliases over the auto-generated OpenAPI surface.
 *
 * Source of truth: `living_world/web/schemas.py` (Pydantic).
 * Pipeline:        Python → api-schema/openapi.json → api.generated.ts → here.
 *
 * Run `make schema` to refresh after any Python schema change. `tsc --noEmit`
 * will then red-line every consumer that no longer matches.
 *
 * DO NOT add new fields here — add them in schemas.py and regenerate.
 * This file ONLY contains friendly re-exports + small helper types that
 * have no Python counterpart.
 */
import type { components } from "./api.generated";

type Schemas = components["schemas"];

// ── Domain models (mirrored from Python Pydantic) ────────────────────────

export type Agent              = Schemas["Agent"];
export type Relationship       = Schemas["Relationship"];
export type WorldEvent         = Schemas["WorldEvent"];
export type WorldSnapshot      = Schemas["WorldSnapshot"];
export type Tile               = Schemas["Tile"];
export type Chapter            = Schemas["Chapter"];
export type FeatureStatus      = Schemas["FeatureStatus"];
export type EventTemplateRow   = Schemas["EventTemplateRow"];
export type PersonaRow         = Schemas["PersonaRow"];
export type SocialGraph        = Schemas["SocialGraph"];
export type SocialAgent        = Schemas["SocialAgent"];
export type SocialRelationship = Schemas["SocialRelationship"];
export type Health             = Schemas["Health"];
export type Ok                 = Schemas["Ok"];

// Diversity / event-kinds / chronicle.md were removed from the wire
// format in 2026-04-26. The dashboard computes them client-side via
// `@living-world/sim-core` (diversitySummary / eventKindDistribution /
// exportChronicleMarkdown). Re-export the TS-side type for convenience:
export type { DiversitySummary } from "@living-world/sim-core";

// Request bodies
export type BootstrapBody      = Schemas["BootstrapBody"];
export type TickBody           = Schemas["TickBody"];

// ── Friendly outcome literal (the OpenAPI enum erases to bare string;
//    keep a tighter type for switch() exhaustiveness on the UI side).
export type Outcome = "success" | "failure" | "neutral";
