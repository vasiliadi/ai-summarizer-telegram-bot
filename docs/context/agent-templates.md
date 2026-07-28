# Agent Templates — On-Demand Reference

> **Do NOT read this file at session start.** Read it only when writing a handoff or a Rule 3 overflow file.

---

## Template 1: Session Handoff

**Use when:** The user asks for a handoff. The steps around it — where to write, what to archive — are in `.claude/commands/handoff.md`.

**Write to:** `docs/summaries/handoff-[YYYY-MM-DD]-[topic].md`

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

---

## Template 2: Analysis (Rule 3 Overflow)

**Use when:** A sub-agent return exceeds the Rule 3 budget and goes to a file instead of into the reply. Keep only the latest version per topic (archive the old one if re-run).

**Write to:** `docs/summaries/analysis-[topic].md`

```markdown
# Analysis: [Topic]
**Date:** [YYYY-MM-DD]  **Scope:** [what was investigated]

## Core Finding
[one sentence]

## Findings
- WHAT: [finding] — EVIDENCE: [`file:line`, exact numbers — do not round] — SO WHAT: [why it matters here]

## Open Items
- [OPEN/ASSUMED item, or next step] or None
```
