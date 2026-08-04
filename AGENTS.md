# AGENTS.md

## Session Start

Handoffs in `docs/summaries/` and `docs/archive/handoffs/` are a work log, not session context — never load one on your own. When the user points at previous work, read every handoff they name, then follow each one's Files to Load Next Session and skip whatever its What NOT to Re-Read lists.

Read `docs/context/architecture.md` before touching code, and `docs/context/style-guide.md` before writing code, for the conventions Ruff does not enforce. Docs-only work needs neither.

Then state what you plan to do this session and any open questions.

Before your first edit to a tracked file, branch off `main` (`git checkout -b <scope>-<short-desc>`, matching the commit scope convention in `docs/context/git-guide.md`). A `PreToolUse` hook enforces this; gitignored files such as handoffs in `docs/summaries/` are exempt.

## Rules

1. **The handoff is a history log, written on demand.** Do not create or update it while work is in progress — write it only when the user asks, by following `.claude/commands/handoff.md` (the `/handoff` command, or its steps directly). Rule 3 overflow files are a separate output — template in `docs/context/agent-templates.md`.
2. **Surface every open question.** Mark unresolved items OPEN or ASSUMED in the final answer, and in the handoff when one is written. Before delivering output, verify exact numbers are preserved and claims are backed by specific data.
3. Sub-agent returns must be structured — exact numbers, file paths, decisions with rationale, open items — not free-form prose. Target 1,000–2,000 tokens per return; write anything longer to `docs/summaries/analysis-<topic>.md` and return the path.
4. Before running any Python command or modifying dependencies, read `docs/context/uv-guide.md`.
5. Commit per `docs/context/git-guide.md`, which also covers the pre-commit hooks and the coverage report. Never bypass hooks with `--no-verify`. Follow-up fixes go into new commits — never amend, rebase, or otherwise rewrite an existing commit unless the user asks for that directly. Under `docs/`, stage only `docs/context/` — the rest is gitignored.
6. **Never `git push` unprompted** — only on `/create-pr` or a direct ask to push, one push each, then spent. Otherwise commit locally and report it ready.
7. A code change updates its tests **and** any `docs/context/` doc it invalidates (`architecture.md` for architecture, `style-guide.md` for conventions) in the same PR. Treat both as mandatory — skipping either is equivalent to bypassing the pre-commit hooks.

## Where Things Live

- `docs/summaries/` — session outputs: handoffs (`handoff-*.md`, work log) and Rule 3 overflow analyses (`analysis-*.md`). **(gitignored)**
- `docs/context/` — reusable domain knowledge, loaded only when relevant. **(tracked)**
  - `architecture.md` — component map and data flow; update only on architectural change
  - `style-guide.md` — coding conventions Ruff does not enforce
  - `git-guide.md` — commit format, pre-commit hooks, coverage
  - `uv-guide.md` — running the project and managing dependencies
  - `agent-templates.md` — handoff and analysis (Rule 3 overflow) templates (read on demand)
- `docs/archive/` — processed raw files. Do not read unless explicitly told. **(gitignored)**
- `.claude/commands/handoff.md` — the `/handoff` routine; agents without slash commands follow its steps directly.
