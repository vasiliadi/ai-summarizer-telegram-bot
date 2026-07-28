# Agent Templates — On-Demand Reference

> **Do NOT read this file at session start.** Read it only when writing a handoff, a decision record, or an analysis summary.

---

## Template 1: Session Handoff

**Use when:** The user asks for one (`/handoff`). It is a history log — never created or updated while work is in progress.

**Write to:** `docs/summaries/handoff-[YYYY-MM-DD]-[topic].md` — then move the previous handoff, if one is there, to `docs/archive/handoffs/`.

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

## Template 2: Decision Record

**Use when:** A significant decision is made during a session (library choice, architecture, migration strategy, error-handling approach). These persist in `docs/summaries/` as the project's ADRs.

**Write to:** `docs/summaries/decision-[number]-[topic].md`

```markdown
# Decision [N]: [Short Title] ([ticket if any])
**Date:** [YYYY-MM-DD]  **Branch:** [branch]  **Issue:** [link/id, if any]

## Problem
[2-3 sentences: what situation prompted this decision]

## Decision
[One clear statement of what was decided]
- CHOSE [option] BECAUSE [specific reason] — STATUS: [confirmed (user) / provisional]
- REJECTED [alternative] BECAUSE [specific reason]

## Files Modified
| File | Change |
|------|--------|
| `[path]` | [what changed] |

## Verification
- pre-commit hooks at commit time — [result]
- pytest hook — [exact pass count, e.g. **207 passed**; no new uncovered lines]

## Open Items
- [next step / unresolved item] or None
```

---

## Template 3: Analysis / Research Summary

**Use when:** Completing a technical evaluation, feasibility check, incident investigation, or refactor scoping. Keep only the latest version per topic (archive the old one if re-run).

**Write to:** `docs/summaries/analysis-[topic].md`

```markdown
# Analysis Summary: [Topic]
**Completed:** [YYYY-MM-DD]
**Analysis Type:** [technical / feasibility / incident / refactor]
**Sources Used:** [file paths or URLs]
**Confidence:** [high / medium / low — and WHY]

## Core Finding (One Sentence)
[Single sentence: the most important conclusion]

## Evidence Base
<!-- Specific data points. Exact values only — do not round. -->
| Data Point | Value | Source | Date of Data |
|-----------|-------|--------|-------------|
| [metric]  | [exact value] | [source] | [date] |

## Detailed Findings
### Finding 1: [Name]
- WHAT: [the finding]
- SO WHAT: [why it matters for this project]
- EVIDENCE: [specific supporting data, file:line]
- CONFIDENCE: [high/medium/low]

## Recommended Next Steps
1. [action] — priority [high/medium/low], depends on [what]
```
