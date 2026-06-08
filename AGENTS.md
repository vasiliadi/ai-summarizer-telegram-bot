# AGENTS.md

## Session Start

Read the latest handoff in docs/summaries/ if one exists. Load only the files that handoff references — not all summaries. If no handoff exists, ask: what is the project, what type of work, what is the target deliverable.

Before starting work, state: what you understand the project state to be, what you plan to do this session, and any open questions.

## Rules

1. Do not mix unrelated project contexts in one session.
2. Write state to disk, not conversation. After completing meaningful work, write a summary to docs/summaries/ using the Session Summary/Handoff template below. Include: decisions with rationale, exact numbers, file paths, open items.
3. Before compaction or session end, write to disk: every number, every decision with rationale, every open question, every file path, exact next action.
4. When switching work types (research → writing → review), write a handoff to docs/summaries/handoff-[date]-[topic].md using the Session Summary/Handoff template below (fill the optional tail) and suggest a new session.
5. Do not silently resolve open questions. Mark them OPEN or ASSUMED.
6. Do not bulk-read documents. Process one at a time: read, summarize to disk, release from context before reading next. For the detailed protocol, read docs/context/processing-protocol.md.
7. Sub-agent returns must be structured (numbers, file paths, decisions, open items), not free-form prose. See `docs/context/subagent-rules.md`.
8. Before running any Python command or modifying dependencies, read `docs/context/uv-guide.md`.
9. Before every commit, pass: `ruff format .`, `ruff check .`, `ty check .`, `uv run pytest`. See `docs/context/git-guide.md` for the full sequence.
10. When changing code, update or add tests in the same PR. Treat test maintenance as mandatory — skipping it is equivalent to skipping the pre-commit checks in Rule 9.

## Session Summary / Handoff Template

Write to `docs/summaries/summary-[YYYY-MM-DD]-[topic].md` after meaningful work, or `handoff-[YYYY-MM-DD]-[topic].md` when ending/switching the session — then fill the optional tail and move the previous handoff to `docs/archive/handoffs/`.

```markdown
# [Summary | Handoff]: [Topic]
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

- templates/claude-templates.md — decision, analysis, source-summary templates (read on demand). The session summary/handoff template lives inline in AGENTS.md above.
- docs/summaries/ — active session state (latest handoff + project-digest + decision records + source summaries)
- docs/context/ — reusable domain knowledge, loaded only when relevant to the current task
  - processing-protocol.md — full document processing steps
  - archive-rules.md — summary lifecycle and file archival rules
  - tech-stack.md — architecture decisions
  - style-guide.md — writing or coding conventions
  - project-structure.md — repository layout reference
  - git-guide.md — git workflow and repository conventions
  - tooling-guide.md — developer tools and how to run them
  - uv-guide.md — running the project and managing dependencies with `uv`
  - subagent-rules.md — rules for sub-agent usage and outputs
- docs/archive/ — processed raw files. Do not read unless explicitly told.
- output/deliverables/ — final outputs

## Error Recovery

If context degrades or auto-compact fires unexpectedly: write current state to docs/summaries/recovery-[date].md, tell the user what may have been lost, suggest a fresh session.

## Before Delivering Output

Verify: exact numbers preserved, open questions marked OPEN, output matches what was requested (not assumed), claims backed by specific data, output consistent with stored decisions in docs/context/, summary written to disk for this session's work.
