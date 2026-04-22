"""Quantitative readouts on the world — social graphs, diversity, etc.

Pure-rule code. No LLM, no I/O. Useful for both runtime adjustments
(emergent heat targeting) and post-hoc analysis (chronicle quality).
"""
from living_world.metrics.social import (
    SocialMetrics,
    compute_social_metrics,
    affinity_graph,
)

__all__ = ["SocialMetrics", "compute_social_metrics", "affinity_graph"]
