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
    "hunger":    +12.0,   # gets hungry every day
    "safety":    -2.0,    # mild drift toward less-safe over time
    "belonging":  -1.0,   # social need slowly grows (negative drift)
    "esteem":     -0.5,
    "autonomy":   -0.5,
}

# Emotions decay toward baseline. Per-tick fraction of distance from baseline
# that is removed. 0.30 means "fade 30% per day".
EMOTION_DECAY_RATE = 0.30
EMOTION_BASELINE = {
    "fear":     0.0,
    "joy":      30.0,
    "anger":    0.0,
    "sadness":  0.0,
    "surprise": 0.0,
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
