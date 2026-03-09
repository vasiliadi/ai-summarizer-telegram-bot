# Document Processing Protocol

Use this whenever you need to process multiple documents or large files.

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
