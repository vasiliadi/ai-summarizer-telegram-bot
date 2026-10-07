#!/bin/bash
# Claude Code SessionStart hook for cloud sessions; see "Cloud Sessions" in docs/context/uv-guide.md.
set -euo pipefail

[ "${CLAUDE_CODE_REMOTE:-}" = "true" ] || exit 0

cd "$CLAUDE_PROJECT_DIR"

# stdout of a SessionStart hook lands in Claude's context; keep the install noise in a log
exec >>"$HOME/session-start.log" 2>&1

# git hooks first: a failed uv sync must not leave commits unchecked
pre-commit install
pre-commit install-hooks || true
uv sync --frozen
