"""Per-tick decay of needs and emotions — pure rule, no LLM.

Without this, LLM-set values would persist forever (anger from day 1
still at 80 on day 30). With this, the body brings the mind home.

Defaults are tuned to feel right for "1 tick = 1 day":
  - hunger ramps up daily (need food → motivates eating events later)
  - safety drifts toward neutral if nothing dangerous happens
  - emotions decay toward baseline (fear/anger fade unless reinforced)
"""

from __future__ import annotations

from living_world.core.world import World


# Per-tick increment for needs that grow when unmet.
# Positive = grows over time; absolute number is the daily delta.
NEED_GROWTH = {
    "hunger":  +12.0,   # gets hungry every day
    "safety":   -2.0,   # mild drift toward less-safe over time
}

# Emotions decay toward baseline. Per-tick fraction of distance from baseline
# that is removed. 0.30 means "fade 30% per day".
EMOTION_DECAY_RATE = 0.30
EMOTION_BASELINE = {
    "fear":  0.0,
    "joy":  30.0,
    "anger": 0.0,
}


def decay_needs_and_emotions(world: World) -> None:
    """Apply natural drift to every living agent's needs + emotions.

    Bounded between 0 and 100. Cheap (no LLM, no I/O) — runs every tick.
    """
    for agent in world.living_agents():
        needs = agent.get_needs()
        for key, delta in NEED_GROWTH.items():
            cur = needs.get(key, 50.0)
            needs[key] = max(0.0, min(100.0, cur + delta))

        emotions = agent.get_emotions()
        for key, baseline in EMOTION_BASELINE.items():
            cur = emotions.get(key, baseline)
            emotions[key] = cur + (baseline - cur) * EMOTION_DECAY_RATE


def auto_satisfy_routine_needs(world: World, rng) -> None:
    """When a need saturates, give the agent a chance to satisfy it routinely.

    Without this, hunger climbs to 100 and stays there forever — the signal
    loses information. With this, hungry agents have a 30% chance per tick
    to "eat" (hunger -= 60, small joy bump). Same shape for safety drift.

    No LegendEvent emitted: these are background body-keeping routines, not
    story moments. They show up in the agent card's needs panel as the bars
    going down, which is enough.
    """
    for agent in world.living_agents():
        needs = agent.get_needs()
        if needs["hunger"] > 80 and rng.random() < 0.3:
            agent.adjust_need("hunger", -60)
            agent.adjust_emotion("joy", +5)
        if needs["safety"] < 30 and rng.random() < 0.3:
            agent.adjust_need("safety", +40)  # found a safe spot
