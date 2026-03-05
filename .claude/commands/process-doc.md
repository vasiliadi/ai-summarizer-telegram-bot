Process an input document into a structured source summary.

Steps:
1. Read `templates/claude-templates.md` and find the Source Document Summary template (Template 1). Use the Light Source Summary if this is a small project (under 5 sessions), Full Source Summary otherwise.
2. Read the document at: $ARGUMENTS
3. Extract all information into the template format. Pay special attention to:
   - EXACT numbers — do not round or paraphrase
   - Requirements in IF/THEN/BUT/EXCEPT format
   - Decisions with rationale and rejected alternatives
   - Open questions marked as OPEN, ASSUMED, or MISSING
4. Write the summary to `./docs/summaries/source-[filename].md`.
5. Move the original document to `./docs/archive/`.
6. Tell me: what was extracted, what's unclear, and what needs follow-up.
