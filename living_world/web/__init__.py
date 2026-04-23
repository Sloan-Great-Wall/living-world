"""Thin sim REST API consumed by the Tauri+Solid+TS dashboard.

Boot via `lw serve` (CLI) or directly:
    uvicorn living_world.web.server:app --reload --port 8000

The Tauri/Vite frontend at http://localhost:1420 calls this server at
http://localhost:8000. CORS is permissive for the dev origin.
"""
from living_world.web.server import app, create_app

__all__ = ["app", "create_app"]
