#!/bin/bash
# SessionStart hook: installs project deps and git hooks in Claude Code cloud sessions.
# The environment's setup script provisions the VM (Python 3.14, uv, pre-commit) but runs
# outside the repo, so anything that needs pyproject.toml or .git lives here instead.
# See "Cloud Sessions" in docs/context/uv-guide.md.
set -euo pipefail

[ "${CLAUDE_CODE_REMOTE:-}" = "true" ] || exit 0

cd "$CLAUDE_PROJECT_DIR"

# stdout of a SessionStart hook lands in Claude's context; keep the install noise in a log
exec >>"$HOME/session-start.log" 2>&1

uv sync --frozen
pre-commit install
pre-commit install-hooks || true
