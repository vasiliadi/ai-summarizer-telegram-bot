# Agent Templates — On-Demand Reference

> **Do NOT read this file at session start.** Read it only when you need to write a decision record, analysis summary, or source-document summary. The session handoff template lives inline in AGENTS.md — not here.

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

## Conditional Conclusions
- IF [condition], THEN [conclusion], BECAUSE [evidence]
- IF [alternative condition], THEN [different conclusion]

## What This Analysis Does NOT Cover
- [topic not addressed / data not available]

## Recommended Next Steps
1. [action] — priority [high/medium/low], depends on [what]
```

---

## Template 3: Source Document Summary

**Use when:** Processing an external docs dump — library API docs, RFCs, migration guides, changelogs — before adopting or upgrading a dependency. Replaces the raw document; see `docs/context/processing-protocol.md`.

**Write to:** `docs/summaries/source-[library]-[topic].md`

```markdown
# Source Summary: [Document Name]
**Processed:** [YYYY-MM-DD]
**Source:** [path or URL]
**Type:** [library docs / RFC / changelog / migration guide]
**Confidence:** [high = understood everything / medium = some interpretation / low = gaps]

## Exact Numbers & Facts
<!-- Copy every version, limit, timeout, default exactly. Do NOT round or paraphrase. -->
- [item]: [exact value] (section ref if available)

## Key Points
- [fact] — [section ref]

## Open Questions
- [UNCLEAR / MISSING item] — needs [what] or None
```

---

## End of Templates

**Return to your task after reading the template you need. Do not keep this file in active context.**
