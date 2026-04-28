"""Entry point for `python -m living_world.web`.

Launches uvicorn against the FastAPI app on a fixed host/port. This
exists so PyInstaller can bundle a single binary that "just runs the
sim API" without importing uvicorn from the user's environment.

The Tauri sidecar (`dashboard-tauri/src-tauri/src/lib.rs`) prefers the
PyInstaller binary in production and falls back to running this module
via the project venv in dev. Both paths invoke the same uvicorn boot,
so behaviour is identical regardless of how the sidecar was launched.
"""

from __future__ import annotations

import os
import sys

import uvicorn


def main() -> None:
    host = os.environ.get("LW_API_HOST", "127.0.0.1")
    port = int(os.environ.get("LW_API_PORT", "8765"))
    log_level = os.environ.get("LW_API_LOG_LEVEL", "warning")

    # Banner so the Tauri sidecar log shows the binary actually started.
    # This is the only thing that prints unconditionally — uvicorn at
    # warning level is otherwise silent until a request lands.
    print(f"[lw-sidecar] booting on {host}:{port} (log_level={log_level})", flush=True)

    # Pass the imported app object directly instead of the
    # `"package.module:app"` import string. PyInstaller's frozen
    # imports work for explicit imports but not always for
    # uvicorn's late-resolved string-based import — so we sidestep.
    from living_world.web.server import app

    try:
        uvicorn.run(app, host=host, port=port, log_level=log_level)
    except Exception as exc:
        print(f"[lw-sidecar] uvicorn exited: {exc}", flush=True, file=sys.stderr)
        raise


if __name__ == "__main__":
    main()
