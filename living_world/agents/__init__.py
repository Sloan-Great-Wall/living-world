"""Public facade for the LLM-driven agent layer.

Re-exports the classes that other code (factory, tick_loop, tests,
dashboards, future packages) imports. Consumers should write:

    from living_world.agents import AgentSelfUpdate, Narrator

…and never reach into submodules directly. That way a future rename
or split (e.g. moving `MemoryReflector` to `living_world.memory.*`)
only requires editing this file, not every consumer.

This was L-04 in KNOWN_ISSUES.md (2026-04-26 audit). See
`docs/HISTORY.md` for the rationale.

Submodule layout:
    chronicler    — descriptive 说书人; runs every N ticks, never steers
    conscience    — system-2 LLM that may VETO/ADJUST resolver outcomes
    dialogue      — A→B reaction loop, mutates affinity + beliefs
    emergent      — proposes novel events on hot tiles
    event_curator — promotes recurring emergent events into templates
    move_advisor  — LLM tile-choice override on top of the rule layer
    narrator      — Tier-3 narrative rewrite for high-importance events
    perception    — first-person reframe of an event for memory storage
    planner       — weekly per-agent plan (goals / seek / avoid)
    reflector     — Park-style belief synthesis from raw memories
    self_update   — agent speaks AS itself; reports inner-state shift
"""

from __future__ import annotations

from living_world.agents.chronicler import Chapter, Chronicler
from living_world.agents.conscience import ConsciousnessLayer, ConsciousVerdict
from living_world.agents.dialogue import DialogueGenerator
from living_world.agents.emergent import EmergentEventProposer
from living_world.agents.event_curator import promote_emergent, prune_tail
from living_world.agents.move_advisor import LLMMoveAdvisor
from living_world.agents.narrator import Narrator, NarratorBudget, NarratorStats
from living_world.agents.perception import SubjectivePerception
from living_world.agents.planner import AgentPlanner
from living_world.agents.reflector import MemoryReflector
from living_world.agents.self_update import AgentSelfUpdate

__all__ = [
    # narrator
    "Narrator",
    "NarratorBudget",
    "NarratorStats",
    # chronicler
    "Chronicler",
    "Chapter",
    # conscience
    "ConsciousnessLayer",
    "ConsciousVerdict",
    # dialogue / interaction
    "DialogueGenerator",
    # emergent
    "EmergentEventProposer",
    # event curator (rule-layer helpers, exposed here so callers can
    # use one import for the whole agent surface)
    "promote_emergent",
    "prune_tail",
    # movement
    "LLMMoveAdvisor",
    # perception / self
    "SubjectivePerception",
    "AgentSelfUpdate",
    # planning
    "AgentPlanner",
    # memory
    "MemoryReflector",
]
