# Claude Templates — On-Demand Reference

> **Do NOT read this file at session start.** Read it only when you need to write a summary, handoff, decision record, or subagent output. This file is referenced from AGENTS.md.

---

## Template 1: Source Document Summary

**Use when:** Processing any input document (client brief, research report, requirements doc, existing proposal)

**Write to:** `./docs/summaries/source-[filename].md`

```markdown
# Source Summary: [Original Document Name]
**Processed:** [YYYY-MM-DD]
**Source Path:** [exact file path]
**Archived From:** [original path, if moved to docs/archive/]
**Document Type:** [brief / requirements / research / proposal / transcript / other]
**Confidence:** [high = I understood everything / medium = some interpretation needed / low = significant gaps]

## Exact Numbers & Metrics
<!-- List EVERY specific number, dollar amount, percentage, date, count, measurement.
     Do NOT round. Do NOT paraphrase. Copy exactly as stated in source. -->
- [metric]: [exact value] (page/section reference if available)
- [metric]: [exact value]

## Key Facts (Confirmed)
<!-- Only include facts explicitly stated in the document. Tag source. -->
- [fact] — stated in [section/page]
- [fact] — stated in [section/page]

## Requirements & Constraints
<!-- Use IF/THEN/BUT/EXCEPT format to preserve conditional logic -->
- REQUIREMENT: [what is needed]
  - CONDITION: [when/if this applies]
  - CONSTRAINT: [limitation or exception]
  - PRIORITY: [must-have / should-have / nice-to-have / stated by whom]

## Decisions Referenced
<!-- Any decisions mentioned in the document -->
- DECISION: [what was decided]
  - RATIONALE: [why, as stated in document]
  - ALTERNATIVES MENTIONED: [what else was considered]
  - DECIDED BY: [who, if stated]

## Relationships to Other Documents
<!-- How this document connects to other known project documents -->
- SUPPORTS: [other document/decision it reinforces]
- CONTRADICTS: [other document/decision it conflicts with]
- DEPENDS ON: [other document/decision it requires]
- UPDATES: [other document/decision it supersedes]

## Open Questions & Ambiguities
<!-- Things that are NOT resolved in this document -->
- UNCLEAR: [what is ambiguous] — needs clarification from [whom]
- ASSUMED: [interpretation made] — verify with [whom]
- MISSING: [information referenced but not provided]

## Verbatim Quotes Worth Preserving
<!-- 2-5 direct quotes that capture stakeholder language, priorities, or constraints
     These are critical for proposals — use the client's own words back to them -->
- "[exact quote]" — [speaker/author], [context]
```

---

## Template 2: Analysis / Research Summary

**Use when:** Completing competitive analysis, market research, technical evaluation

**Write to:** `./docs/summaries/analysis-[topic].md`

```markdown
# Analysis Summary: [Topic]
**Completed:** [YYYY-MM-DD]
**Analysis Type:** [competitive / market / technical / financial / feasibility]
**Sources Used:** [list source paths or URLs]
**Confidence:** [high / medium / low — and WHY this confidence level]

## Core Finding (One Sentence)
[Single sentence: the most important conclusion]

## Evidence Base
<!-- Specific data points supporting the finding. Exact numbers only. -->
| Data Point | Value | Source | Date of Data |
|-----------|-------|--------|-------------|
| [metric]  | [exact value] | [source] | [date] |

## Detailed Findings
### Finding 1: [Name]
- WHAT: [the finding]
- SO WHAT: [why it matters for this project]
- EVIDENCE: [specific supporting data]
- CONFIDENCE: [high/medium/low]

### Finding 2: [Name]
[same structure]

## Conditional Conclusions
<!-- Use IF/THEN format -->
- IF [condition], THEN [conclusion], BECAUSE [evidence]
- IF [alternative condition], THEN [different conclusion]

## What This Analysis Does NOT Cover
<!-- Explicit scope boundaries to prevent future sessions from over-interpreting -->
- [topic not addressed and why]
- [data not available]

## Recommended Next Steps
1. [action] — priority [high/medium/low], depends on [what]
2. [action]
```

---

## Template 3: Decision Record

**Use when:** Any significant decision is made during a session

**Write to:** `./docs/summaries/decision-[number]-[topic].md`

```markdown
# Decision Record: [Short Title]
**Decision ID:** DR-[sequential number]
**Date:** [YYYY-MM-DD]
**Status:** CONFIRMED / PROVISIONAL / REQUIRES_VALIDATION

## Decision
[One clear sentence: what was decided]

## Context
[2-3 sentences: what situation prompted this decision]

## Rationale
- CHOSE [option] BECAUSE: [specific reasons with data]
- REJECTED [alternative 1] BECAUSE: [specific reasons]
- REJECTED [alternative 2] BECAUSE: [specific reasons]

## Quantified Impact
- [metric affected]: [expected change with numbers]
- [cost/time/resource implication]: [specific figures]

## Conditions & Constraints
- VALID IF: [conditions under which this decision holds]
- REVISIT IF: [triggers that should cause reconsideration]
- DEPENDS ON: [upstream decisions or facts this relies on]

## Stakeholder Input
- [name/role]: [their stated position, if known]

## Downstream Effects
- AFFECTS: [what other decisions, documents, or deliverables this impacts]
- REQUIRES UPDATE TO: [specific files or deliverables that need revision]
```

---

## Template 4: Session Handoff

**Use when:** A session is ending (context limit approaching OR phase complete)

**Write to:** `./docs/summaries/handoff-[YYYY-MM-DD]-[topic].md`

**LIFECYCLE**: After writing a new handoff, move the PREVIOUS handoff to `docs/archive/handoffs/`.

```markdown
# Session Handoff: [Topic]
**Date:** [YYYY-MM-DD]
**Session Duration:** [approximate]
**Session Focus:** [one sentence]
**Context Usage at Handoff:** [estimated percentage if known]

## What Was Accomplished
<!-- Be specific. Include file paths for every output. -->
1. [task completed] → output at `[file path]`
2. [task completed] → output at `[file path]`

## Exact State of Work in Progress
<!-- If anything is mid-stream, describe exactly where it stopped -->
- [work item]: completed through [specific point], next step is [specific action]
- [work item]: blocked on [specific issue]

## Decisions Made This Session
<!-- Reference decision records if created, otherwise summarize here -->
- DR-[number]: [decision] (see `./docs/summaries/decision-[file]`)
- [Ad-hoc decision]: [what] BECAUSE [why] — STATUS: [confirmed/provisional]

## Key Numbers Generated or Discovered This Session
<!-- Every metric, estimate, or figure produced. Exact values. -->
- [metric]: [value] — [context for where/how this was derived]

## Conditional Logic Established
<!-- Any IF/THEN/BUT/EXCEPT reasoning that future sessions must respect -->
- IF [condition] THEN [approach] BECAUSE [rationale]

## Files Created or Modified
| File Path | Action | Description |
|-----------|--------|-------------|
| `[path]`  | Created | [what it contains] |
| `[path]`  | Modified | [what changed and why] |

## What the NEXT Session Should Do
<!-- Ordered, specific instructions. The next session starts by reading this. -->
1. **First**: [specific action with file paths]
2. **Then**: [specific action]
3. **Then**: [specific action]

## Open Questions Requiring User Input
<!-- Do NOT proceed on these without explicit user confirmation -->
- [ ] [question] — impacts [what downstream deliverable]
- [ ] [question]

## Assumptions That Need Validation
<!-- Things treated as true this session but not confirmed -->
- ASSUMED: [assumption] — validate by [method/person]

## What NOT to Re-Read
<!-- Prevent the next session from wasting context on already-processed material -->
- `[file path]` — already summarized in `[summary file path]`

## Files to Load Next Session
<!-- Explicit index of what the next session should read. Acts as progressive disclosure index layer. -->
- `[file path]` — needed for [reason]
- `[file path]` — needed for [reason]
```

---

## Template 5: Project Brief (Initial Setup)

**Use when:** Creating the 00-project-brief.md at project start

**Write to:** `./docs/summaries/00-project-brief.md`

```markdown
# Project Brief: [Project Name]
**Created:** [YYYY-MM-DD]
**Last Updated:** [YYYY-MM-DD]

## Project
- **Name:** [project name]
- **Repo:** [repo URL]
- **Scope:** [one paragraph description]
- **Target Deliverable:** [specific output expected]
- **Timeline:** [deadline if known, or "ongoing"]

## Input Documents
| Document | Path | Processed? | Summary At |
|----------|------|-----------|------------|
| [name]   | `[path]` | Yes/No | `[summary path]` |

## Success Criteria
- [criterion 1]
- [criterion 2]

## Known Constraints
- [constraint 1]
- [constraint 2]

## Project Phase Tracker
| Phase | Status | Summary File | Date |
|-------|--------|-------------|------|
| Discovery | Not Started / In Progress / Complete | `[path]` | |
| Strategy | Not Started / In Progress / Complete | `[path]` | |
| Deliverable Draft | Not Started / In Progress / Complete | `[path]` | |
| Review & Polish | Not Started / In Progress / Complete | `[path]` | |
```

---

## Template 6: Task Definition

**Use when:** Defining a discrete unit of work before starting execution

```markdown
## Task: [name]
**Date:** [YYYY-MM-DD]
**Client:** [if applicable]
**Work Type:** [proposal / workshop / analysis / content / agent development]

### Context Files to Load
- `[file path]` — [why needed]

### Action
[What to produce. Be specific about format, length, and scope.]

### Verify
- [ ] Numbers match source data exactly
- [ ] Open questions marked OPEN
- [ ] Output matches what was requested, not what was assumed
- [ ] Claims backed by specific data
- [ ] Consistent with stored decisions in docs/context/

### Done When
- [ ] Output file exists at `[specific path]`
- [ ] Summary written to `docs/summaries/[specific file]`
```

---

## Subagent Output Contracts

**CRITICAL: When subagents return results to the main agent, unstructured prose causes information loss. These output contracts define the EXACT format subagents must return.**

### Contract for Document Analysis Subagent

```
=== DOCUMENT ANALYSIS OUTPUT ===
SOURCE: [file path]
TYPE: [document type]
CONFIDENCE: [high/medium/low]

NUMBERS:
- [metric]: [exact value]
[repeat for all numbers found]

REQUIREMENTS:
- REQ: [requirement] | CONDITION: [if any] | PRIORITY: [level] | CONSTRAINT: [if any]
[repeat]

DECISIONS_REFERENCED:
- DEC: [what] | WHY: [rationale] | BY: [who]
[repeat]

CONTRADICTIONS:
- [this document says X] CONTRADICTS [other known fact Y]
[repeat or NONE]

OPEN:
- [unresolved item] | NEEDS: [who/what to resolve]
[repeat or NONE]

QUOTES:
- "[verbatim]" — [speaker], [context]
[repeat, max 5]

=== END OUTPUT ===
```

### Contract for Research/Analysis Subagent

```
=== RESEARCH OUTPUT ===
QUERY: [what was researched]
SOURCES: [list]
CONFIDENCE: [high/medium/low] BECAUSE [reason]

CORE_FINDING: [one sentence]

EVIDENCE:
- [data point]: [exact value] | SOURCE: [where] | DATE: [when]
[repeat]

CONCLUSIONS:
- IF [condition] THEN [conclusion] | EVIDENCE: [reference]
[repeat]

GAPS:
- [what was not found or not covered]
[repeat or NONE]

NEXT_STEPS:
- [recommended action] | PRIORITY: [level]
[repeat]

=== END OUTPUT ===
```

### Contract for Review/QA Subagent

```
=== REVIEW OUTPUT ===
REVIEWED: [file path or deliverable name]
AGAINST: [what standard — spec, requirements, style guide]

PASS: [yes/no/partial]

ISSUES:
- SEVERITY: [critical/major/minor] | ITEM: [description] | LOCATION: [where in document] | FIX: [suggested resolution]
[repeat]

MISSING:
- [expected content/section not found] | REQUIRED_BY: [which requirement]
[repeat or NONE]

INCONSISTENCIES:
- [item A says X] BUT [item B says Y] | RESOLUTION: [suggested]
[repeat or NONE]

STRENGTHS:
- [what works well — for positive reinforcement in iteration]
[max 3]

=== END OUTPUT ===
```

---

## Phase-Based Workflow Templates

### Agent/Application Development

```
Phase 1: Requirements → Spec
├── Process all input documents → Source Document Summaries
├── Generate structured specification
├── Output: ./output/SPEC.md
├── Write: ./docs/summaries/01-spec-complete.md (Handoff Template)
├── → Suggest new session for Phase 2

Phase 2: Architecture → Schema
├── Read SPEC.md + summaries only
├── Design data model
├── Define agent behaviors and workflows
├── Output: ./output/schemas/data-model.yaml
├── Output: ./output/schemas/agent-definitions.yaml
├── Write: ./docs/summaries/02-architecture-complete.md (Handoff Template)
├── → Suggest new session for Phase 3

Phase 3: Prompts → Integration
├── Read schemas + spec only
├── Write system prompts for each agent
├── Map API integrations and data flows
├── Output: ./output/prompts/[agent-name].md (one per agent)
├── Output: ./output/schemas/integration-map.yaml
├── Write: ./docs/summaries/03-prompts-complete.md (Handoff Template)
├── → Suggest new session for Phase 4

Phase 4: Assembly → Package
├── Read all output files
├── Assemble complete application package
├── Generate deployment/setup instructions
├── Output: ./output/deliverables/[project]-complete-package/
├── QA check against original spec using Review/QA Output Contract
```

---

## End of Templates

**Return to your task after reading the template(s) you need. Do not keep this file in active context.**
