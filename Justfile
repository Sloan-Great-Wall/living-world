# Living World — `just` aliases mirroring the Makefile.
#
# Both `make check` and `just check` exist; pick whichever your shell
# prefers. Justfile is convention in vibe-coder circles (D ★★★★),
# Makefile is universal (every Mac/Linux ships it).
#
# Both delegate to the same npm/pytest commands so they cannot drift.

# Default: print available targets when no arg.
default:
    @just --list

# Full gate
check:
    @make check

# Auto-fix lint/format
fix:
    @make fix

# Python-only gates
py:
    @make py

# TypeScript-only gates
ts:
    @make ts

# 6-tick rules-only smoke
smoke:
    @make smoke

clean:
    @make clean
