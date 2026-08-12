Write a session handoff file for the current session.

Steps:

1. Fill in every section of the template below based on what was accomplished in this session, including the forward-looking tail (Unfinished Work / Files to Load Next Session / What NOT to Re-Read). Be specific — include exact file paths for every output, exact numbers discovered, and conditional logic established.
2. Archive next, before writing anything: move every existing `docs/summaries/handoff-*.md` to `docs/archive/`. A same-named file already there is an earlier revision of the same work log, so let the incoming file replace it and say so in your summary — never keep both under a suffixed name. Every file moves: `docs/summaries/` is empty when this step ends. Order matters — once the new handoff is on disk it matches that glob too.
3. Write the handoff to `docs/summaries/handoff-[YYYY-MM-DD]-[topic].md`. Never overwrite: if that path still exists after step 2, pick a `[topic]` unique for the date.
4. Tell me the file path of the new handoff and summarize what it contains.

This routine touches only gitignored files — do not branch, and do not edit tracked files as part of it. Promoting durable facts into `docs/context/` belongs to the work itself (`AGENTS.md` rule 6), not to the handoff. If you reach this point and find a durable fact that never made it into a tracked doc, do not quietly write it now: record it under Unfinished Work and say so in your summary, so the fix lands on a branch the user chooses.

Under What NOT to Re-Read list the handoffs, plans, and analyses this session actually opened that a later reader should skip, naming what replaces each — a reason to *read* something belongs in Files to Load instead.

Under Goal, **Task** is the job as you understood it when work began, stated in your own words — not a quote of the user's message. Write the objective and what would count as done, at the level of detail you actually worked to: one or two sentences a next session could act on without the transcript. Assemble it from everything settled before you began the work itself — the first edit, or in a session that produces no edit, the first move toward the deliverable — the opening request plus any clarification that followed — so a task negotiated over several turns reads as one statement, and a task the user gave in pieces is visible as the single thing it became. This line is a two-way check: the user reads it to see whether their ask landed the way they meant it, so write the understanding you acted on, not the safest paraphrase. Do not back-fill it from what got built — if your understanding was wrong or the target moved mid-session, the original understanding stays here and the correction goes under Scope changes. If the messages that set the task are no longer available, reconstruct from the earliest record you still hold and mark the line ASSUMED. **Delivered** is one of DELIVERED / PARTIAL / BLOCKED (stopped by something outside the session) / DROPPED (called off), followed by what is true now and the evidence that proves it — a merged sha, a passing suite, a verified output. A session whose deliverable is an answer is DELIVERED when the answer is in the file. Judge it against the task as corrected — the Task line plus every correction under Scope changes — never against the Task line alone when that line preserves an understanding the session went on to revise. It must agree with Unfinished Work: DELIVERED only when nothing left undone blocks the goal; PARTIAL and BLOCKED each point at the numbered Unfinished Work item covering the gap; DROPPED still records the state the abandoned work was left in — an uncommitted branch, an unapplied migration — because the next session inherits it. **Scope changes** records work added or abandoned after the task was set, and any correction to the understanding recorded under Task, with the reason — a session that grew shows it here, not silently inside What Was Accomplished.

```markdown
# Handoff: [Topic]
**Date:** [YYYY-MM-DD]
**Branch:** [branch — plus state: active / merged as `sha` / abandoned]
**PR/Issue:** [PR number and/or Linear issue] or None

## Goal
- **Task:** [the job as you understood it when work began, in your own words — objective and what counts as done]
- **Delivered:** [DELIVERED/PARTIAL/BLOCKED/DROPPED] — [what is true now; for anything but DELIVERED, the gap and the Unfinished Work item that covers it] — evidence: [the check that proves it]
- **Scope changes:** [work added or abandoned after the task was set, or a correction to the Task line, and why] or None

## What Was Accomplished
- [task] → `[file:line]`

## Decisions Made
- [decision] BECAUSE [rationale] — STATUS: [confirmed/provisional]

## Key Numbers
- [exact test counts, timings, values — do not round]

## Open Questions
- [OPEN/ASSUMED item] or None

## Unfinished Work
1. [ordered, specific action with paths] or None

## Files to Load Next Session
- `[path]` — [what it holds and when it matters; add `~L[start]-[end]` if only one region does; mark it **untracked** if it is not committed, since another agent or a fresh clone will not have it]

## What NOT to Re-Read
- `[path]` — superseded by / already summarized in / unrelated to `[path]`
```
