# Archive Rules

## Raw File Archival

After creating a Source Document Summary for any raw file:

1. Move the raw file to `docs/archive/`
2. Record the move in the source summary's header: `Archived From: [original path]`
3. Do not read from `docs/archive/` unless the user explicitly says "go back to the original [filename]"

## Summary Lifecycle Rules

1. **Session handoffs expire**: After a new handoff is written, the previous handoff moves to `docs/archive/handoffs/`. Only the latest handoff stays in `docs/summaries/`.
2. **Decision records persist**: Decision records (DR-*) stay in `docs/summaries/` permanently — they are institutional memory. For a code project these function as ADRs (library choices, architecture decisions, migration strategies).
3. **Source summaries persist**: Source document summaries stay until the source is no longer relevant — they replace raw documents. Covers research docs, external library docs, RFCs, migration guides, changelogs.
4. **Analysis summaries**: Keep only the latest version. If re-run, the new one replaces the old (archive the old one). Covers incident investigations, bug analyses, refactor plans, codebase exploration notes.
5. **Review notes are ephemeral**: PR review notes (`review-*.md`) are archived after the PR merges or is closed.
6. **Maximum active summaries**: If `docs/summaries/` exceeds 15 files, consolidate older source summaries into a single `project-digest.md` and archive the originals.
