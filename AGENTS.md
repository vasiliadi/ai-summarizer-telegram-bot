# AGENTS.md

## Session Start

Read the latest handoff in docs/summaries/ if one exists. Load only the files that handoff references — not all summaries. If no handoff exists, ask: what is the project, what type of work, what is the target deliverable.

Before starting work, state: what you understand the project state to be, what you plan to do this session, and any open questions.

## Identity

You work with Andrii Vasiliadi, a software engineer building ai-summarizer-telegram-bot. Adapt your communication style and outputs to match this domain.

## Rules

1. Before running any Python command or modifying dependencies, read `docs/context/uv-guide.md`.
2. Do not mix unrelated project contexts in one session.
3. Write state to disk, not conversation. After completing meaningful work, write a summary to docs/summaries/ using templates from templates/claude-templates.md. Include: decisions with rationale, exact numbers, file paths, open items.
4. Before compaction or session end, write to disk: every number, every decision with rationale, every open question, every file path, exact next action.
5. When switching work types (research → writing → review), write a handoff to docs/summaries/handoff-[date]-[topic].md and suggest a new session.
6. Do not silently resolve open questions. Mark them OPEN or ASSUMED.
7. Do not bulk-read documents. Process one at a time: read, summarize to disk, release from context before reading next. For the detailed protocol, read docs/context/processing-protocol.md.
8. Sub-agent returns must be structured, not free-form prose. Use output contracts from templates/claude-templates.md.

## Where Things Live

- templates/claude-templates.md — summary, handoff, decision, analysis, task, output contract templates (read on demand)
- docs/summaries/ — active session state (latest handoff + project brief + decision records + source summaries)
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
