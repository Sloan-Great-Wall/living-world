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

.PHONY: check fix py py-lint py-types py-tests ts ts-sim-core ts-dashboard ts-bundle smoke clean help install

help:
	@echo 'Living World — verification gates'
	@echo ''
	@echo '  make install — npm install (root workspace) + pip install -e .[dev]'
	@echo '  make check   — full gate (lint + types + tests + build)'
	@echo '  make py      — Python-only (ruff + basedpyright + pytest)'
	@echo '  make ts      — TypeScript-only (tsc + vitest + bundle)'
	@echo '  make smoke   — quick rule-only sim run'
	@echo '  make fix     — auto-fix lint/format'
	@echo '  make clean   — remove caches + dist'

install:
	@echo '── pip install -e .[dev] ──'
	@$(PY) -m pip install -e '.[dev]' --quiet
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

# ── TypeScript gates ──
#
# All TS tooling runs from the repo root; npm workspaces routes each
# command to the right package. No more `cd packages/... && npx ...`.

ts: ts-sim-core ts-dashboard ts-bundle
	@echo '✓ typescript gates ok'

ts-sim-core:
	@echo '── @living-world/sim-core: typecheck + parity ──'
	@npm run typecheck --workspace=@living-world/sim-core
	@npm run test      --workspace=@living-world/sim-core

ts-dashboard:
	@echo '── dashboard-tauri: typecheck + build ──'
	@npm run typecheck --workspace=dashboard-tauri
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
	@find . -name __pycache__ -type d -prune -exec rm -rf {} +
	@find . -name '*.pyc' -delete
	@echo '✓ cleaned'
