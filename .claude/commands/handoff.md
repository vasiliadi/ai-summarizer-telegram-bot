Write a session handoff file for the current session.

Steps:
1. Read `templates/claude-templates.md` and find the Session Handoff template (Template 4). Use the Light Handoff if this is a small project (under 5 sessions), Full Handoff otherwise.
2. Fill in every field based on what was accomplished in this session. Be specific — include exact file paths for every output, exact numbers discovered, and conditional logic established.
3. Write the handoff to `./docs/summaries/handoff-[today's date]-[topic].md`.
4. If a previous handoff file exists in `./docs/summaries/`, move it to `./docs/archive/handoffs/`.
5. Tell me the file path of the new handoff and summarize what it contains.
