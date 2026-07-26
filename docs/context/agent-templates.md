# Agent Templates — On-Demand Reference

> **Do NOT read this file at session start.** Read it only when writing a decision record or an analysis summary. The session handoff template lives inline in `AGENTS.md`.

---

## Template 1: Decision Record

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

## Template 2: Analysis / Research Summary

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
