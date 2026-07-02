# AGENTS.md

## Session Start

Read the latest handoff in `docs/summaries/` if one exists. Load only the files that handoff references — not all summaries. If no handoff exists, ask: what is the project, what type of work, what is the target deliverable.

For a quick orientation to the codebase (component map and data flow), read `docs/context/architecture.md` if present.

Before starting work, state: what you understand the project state to be, what you plan to do this session, and any open questions.

Before your first file edit, ensure you are not on `main`. If you are, create a feature branch (`git checkout -b <scope>-<short-desc>`, matching the commit scope convention in `docs/context/git-guide.md`). A `PreToolUse` hook backs this up by blocking edits to repo files while on `main` — but it exempts gitignored working files (session handoffs in `docs/summaries/`), so writing those on `main` needs no branch; only edits to tracked files trigger the branch requirement.

## Rules

1. **Write state to disk, not conversation.** Record work in the session handoff at `docs/summaries/handoff-[date]-[topic].md` using the Handoff template below — create it on first meaningful write and update it as work progresses, capturing decisions with rationale, exact numbers, file paths, and open items. Before compaction, before switching work types (research → writing → review), and at session end, do a full update: every number, every decision with rationale, every open question, every file path, and the exact next action — finalizing with `.claude/commands/handoff.md` (the `/handoff` command, or follow its steps directly if slash commands are unavailable). Do not create a separate recovery or checkpoint artifact.
2. **Do not silently resolve open questions.** Mark unresolved items as OPEN or ASSUMED in the handoff and in the final answer when relevant. Before delivering output, verify that exact numbers are preserved and that claims are backed by specific data.
3. Use `docs/context/processing-protocol.md` for multiple documents, large files, docs dumps, broad research, big diffs, incident traces, or broad codebase exploration. Targeted lookup in a few short files does not require source-summary overhead.
4. When sub-agents are used, their returns must be structured with exact numbers, file paths, decisions with rationale, and open items — not free-form prose. See `docs/context/subagent-rules.md`.
5. Before running any Python command or modifying dependencies, read `docs/context/uv-guide.md`.
6. Pre-commit hooks enforce format/lint/type/test checks at commit time — do not run them manually before committing, and never bypass them with `--no-verify`. When the pytest hook runs, review its coverage output — no new uncovered lines.
7. When you want to commit, see `docs/context/git-guide.md`. Follow-up fixes go into new commits — never amend, rebase, or otherwise rewrite an existing commit unless the user asks for that directly. Never stage `docs/summaries/` or `docs/archive/` (gitignored); under `docs/`, only `docs/context/` is tracked.
8. **Never `git push` on your own — a push happens only via the user invoking `/create-pr` or pushing it themselves.**
9. When changing code, update or add tests in the same PR. Treat test maintenance as mandatory — skipping it is equivalent to bypassing the pre-commit hooks in Rule 6.

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
