"""Build the Python sidecar binary that Tauri ships in production.

Output: a single executable produced by PyInstaller that runs uvicorn
against `living_world.web.server:app`. Dropped under
`dashboard-tauri/src-tauri/binaries/` with the platform-specific
target-triple suffix Tauri expects (e.g.
`lw-sidecar-aarch64-apple-darwin`).

L-21 scope (this script):
  - macOS / Linux / Windows local builds
  - Single-file binary (`--onefile`)
  - All Python deps bundled (uvicorn, fastapi, pydantic, …)
  - World-pack YAML + settings.yaml shipped via `--add-data`

Out of scope (future):
  - Code signing / notarization (macOS Apple Developer cert required)
  - Cross-compilation (each target platform builds on its own host)
  - Universal2 binary on macOS (build separately + lipo)
  - Smaller binaries via `--exclude-module` audit
"""

from __future__ import annotations

import platform
import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
BINARIES_DIR = REPO_ROOT / "dashboard-tauri" / "src-tauri" / "binaries"
ENTRY = REPO_ROOT / "scripts" / "lw_sidecar_entry.py"


def detect_target_triple() -> str:
    """Return the Rust-style target triple for the current host.

    Tauri expects sidecar binaries named `<base>-<triple>{.exe}`. The
    triple-format strings are stable across Tauri versions.
    """
    machine = platform.machine().lower()
    system = platform.system()
    if system == "Darwin":
        if machine in ("arm64", "aarch64"):
            return "aarch64-apple-darwin"
        return "x86_64-apple-darwin"
    if system == "Linux":
        if machine in ("aarch64", "arm64"):
            return "aarch64-unknown-linux-gnu"
        return "x86_64-unknown-linux-gnu"
    if system == "Windows":
        if machine in ("aarch64", "arm64"):
            return "aarch64-pc-windows-msvc"
        return "x86_64-pc-windows-msvc"
    raise RuntimeError(f"unsupported platform: {system} {machine}")


def main() -> int:
    triple = detect_target_triple()
    is_windows = triple.endswith("windows-msvc")
    suffix = ".exe" if is_windows else ""
    out_name = f"lw-sidecar-{triple}{suffix}"

    BINARIES_DIR.mkdir(parents=True, exist_ok=True)

    print(f"[build] target triple: {triple}")
    print(f"[build] output:        {BINARIES_DIR}/{out_name}")
    print(f"[build] entry:         {ENTRY.relative_to(REPO_ROOT)}")

    # Cargo's `tauri build` reads the binary directly from `binaries/`;
    # PyInstaller writes to `dist/` by default, so we relocate after.
    work_dir = REPO_ROOT / ".pyinstaller-build"
    dist_dir = work_dir / "dist"
    work_dir.mkdir(parents=True, exist_ok=True)

    # Pack data limitation (L-21 MVP scope):
    #
    # PyInstaller `--add-data` for the full `world_packs/` tree caused
    # the bundled binary to hang at startup with no Python output at
    # all (verified 2026-04-26 with PyInstaller 6.20). A minimal hello-
    # world bundle works fine; adding `--add-data` for ~30 YAML files
    # silently breaks startup. Root cause not yet diagnosed.
    #
    # MVP workaround: ship YAML data OUTSIDE the binary. The Tauri
    # sidecar spawns the binary with `cwd = repo_root` (dev) or
    # `cwd = resource_dir` (prod) so `Path('world_packs')` resolves.
    # Tauri's `bundle.resources` will copy the directory next to the
    # `.app` in production.
    #
    # Follow-up tracked in KNOWN_ISSUES.md L-21:
    #   * diagnose --add-data hang on macOS aarch64
    #   * once fixed, embed world_packs in the binary so the sim is
    #     truly self-contained
    sep = ";" if is_windows else ":"
    add_data_args: list[str] = []
    _ = sep  # placeholder for cross-platform separator once we re-enable

    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--onefile",
        "--name", f"lw-sidecar-{triple}",
        "--distpath", str(dist_dir),
        "--workpath", str(work_dir / "build"),
        "--specpath", str(work_dir),
        "--clean",
        "--noconfirm",
        # Hidden imports that PyInstaller's static analysis misses.
        # uvicorn picks workers + protocols dynamically; without these
        # the bundled binary crashes on first request.
        "--hidden-import=uvicorn.protocols.http.h11_impl",
        "--hidden-import=uvicorn.protocols.http.httptools_impl",
        "--hidden-import=uvicorn.protocols.websockets.wsproto_impl",
        "--hidden-import=uvicorn.protocols.websockets.websockets_impl",
        "--hidden-import=uvicorn.lifespan.on",
        "--hidden-import=uvicorn.loops.asyncio",
        "--hidden-import=uvicorn.loops.auto",
        # Pull the sim's whole package tree in by name so PyInstaller
        # doesn't try to be clever with conditional imports inside it.
        "--collect-submodules=living_world",
        # YAML world-pack loader uses pyyaml's C accelerator if present.
        "--collect-submodules=yaml",
        *add_data_args,
        str(ENTRY),
    ]
    print(f"[build] running: {' '.join(cmd)}")
    rc = subprocess.call(cmd)
    if rc != 0:
        print(f"[build] PyInstaller exited {rc}", file=sys.stderr)
        return rc

    # Move the produced binary into place.
    src = dist_dir / f"lw-sidecar-{triple}{suffix}"
    dst = BINARIES_DIR / out_name
    if not src.exists():
        print(f"[build] expected output missing: {src}", file=sys.stderr)
        return 2
    shutil.move(str(src), str(dst))
    if not is_windows:
        dst.chmod(0o755)
    print(f"[build] ✓ wrote {dst.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
