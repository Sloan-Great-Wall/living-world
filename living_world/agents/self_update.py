"""AgentSelfUpdate — after a meaningful event, the agent updates itself.

This is the AgentSociety move: instead of letting hardcoded `STAT_RIPPLES`
decide that "fear += 25" when SCP-173 strikes, the LLM speaks AS the agent
and reports how the experience shifted them — fear, hope, motivation,
goal, the lot. The validator clamps numbers and rejects identity-violating
changes; everything else gets applied.

Result: the agent's internal state becomes a function of its lived
experience, not a function of pre-authored ripple tables.

Cost: one LLM call per (participant, important event). Importance-gated.

Hard rails (validator enforces):
  - life_stage / agent_id / pack_id / persona_card cannot be changed.
  - numeric deltas are clamped to a sane per-update range.
  - tags can only be added/removed if not in a small protected set.
  - reflection text is bounded length.
"""

from __future__ import annotations

import json
import re

from living_world.core.agent import Agent
from living_world.core.event import LegendEvent
from living_world.llm.base import LLMClient


SYSTEM_PROMPT = """You ARE the character below. Something just happened to you.
Report how the experience changed your inner state.

Output a SINGLE JSON object — no prose outside, no code fences. Fields:

  "attribute_deltas": optional dict mapping existing attribute names to
                      integer deltas in [-25, +25]. Only adjust what would
                      plausibly shift from THIS event.
  "needs_deltas":     optional dict over {hunger, safety}, deltas in [-30, +30].
  "emotions_deltas":  optional dict over {fear, joy, anger}, deltas in [-40, +40].
  "tags_to_add":      optional list of short lowercased tags to add
                      (e.g. ["traumatized"], ["resolute"]). Max 2.
  "tags_to_remove":   optional list of tags to remove. Max 2.
  "current_goal":     optional string ≤100 chars — your new active goal,
                      or null to keep the existing one.
  "motivations":      optional list of 1-3 short strings — what's driving
                      you right now beyond your goal.
  "belief_update":    optional {"topic": str, "belief": str ≤120}.
  "reflection":       optional first-person sentence ≤180 chars — a
                      private thought you had about this event.

Rules:
 - Stay in-character. Don't break the fourth wall.
 - Don't invent new events or kill anyone.
 - REQUIRED: if the event mattered to you at all, you MUST return at least
   ONE non-zero delta (emotion, need, or attribute). Empty {} is only valid
   if you literally weren't present or the event was wholly trivial.
 - Scale deltas with intensity: a near-death moment shifts emotions by 20-35,
   a minor surprise by 5-10. Don't undershoot dramatic events.

EXAMPLE 1 — A guard who watched a colleague get killed by SCP-173:
{"emotions_deltas": {"fear": 30, "joy": -15},
 "needs_deltas": {"safety": -25},
 "attribute_deltas": {"morale": -15},
 "tags_to_add": ["shaken"],
 "belief_update": {"topic": "scp-173", "belief": "do not blink, ever"},
 "reflection": "I was three meters away. Three. It could have been me."}

EXAMPLE 2 — A scholar who finally cornered a fox-spirit and it laughed and vanished:
{"emotions_deltas": {"anger": 20, "joy": 10},
 "attribute_deltas": {"resolve": 10},
 "motivations": ["catch the fox-spirit before the next moon"],
 "current_goal": "set a proper iron-cold trap by the willow grove",
 "reflection": "She mocked me. Fine. Next time the iron will be ready."}
"""


def _build_prompt(agent: Agent, event: LegendEvent) -> str:
    """Returns only the DYNAMIC part. SYSTEM_PROMPT is sent separately
    via client.complete(system=...) so Ollama can KV-cache it (P1)."""
    parts = ["YOU"]
    parts.append(f"  Name: {agent.display_name}")
    parts.append(f"  Persona: {(agent.persona_card or '').strip()[:200]}")
    if agent.current_goal:
        parts.append(f"  Current goal: {agent.current_goal}")
    if agent.tags:
        parts.append(f"  Tags: {', '.join(sorted(agent.tags))}")
    if agent.attributes:
        attrs = " ".join(f"{k}:{v}" for k, v in list(agent.attributes.items())[:8])
        parts.append(f"  Attributes: {attrs}")
    needs = agent.get_needs()
    parts.append(
        "  Needs: "
        + " ".join(f"{k}:{v:.0f}" for k, v in needs.items())
    )
    emotions = agent.get_emotions()
    parts.append(
        "  Emotions: "
        + " ".join(f"{k}:{v:.0f}" for k, v in emotions.items())
    )
    beliefs = agent.get_beliefs()
    if beliefs:
        bits = " | ".join(f"{k}: {v}" for k, v in list(beliefs.items())[:3])
        parts.append(f"  Beliefs: {bits}")

    parts.append("")
    parts.append("WHAT JUST HAPPENED")
    parts.append(f"  Event: {event.event_kind} ({event.outcome}, day {event.tick})")
    parts.append(f"  Where: {event.tile_id}")
    parts.append(
        f"  Others involved: "
        + (", ".join(p for p in event.participants if p != agent.agent_id) or "(none)")
    )
    parts.append(f"  What it was: {event.best_rendering()[:280]}")
    parts.append("")
    parts.append("Your update JSON:")
    return "\n".join(parts)


# ── Validator constants ───────────────────────────────────────────────────
_PROTECTED_TAGS = {"scp", "cthulhu", "liaozhai", "anomaly",
                    "great-old-one", "outer-god", "deity",
                    "permanent_historical", "d-class", "researcher"}
_NEED_KEYS = {"hunger", "safety"}
_EMOTION_KEYS = {"fear", "joy", "anger"}
_BANNED_TAGS = {"deceased", "alive", "born"}  # state changes only via rules


def _parse(text: str) -> dict | None:
    """Best-effort JSON extraction. First tries the whole text, then a
    greedy {...} match (handles nested objects properly)."""
    t = (text or "").strip()
    if not t:
        return None
    # Direct parse first — works for clean JSON.
    try:
        data = json.loads(t)
        return data if isinstance(data, dict) else None
    except Exception:
        pass
    # Fallback: greedy match grabs the outermost braces (handles nested).
    m = re.search(r"\{[\s\S]*\}", t)
    if not m:
        return None
    try:
        data = json.loads(m.group(0))
    except Exception:
        return None
    return data if isinstance(data, dict) else None


def _clamp_int(v, lo: int, hi: int) -> int | None:
    try:
        n = int(v)
    except (TypeError, ValueError):
        return None
    return max(lo, min(hi, n))


def _clamp_float(v, lo: float, hi: float) -> float | None:
    try:
        n = float(v)
    except (TypeError, ValueError):
        return None
    return max(lo, min(hi, n))


def _validate_tag(t) -> str | None:
    if not isinstance(t, str):
        return None
    s = t.strip().lower()
    if not s or len(s) > 32 or " " in s or s in _BANNED_TAGS:
        return None
    return s


class AgentSelfUpdate:
    """LLM speaks AS the agent and reports their inner state change."""

    def __init__(self, client: LLMClient) -> None:
        self.client = client
        # Diagnostic counters
        self.stats = {"calls": 0, "llm_error": 0, "parse_fail": 0,
                       "empty_dict": 0, "ok_real": 0, "ok_fallback": 0}

    def apply(self, agent: Agent, event: LegendEvent) -> dict:
        """Mutate the agent based on LLM-emitted delta. Returns the parsed
        delta for logging (empty dict on any failure or noise)."""
        self.stats["calls"] += 1
        try:
            resp = self.client.complete(_build_prompt(agent, event),
                                         max_tokens=380, temperature=0.7,
                                         json_mode=True, system=SYSTEM_PROMPT)
        except Exception:
            self.stats["llm_error"] += 1
            return {}
        return self._apply_response(agent, event, resp.text)

    async def apply_async(self, agent: Agent, event: LegendEvent) -> dict:
        """Async variant — pair with asyncio.gather() to update many
        agents' inner state in parallel after a multi-participant event.
        Big tick-time win for events with 2-4 participants."""
        self.stats["calls"] += 1
        try:
            resp = await self.client.acomplete(_build_prompt(agent, event),
                                                max_tokens=380, temperature=0.7,
                                                json_mode=True)
        except Exception:
            self.stats["llm_error"] += 1
            return {}
        return self._apply_response(agent, event, resp.text)

    def _apply_response(self, agent: Agent, event: LegendEvent, text: str) -> dict:
        """Shared post-LLM logic — parse text, mutate agent, return delta dict.
        Both sync `apply` and `apply_async` end here so behavior is identical."""
        data = _parse(text or "")
        if data is None:
            self.stats["parse_fail"] += 1
            data = {}  # fall through to fallback path
        if not data:
            self.stats["empty_dict"] += 1

        applied: dict = {}

        # Attribute deltas — only for keys the agent already has, clamped.
        att = data.get("attribute_deltas")
        if isinstance(att, dict) and agent.attributes:
            applied_att: dict = {}
            for k, v in att.items():
                if k not in agent.attributes:
                    continue
                cur = agent.attributes[k]
                if not isinstance(cur, (int, float)):
                    continue
                d = _clamp_int(v, -25, 25)
                if d is None or d == 0:
                    continue
                new = max(0, min(100, int(cur) + d))
                agent.attributes[k] = new
                applied_att[k] = d
            if applied_att:
                applied["attribute_deltas"] = applied_att

        # Needs deltas
        nd = data.get("needs_deltas")
        if isinstance(nd, dict):
            applied_nd: dict = {}
            for k, v in nd.items():
                if k not in _NEED_KEYS:
                    continue
                d = _clamp_float(v, -30.0, 30.0)
                if d is None or d == 0:
                    continue
                agent.adjust_need(k, d)
                applied_nd[k] = d
            if applied_nd:
                applied["needs_deltas"] = applied_nd

        # Emotions deltas
        ed = data.get("emotions_deltas")
        if isinstance(ed, dict):
            applied_ed: dict = {}
            for k, v in ed.items():
                if k not in _EMOTION_KEYS:
                    continue
                d = _clamp_float(v, -40.0, 40.0)
                if d is None or d == 0:
                    continue
                agent.adjust_emotion(k, d)
                applied_ed[k] = d
            if applied_ed:
                applied["emotions_deltas"] = applied_ed

        # Tag adds (capped)
        adds = data.get("tags_to_add")
        if isinstance(adds, list):
            ok_adds = []
            for t in adds[:2]:
                s = _validate_tag(t)
                if s and s not in _PROTECTED_TAGS and s not in agent.tags:
                    agent.tags.add(s)
                    ok_adds.append(s)
            if ok_adds:
                applied["tags_added"] = ok_adds

        # Tag removes (cannot remove protected tags)
        rems = data.get("tags_to_remove")
        if isinstance(rems, list):
            ok_rems = []
            for t in rems[:2]:
                s = _validate_tag(t)
                if s and s in agent.tags and s not in _PROTECTED_TAGS:
                    agent.tags.discard(s)
                    ok_rems.append(s)
            if ok_rems:
                applied["tags_removed"] = ok_rems

        # Current goal update
        goal = data.get("current_goal")
        if isinstance(goal, str):
            new_goal = goal.strip()[:100]
            if new_goal and new_goal != agent.current_goal:
                agent.current_goal = new_goal
                applied["new_goal"] = new_goal

        # Motivations
        mots = data.get("motivations")
        if isinstance(mots, list):
            cleaned = [str(m).strip()[:80] for m in mots[:3]
                       if isinstance(m, (str, int, float)) and str(m).strip()]
            if cleaned:
                agent.state_extra["motivations"] = cleaned
                applied["motivations"] = cleaned

        # Belief update (single one)
        bu = data.get("belief_update")
        if isinstance(bu, dict):
            topic = bu.get("topic")
            belief = bu.get("belief")
            if isinstance(topic, str) and isinstance(belief, str):
                topic = topic.strip()[:48]
                belief = belief.strip()[:200]
                if topic and belief:
                    agent.set_belief(topic, belief)
                    applied["belief_update"] = {"topic": topic, "belief": belief}

        # Reflection (returned to caller for memory storage)
        refl = data.get("reflection")
        if isinstance(refl, str):
            r = refl.strip()[:200]
            if r:
                applied["reflection"] = r

        # ── Fallback: meaningful events MUST leave a mark ──
        # If the LLM coughed up nothing numeric on a meaningful event, inject
        # default emotional drift so internal state actually moves. Keeps the
        # system from going completely static when a small local model is too
        # conservative. Threshold matches self_update_threshold (0.5) so every
        # call that gets here is fallback-eligible.
        numeric_keys = ("attribute_deltas", "needs_deltas", "emotions_deltas")
        had_numeric = any(k in applied for k in numeric_keys)
        if not had_numeric and event.importance >= 0.5:
            outcome = (event.outcome or "neutral").lower()
            if outcome == "failure":
                fb_em, fb_nd = {"fear": 12.0, "joy": -8.0}, {"safety": -10.0}
            elif outcome == "success":
                fb_em, fb_nd = {"joy": 10.0, "fear": -5.0}, {}
            else:
                fb_em, fb_nd = {"fear": 5.0}, {}
            for k, d in fb_em.items():
                agent.adjust_emotion(k, d)
            for k, d in fb_nd.items():
                agent.adjust_need(k, d)
            applied["emotions_deltas"] = fb_em
            if fb_nd:
                applied["needs_deltas"] = fb_nd
            applied["_fallback"] = True
            self.stats["ok_fallback"] += 1
        elif had_numeric:
            self.stats["ok_real"] += 1

        return applied
