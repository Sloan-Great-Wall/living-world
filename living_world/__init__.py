"""Living World Simulator — Stage A MVP.

Single source of truth for project-wide paths.
"""

from pathlib import Path

__version__ = "0.1.0"

# ──────────────────────────────────────────────────────────────
# Path constants — anything needing these imports from here.
# ──────────────────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parent.parent
PACKS_DIR = PROJECT_ROOT / "world_packs"
