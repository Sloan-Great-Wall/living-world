"""PyInstaller entry point for the bundled sidecar binary.

Lives in `scripts/` (NOT inside the `living_world` package) so the
PyInstaller frozen binary doesn't get confused about whether the
script is a module or a top-level entry. Loads the FastAPI app and
runs uvicorn against it; same env vars as the dev path
(`living_world.web.__main__`).

Why a separate script: when PyInstaller's onefile bootloader runs a
file that lives inside a package, the `__main__` resolution can
collide with package-relative imports. The dev path
(`python -m living_world.web`) works because Python's `-m` switch
sets up the module path correctly. PyInstaller does not — so we
hand it a script that has zero package-relative semantics.
"""

from __future__ import annotations

import os
import sys


def main() -> None:
    # File-based diagnostic so we can confirm the binary even started,
    # independent of how Tauri / shell handles stdio.
    diag = os.environ.get("LW_SIDECAR_DIAG_FILE", "")
    if diag:
        try:
            with open(diag, "a") as fh:
                fh.write("entry main() reached\n")
        except Exception:
            pass

    host = os.environ.get("LW_API_HOST", "127.0.0.1")
    port = int(os.environ.get("LW_API_PORT", "8765"))
    log_level = os.environ.get("LW_API_LOG_LEVEL", "warning")

    print(
        f"[lw-sidecar] booting on {host}:{port} (log_level={log_level})",
        flush=True,
    )

    try:
        import uvicorn

        from living_world.web.server import app
    except Exception as exc:  # pragma: no cover — bundle-import diagnostic
        print(f"[lw-sidecar] import failed: {exc!r}", flush=True, file=sys.stderr)
        raise

    try:
        uvicorn.run(app, host=host, port=port, log_level=log_level)
    except Exception as exc:
        print(f"[lw-sidecar] uvicorn exited: {exc!r}", flush=True, file=sys.stderr)
        raise


if __name__ == "__main__":
    main()
