# AGENTS.md

## Session Start

Read the latest handoff in `docs/summaries/` if one exists, loading only the files it references. If no handoff exists, ask: what is the project, what type of work, what is the target deliverable.

For codebase orientation read `docs/context/architecture.md`; before writing code also read `docs/context/style-guide.md` for the conventions Ruff does not enforce.

Then state: what you understand the project state to be, what you plan to do this session, and any open questions.

Before your first edit to a tracked file, branch off `main` (`git checkout -b <scope>-<short-desc>`, matching the commit scope convention in `docs/context/git-guide.md`). A `PreToolUse` hook enforces this; gitignored files such as handoffs in `docs/summaries/` are exempt.

## Rules

1. **Write state to disk, not conversation.** Record work in the session handoff at `docs/summaries/handoff-[YYYY-MM-DD]-[topic].md` using the Handoff template below — create it on first meaningful write, update it as work progresses. Before compaction, before switching work types, and at session end, do a full update: every number, decision with rationale, open question, file path, and the exact next action — finalizing with `.claude/commands/handoff.md` (the `/handoff` command, or its steps directly). The handoff is the only session-state artifact; decision records and analyses are separate outputs.
2. **Surface every open question.** Mark unresolved items OPEN or ASSUMED in the handoff and in the final answer. Before delivering output, verify exact numbers are preserved and claims are backed by specific data.
3. For docs dumps, big diffs, incident traces, or broad codebase exploration, summarize to `docs/summaries/` as you go instead of holding raw content in context. Targeted lookup in a few short files needs no such overhead.
4. Sub-agent returns must be structured — exact numbers, file paths, decisions with rationale, open items — not free-form prose. Target 1,000–2,000 tokens.
5. Before running any Python command or modifying dependencies, read `docs/context/uv-guide.md`.
6. Commit per `docs/context/git-guide.md`, which also covers the pre-commit hooks and the coverage report. Never bypass hooks with `--no-verify`. Follow-up fixes go into new commits — never amend, rebase, or otherwise rewrite an existing commit unless the user asks for that directly. Under `docs/`, stage only `docs/context/` — the rest is gitignored.
7. **Never `git push` on your own — a push happens only via the user invoking `/create-pr` or pushing it themselves.**
8. A code change updates its tests **and** any `docs/context/` doc it invalidates (`architecture.md` for architecture, `style-guide.md` for conventions) in the same PR. Treat both as mandatory — skipping either is equivalent to bypassing the pre-commit hooks.

## Handoff Template

Fill the optional tail when ending or switching the session, then move the previous handoff to `docs/archive/handoffs/`.

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

- `docs/summaries/` — session outputs: the handoff (session state), decision records, analyses. **(gitignored)**
- `docs/context/` — reusable domain knowledge, loaded only when relevant. **(tracked)**
  - `architecture.md` — component map and data flow; update only on architectural change
  - `style-guide.md` — coding conventions Ruff does not enforce
  - `git-guide.md` — commit format, pre-commit hooks, coverage
  - `uv-guide.md` — running the project and managing dependencies
  - `agent-templates.md` — decision-record and analysis templates (read on demand)
- `docs/archive/` — processed raw files. Do not read unless explicitly told. **(gitignored)**
- `.claude/commands/handoff.md` — the `/handoff` routine; agents without slash commands follow its steps directly.
