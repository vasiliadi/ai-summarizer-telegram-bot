# Document Processing Protocol

Use this whenever you need to process multiple documents or large files.

## Common Triggers in This Repo

Apply this protocol (not just for research documents) when you hit any of these:

- **External docs dump** — library API docs, RFCs, migration guides, changelogs when adopting or upgrading a dependency. Summarize to `docs/summaries/source-[library]-[topic].md`.
- **Large PR / diff review** — a multi-hundred-line diff across many files. Read per-file, write per-file review to `docs/summaries/review-[pr]-[file].md`, then synthesize.
- **Incident / stack trace investigation** — long logs or multi-service traces. Summarize findings per service to `docs/summaries/incident-[date]-[service].md`.
- **Codebase exploration before refactor** — many files to understand before proposing changes. Grep/Glob first, read targeted files only, write `docs/summaries/refactor-notes-[area].md`.

## For 1-3 Short Documents (< 2K words each)

Read sequentially. After each document, write a Source Document Summary (Template 1 from `templates/claude-templates.md`) to disk. Then proceed with work using summaries only.

## For 4+ Documents OR Any Document > 2K Words

**Step 1:** List all documents with file sizes. Present to user for prioritization.

**Step 2:** Process each document individually:

- Read one document
- Extract into Source Document Summary format
- Write to `./docs/summaries/source-[filename].md`
- Release the document from active consideration before reading the next

**Step 3:** After all documents are processed, read only the summaries to form your working context.

**Step 4:** Cross-reference summaries for contradictions or dependencies. Note these explicitly.

**Step 5:** Proceed with the actual task using summaries as your reference.
