# Living World — single-command verification gate.
#
# AI-Native criterion C ("一键自验证"): one command, one exit code,
# <60s feedback. Every gate that protects merge-readiness runs here.
#
# Targets:
#   make check    — run every gate (lint + types + tests + build); CI uses this
#   make fix      — auto-fix what auto-fixers can (ruff format + ruff fix)
#   make py       — Python-only gates (faster, when only Python changed)
#   make ts       — TypeScript-only gates (faster, when only TS changed)
#   make smoke    — quick sim run (no LLM); seeds + invariants
#   make clean    — remove generated artefacts
#
# Convention: every recipe must exit 0 on success, non-zero on any failure.
# No `|| true` swallowing — that's how we keep AI loops trustworthy.
#
# Repo layout (Phase 1.5 monorepo):
#   living_world/              Python sim
#   tests/                     Python tests
#   packages/sim-core/         TS: dice + social metrics (Python parity)
#   dashboard-tauri/           TS: Solid UI + Tauri shell
#   tsconfig.base.json         shared TS compiler options
#   node_modules/              ONE tree (npm workspaces)
#   package.json               root workspace manifest

PY      := .venv/bin/python
PYTEST  := $(PY) -m pytest
RUFF    := $(PY) -m ruff
PYRIGHT := .venv/bin/basedpyright
# uv is ~15× faster than pip for resolve + install; installed INTO the venv
# so no system-level dep. Falls back to pip if uv missing (first-time bootstrap).
UV      := .venv/bin/uv

.PHONY: check fix py py-lint py-types py-tests ts ts-sim-core ts-dashboard ts-bundle ts-schema smoke clean help install schema schema-check build-sidecar build-app

help:
	@echo 'Living World — verification gates'
	@echo ''
	@echo '  make install        — npm install (root) + uv pip install -e .[dev]'
	@echo '  make check          — full gate (schema + lint + types + tests + build)'
	@echo '  make py             — Python-only (ruff + basedpyright + pytest)'
	@echo '  make ts             — TypeScript-only (schema + tsc + vitest + bundle)'
	@echo '  make schema         — regenerate OpenAPI + TS types'
	@echo '  make smoke          — quick rule-only sim run'
	@echo '  make fix            — auto-fix lint/format'
	@echo '  make build-sidecar  — PyInstaller bundles Python sim API for Tauri'
	@echo '  make build-app      — full prod app: build-sidecar + tauri build'
	@echo '  make clean          — remove caches + dist'

install:
	@# Use uv if available (30× faster resolve); fall back to pip otherwise.
	@if [ -x $(UV) ]; then \
		echo '── uv pip install -e .[dev] ──'; \
		$(UV) pip install -e '.[dev]' --quiet; \
	else \
		echo '── pip install -e .[dev] (uv not installed; run `pip install uv` to go faster) ──'; \
		$(PY) -m pip install -e '.[dev]' --quiet; \
	fi
	@echo '── npm install (workspaces) ──'
	@npm install --silent
	@echo '✓ installed'

check: py ts
	@echo ''
	@echo '✓ all gates passed'

# ── Python gates ──

py: py-lint py-types py-tests
	@echo '✓ python gates ok'

py-lint:
	@echo '── ruff (lint + format check) ──'
	@$(RUFF) check living_world tests
	@$(RUFF) format --check living_world tests

py-types:
	@echo '── basedpyright (strict type check) ──'
	@$(PYRIGHT) || (echo '✗ basedpyright reported issues'; exit 1)

py-tests:
	@echo '── pytest (unit + invariants + smoke; live LLM auto-skipped) ──'
	@$(PYTEST) -x -q --tb=short

# ── Cross-layer schema (Python Pydantic ─► TS types) ──
#
# `make schema`        — regenerate api-schema/openapi.json + api.generated.ts.
#                        Run after editing living_world/web/schemas.py; commit
#                        both files in the same change so reviewers see them.
# `make schema-check`  — verify the committed files match the live Python; CI
#                        gate. Drift means schemas changed without regen.

schema:
	@echo '── dump OpenAPI from FastAPI ──'
	@$(PY) scripts/dump_openapi.py
	@echo '── openapi-typescript ─► api.generated.ts ──'
	@npm run schema:gen --workspace=dashboard-tauri --silent
	@echo '✓ schema regenerated'

schema-check:
	@echo '── schema drift check ──'
	@$(PY) scripts/dump_openapi.py > /dev/null
	@if ! git diff --quiet -- api-schema/openapi.json; then \
		echo '✗ api-schema/openapi.json is stale — run `make schema` and commit'; \
		git --no-pager diff --stat api-schema/openapi.json; \
		exit 1; \
	fi
	@npm run schema:gen --workspace=dashboard-tauri --silent
	@if ! git diff --quiet -- dashboard-tauri/src/types/api.generated.ts; then \
		echo '✗ api.generated.ts is stale — run `make schema` and commit'; \
		exit 1; \
	fi

# ── TypeScript gates ──
#
# All TS tooling runs from the repo root; npm workspaces routes each
# command to the right package. No more `cd packages/... && npx ...`.

ts: ts-schema ts-sim-core ts-dashboard ts-bundle
	@echo '✓ typescript gates ok'

ts-schema: schema-check

ts-sim-core:
	@echo '── @living-world/sim-core: typecheck + parity ──'
	@npm run typecheck --workspace=@living-world/sim-core
	@npm run test      --workspace=@living-world/sim-core

ts-dashboard:
	@echo '── dashboard-tauri: typecheck + component tests + build ──'
	@npm run typecheck --workspace=dashboard-tauri
	@npm run test      --workspace=dashboard-tauri
	@npm run build     --workspace=dashboard-tauri > /tmp/lw-build.log 2>&1 \
		|| (cat /tmp/lw-build.log; exit 1)

ts-bundle:
	@echo '── dashboard-tauri: bundle-size budget ──'
	@npm run bundle:check --workspace=dashboard-tauri

# ── Convenience ──

smoke:
	@echo '── 6-tick rules-only smoke (no LLM) ──'
	@$(PYTEST) tests/test_simulation_invariants.py -q

fix:
	@$(RUFF) check --fix living_world tests
	@$(RUFF) format living_world tests
	@echo '✓ ruff auto-fixes applied'

clean:
	@rm -rf .pytest_cache .ruff_cache .basedpyright
	@rm -rf node_modules packages/*/node_modules dashboard-tauri/node_modules
	@rm -rf packages/*/dist dashboard-tauri/dist
	@rm -rf .pyinstaller-build dashboard-tauri/src-tauri/binaries
	@find . -name __pycache__ -type d -prune -exec rm -rf {} +
	@find . -name '*.pyc' -delete
	@echo '✓ cleaned'

# ── Production build (L-21) ──
#
# `make build-sidecar` produces `dashboard-tauri/src-tauri/binaries/
# lw-sidecar-<triple>{.exe}` via PyInstaller. Tauri then ships it as
# `bundle.externalBin`. Each platform has to run this on its own host
# (PyInstaller doesn't cross-compile cleanly).
#
# `make build-app` runs the full chain: sidecar build → tauri build,
# producing a signed-but-not-notarized `.app` / `.exe` / `.AppImage`
# in `dashboard-tauri/src-tauri/target/release/bundle/`.

build-sidecar:
	@echo '── PyInstaller: bundling Python sidecar ──'
	@$(PY) scripts/build_sidecar.py

build-app: build-sidecar
	@echo '── tauri build: producing platform .app/.exe ──'
	@npm run tauri --workspace=dashboard-tauri -- build
