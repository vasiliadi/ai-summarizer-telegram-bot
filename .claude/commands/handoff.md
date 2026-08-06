Write a session handoff file for the current session.

Steps:

1. Fill in every section of the template below based on what was accomplished in this session, including the forward-looking tail (Unfinished Work / Files to Load Next Session / What NOT to Re-Read). Be specific — include exact file paths for every output, exact numbers discovered, and conditional logic established.
2. Write the handoff to `docs/summaries/handoff-[YYYY-MM-DD]-[topic].md`.
3. If a previous handoff file exists in `docs/summaries/`, move it to `docs/archive/handoffs/`.
4. Tell me the file path of the new handoff and summarize what it contains.

Under What NOT to Re-Read list the handoffs, plans, and analyses this session actually opened that a later reader should skip, naming what replaces each — a reason to *read* something belongs in Files to Load instead.

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

## Unfinished Work
- [ordered, specific action with paths] or None

## Files to Load Next Session
- `[path]` — [what it holds and when it matters; add `~L[start]-[end]` if only one region does]

## What NOT to Re-Read
- `[path]` — superseded by / already summarized in / unrelated to `[path]`
```
