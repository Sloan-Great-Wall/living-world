# ADR 0004 · Chronicler is non-interventionist

| Status | Accepted (retroactive — codified 2026-04-26) |
|---|---|
| Deciders | sloan + Claude |
| Supersedes | — |

## Context

Once we had multiple LLM agents (planner, narrator, emergent
proposer, conscience), the temptation grew to give them all
"steering" power: let the chronicler nudge what happens next, let the
narrator decide who lives. This is what RimWorld's "Storyteller"
does (Cassandra/Phoebe/Randy directly schedule events).

The question: should the chronicler — the 说书人 who writes chapter
summaries — also influence the future?

## Decision

**No.** The chronicler is strictly **descriptive**. It reads what has
emerged, picks the most narratively significant moments, and writes a
chapter. It does **not**:

- Schedule future events
- Adjust agent state, beliefs, motivations
- Push the storyteller toward any tile or event kind
- Talk to the conscience or the resolver

This is enforced in code:
- `living_world/agents/chronicler.py` only reads `world.events_since`
  and `world.chapters` (write to chapters is a function call, not
  state mutation)
- `ChroniclerPhase` runs AFTER `StorytellerPhase` and `EmergentPhase`
  every tick — by construction it cannot influence the events it sees
- The chronicler has no LLM call into the next tick's prompt
  machinery; planner / emergent / narrator never read chapters

Mental model: **screenwriter vs chronicler**. A screenwriter decides
Act 2 climax. A chronicler notes what happened and what it meant. We
have a screenwriter (the storyteller + emergent proposer); we don't
need the chronicler to be a second one.

## Alternatives considered

### A · Chronicler also schedules events ("RimWorld Cassandra" mode)
- **Pro**: tighter narrative arc; AI can engineer climaxes
- **Con**: invalidates the *emergent* premise of the sim. Once events
  are scheduled, every event becomes an artifact of the chronicler's
  arc-building, not of agent choice. The whole point of Park-style
  generative agents is that the story emerges from the agents.
- **Verdict**: rejected. The interesting research question is
  "what stories do agents produce on their own?", not "what stories
  does an LLM playwright produce given agents as actors?"

### B · Chronicler can adjust agent beliefs ("the legend changes the
people")
- **Pro**: meta-narrative layer; the way we tell stories shapes the
  characters who live them
- **Con**: same emergent-violation problem; muddier; harder to
  attribute behavior cleanly when debugging
- **Verdict**: rejected, but reserved as future "if cross-pack myth-
  blending becomes a goal" hook. Not part of base sim.

### C · Two chroniclers (descriptive + steering, separate)
- **Pro**: clean separation; flag-flippable
- **Con**: doubles the LLM cost; rare to want both at once
- **Verdict**: rejected. If steering ever becomes a feature, it
  belongs in the storyteller / emergent proposer, not in a parallel
  chronicler.

## Consequences

**Positive**:
- Chapters stay honest — they describe what really happened
- Debug story is clean: chronicler output never confuses with sim
  state. "Why did agent X do Y?" never has the answer "because the
  chronicler hinted at it last tick"
- The "AI-as-screenwriter" temptation is structurally blocked

**Negative**:
- Stories sometimes feel meandering. We accept this — agent-generated
  drama is not RimWorld curated drama, and that's the design

**Boundary discipline**:
- ChroniclerPhase runs AFTER all event-producing phases each tick
- chronicler tests assert chapters don't appear in any subsequent
  prompt window
- the dashboard's "Chronicle" tab is read-only — no "edit chapter"
  affordance

## Validation criteria

Revisit if:
1. Multi-pack runs feel arc-less to the point of unwatchable for
   long sessions (consider giving emergent proposer + storyteller a
   "tension target" hint, NOT putting it in the chronicler)
2. Future research direction explicitly wants "AI-as-screenwriter"
   mode for comparative experiments — would warrant a forked branch,
   not a config flag
