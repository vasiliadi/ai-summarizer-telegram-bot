# AGENTS.md

## Session Start

Read the latest handoff in `docs/summaries/` if one exists. Load only the files that handoff references — not all summaries. If no handoff exists, ask: what is the project, what type of work, what is the target deliverable.

For a quick orientation to the codebase (component map and data flow), read `docs/context/architecture.md` if present.

Before starting work, state: what you understand the project state to be, what you plan to do this session, and any open questions.

Before your first file edit, ensure you are not on `main`. If you are, create a feature branch (`git checkout -b <scope>-<short-desc>`, matching the commit scope convention in `docs/context/git-guide.md`). A `PreToolUse` hook backs this up by blocking edits to repo files while on `main` — but it exempts gitignored working files (session handoffs in `docs/summaries/`), so writing those on `main` needs no branch; only edits to tracked files trigger the branch requirement.

## Rules

1. If the session pivots to an unrelated project or topic, do not absorb it: finalize the current handoff (Rule 4) and suggest a new session. One session = one context; `docs/summaries/` keeps one active handoff at a time.
2. Write state to disk, not conversation. After completing meaningful work, record it in the session handoff at `docs/summaries/handoff-[date]-[topic].md` using the Handoff template below — create it on first write, update it as work progresses. Include: decisions with rationale, exact numbers, file paths, open items.
3. Before compaction or session end, write to disk: every number, every decision with rationale, every open question, every file path, exact next action.
4. When switching work types (research → writing → review) or ending the session, finalize the handoff at `docs/summaries/handoff-[date]-[topic].md` using the Handoff template below (fill the optional tail) and suggest a new session.
5. Do not silently resolve open questions. Mark them OPEN or ASSUMED.
6. Do not bulk-read documents. Process one at a time: read, summarize to disk, release from context before reading next. For the detailed protocol, read `docs/context/processing-protocol.md`.
7. Sub-agent returns must be structured (numbers, file paths, decisions, open items), not free-form prose. See `docs/context/subagent-rules.md`.
8. Before running any Python command or modifying dependencies, read `docs/context/uv-guide.md`.
9. Before every commit, pass: `uvx ruff format .`, `uvx ruff check .`, `uvx ty check .`, `uv run pytest --cov`. Review the coverage report and do not introduce new uncovered lines. See `docs/context/git-guide.md` for the full sequence. Commit locally when a unit of work is complete, but **never `git push` until the user asks for that push** — no exceptions, and no inferring permission from context. An open PR on the branch, a review comment to address, a previous push, or a `/create-pr` earlier in the session do **not** authorize the next push; each push needs its own explicit request. Pushing triggers the GitHub code-review agent, and only the user decides when work is ready for it — when a commit is ready, say so and wait. When staging, remember that `docs/summaries/` and `docs/archive/` are gitignored (only `docs/context/` under `docs/` is tracked); never try to add or commit handoff or archive files.
10. When changing code, update or add tests in the same PR. Treat test maintenance as mandatory — skipping it is equivalent to skipping the pre-commit checks in Rule 9.

## Handoff Template

Write to `docs/summaries/handoff-[YYYY-MM-DD]-[topic].md`. Create it after the first meaningful work and update it as the session proceeds; when ending or switching the session, fill the optional tail and move the previous handoff to `docs/archive/handoffs/`.

```markdown
# Handoff: [Topic]
**Date:** [YYYY-MM-DD]  **Branch:** [branch]  **Focus:** [one sentence]

## What Was Accomplished
- [task] → `[file:line]`

## Decisions Made
- [decision] BECAUSE [rationale] — STATUS: [confirmed/provisional]

## Key Numbers
- [exact test counts, timings, values — do not round]

## Files Modified
| File | Action | Description |
|------|--------|-------------|
| `[path]` | Created/Modified | [what and why] |

## Open Questions
- [OPEN/ASSUMED item] or None

<!-- Optional tail — fill only when ending/switching the session (handoff): -->
## What the Next Session Should Do
1. [ordered, specific action with paths]

## Files to Load Next Session
- `[path]` — [why]

## What NOT to Re-Read
- `[path]` — already summarized in `[path]`
```

## Where Things Live

- `docs/summaries/` — active session state (latest handoff + project-digest + decision records + source summaries). **(gitignored — not committed)**
- `docs/context/` — reusable domain knowledge, loaded only when relevant to the current task. **(tracked in git)**
  - `architecture.md` — high-level component map and data flow. Stable; update only on architectural change, not every handoff.
  - `agent-templates.md` — decision, analysis, and source-summary templates (read on demand). The session handoff template lives inline in `AGENTS.md` above.
  - `processing-protocol.md` — full document processing steps
  - `archive-rules.md` — summary lifecycle and file archival rules
  - `style-guide.md` — writing or coding conventions
  - `git-guide.md` — git workflow and repository conventions
  - `uv-guide.md` — running the project and managing dependencies with `uv`
  - `subagent-rules.md` — rules for sub-agent usage and outputs
- `docs/archive/` — processed raw files. Do not read unless explicitly told. **(gitignored — not committed)**
- `.claude/commands/` — step-by-step routine for **handoff** (`handoff.md`). Claude Code exposes it as the `/handoff` slash command; agents without slash-command support should read that file and follow the steps directly.

## Error Recovery

If context degrades or auto-compact fires unexpectedly: do not try to reconstruct state from memory. Re-read the active handoff in `docs/summaries/` and verify its contents against the working tree (`git status`, `git log`) before continuing. Tell the user what may have been lost, and if the handoff is stale relative to the actual work, say so explicitly rather than guessing. If the handoff plus working tree cannot reconstruct reliable state, suggest a fresh session — the handoff exists precisely so a new session can pick up.

## Before Delivering Output

Verify: exact numbers preserved, open questions marked OPEN, output matches what was requested (not assumed), claims backed by specific data, output consistent with decision records in `docs/summaries/`, handoff written/updated to disk for this session's work.
