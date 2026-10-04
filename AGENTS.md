# AGENTS.md

## Start Each Session

Before touching code, read `docs/context/architecture.md`. Before writing code, also read `docs/context/style-guide.md` for conventions Ruff does not enforce. Skip both for docs-only work.

State the session plan and any open questions.

Before the first tracked-file edit, branch from `main` with `git checkout -b <scope>-<short-desc>`; follow the commit scope convention in `docs/context/git-guide.md`. A `PreToolUse` hook enforces this for repo files; gitignored files such as handoffs in `docs/summaries/` are exempt.

## Rules

1. **Surface every open question.** Mark unresolved items OPEN or ASSUMED in the final answer. Before delivering output, verify exact numbers are preserved and claims are backed by specific data.
2. Before running any Python command or modifying dependencies, read `docs/context/uv-guide.md`.
3. Follow the commit, hook, and coverage process in `docs/context/git-guide.md`. Never bypass hooks with `--no-verify`. Put follow-up fixes in new commits; never amend, rebase, or otherwise rewrite an existing commit unless the user asks directly.
4. **Commit your work without asking; push only when asked.** Commit each finished, coherent step on the working branch as you go — ending a session with uncommitted changes is the failure, not committing too often. Never `git push` unprompted: a `/create-pr` invocation or a direct user request authorizes exactly one push and creates no standing permission. Otherwise, report the branch as committed and ready to push.
5. **Keep documentation and tests current in the same PR.** Update tests for every code change, and every `docs/context/` file the work invalidates — a rename or moved responsibility invalidates the component map; a dependency bump can retire a documented workaround.
6. **Record durable facts during the work, in their tracked owner** (see *Where Things Live*). A durable fact is one without which a later session would make a wrong change: an external-service constraint, a settled choice, a convention. Gitignored handoffs and agent-local memory are not substitutes. Treat these updates as mandatory, like the pre-commit hooks.
7. **Docs describe the current state; history goes in the commit message.** Record a rejected alternative only when a later session would plausibly propose it again from reading the code, as the decision and its reason in a sentence or two. What was tried, removed, or superseded, and the numbers that decided it, belong in the commit message. Keep results snapshots and "next step" notes out of `docs/context/`. When a fact stops mattering (the code it guarded is gone, its deadline has passed), delete it.
8. **Versions and dates.** Do not copy versions Renovate bumps (`pyproject.toml` pins, `uv.lock`, `.python-version`, workflow actions) into docs — name the file that holds them. Name a version only where behaviour changed at it. Date a fact only when it observes an external system the repo cannot demonstrate (a provider's behaviour, a calibration, a VM image) or marks a real deadline; the date tells the reader when to re-check it.

## Where Things Live

### Code

- `src/` — the bot. `architecture.md` maps it module by module.
- `tests/` — the pytest suite. Coverage rules are in `git-guide.md`.
- `scripts/` — standalone operational scripts, never imported by the bot. `scripts/eval/` is
  the evaluation harness; read `docs/context/evals.md` before touching it.

### Documentation

- `docs/context/` — reusable domain knowledge and the owner of every durable fact. Load only what the task needs. **(tracked)**
  - `architecture.md` — component map, data flow, external-service gotchas, and standing choices
  - `evals.md` — the evaluation system: datasets, scoring tiers, judges, the `scripts/eval/`
    harness, and anything Langfuse beyond the bot's own tracing (which `architecture.md` owns)
  - `style-guide.md` — coding conventions Ruff does not enforce, including comments and docstrings
  - `git-guide.md` — commit format, pre-commit hooks, coverage, CI workflows
  - `uv-guide.md` — running the project and managing dependencies
- `AGENTS.md` — session process.
- `docs/summaries/` — handoffs written by `/handoff` (`handoff-*.md`). **(gitignored)**
- `docs/archive/` — superseded handoffs, kept flat. Read only when explicitly told. **(gitignored)**
- `.claude/commands/handoff.md` — the `/handoff` routine and its template.
