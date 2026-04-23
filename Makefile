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

PY      := .venv/bin/python
PYTEST  := $(PY) -m pytest
RUFF    := $(PY) -m ruff
PYRIGHT := .venv/bin/basedpyright

# `cd` per recipe so each line runs in the intended dir under make's
# default `-c` shell. Avoids state leaking between targets.

.PHONY: check fix py ts smoke clean help

help:
	@echo 'Living World — verification gates'
	@echo ''
	@echo '  make check   — full gate (lint + types + tests + build)'
	@echo '  make py      — Python-only (ruff + basedpyright + pytest)'
	@echo '  make ts      — TypeScript-only (tsc + vitest + bundle)'
	@echo '  make smoke   — quick rule-only sim run'
	@echo '  make fix     — auto-fix lint/format'
	@echo '  make clean   — remove caches + dist'

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

ts: ts-sim-core ts-dashboard ts-bundle
	@echo '✓ typescript gates ok'

ts-sim-core:
	@echo '── @living-world/sim-core: typecheck + parity ──'
	@cd packages/sim-core && npx tsc --noEmit
	@cd packages/sim-core && npx vitest run

ts-dashboard:
	@echo '── dashboard-tauri: typecheck + build ──'
	@cd dashboard-tauri && npx tsc --noEmit
	@cd dashboard-tauri && npm run build > /tmp/lw-build.log 2>&1 \
		|| (cat /tmp/lw-build.log; exit 1)

ts-bundle:
	@echo '── dashboard-tauri: bundle-size budget ──'
	@cd dashboard-tauri && npm run bundle:check

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
	@rm -rf packages/sim-core/node_modules dashboard-tauri/node_modules
	@rm -rf packages/sim-core/dist dashboard-tauri/dist
	@find . -name __pycache__ -type d -prune -exec rm -rf {} +
	@find . -name '*.pyc' -delete
	@echo '✓ cleaned'
