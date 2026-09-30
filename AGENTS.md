# AGENTS.md

## Start Each Session

Load handoffs from `docs/summaries/` or `docs/archive/` only when the user points to previous work. Read every handoff they name, load its Files to Load Next Session, and skip everything listed under What NOT to Re-Read. Otherwise, treat handoffs as work logs, not session context.

Before touching code, read `docs/context/architecture.md`. Before writing code, also read `docs/context/style-guide.md` for conventions Ruff does not enforce. Skip both for docs-only work.

State the session plan and any open questions.

Before the first tracked-file edit, branch from `main` with `git checkout -b <scope>-<short-desc>`; follow the commit scope convention in `docs/context/git-guide.md`. A `PreToolUse` hook enforces this for repo files; gitignored files such as handoffs in `docs/summaries/` are exempt.

## Rules

1. **Write handoffs only on request.** Treat the handoff as a history log, not an in-progress record, and follow `.claude/commands/handoff.md` (the `/handoff` command, or its steps directly).
2. **Surface every open question.** Mark unresolved items OPEN or ASSUMED in the final answer, and in the handoff when one is written. Before delivering output, verify exact numbers are preserved and claims are backed by specific data.
3. Before running any Python command or modifying dependencies, read `docs/context/uv-guide.md`.
4. Follow the commit, hook, and coverage process in `docs/context/git-guide.md`. Never bypass hooks with `--no-verify`. Put follow-up fixes in new commits; never amend, rebase, or otherwise rewrite an existing commit unless the user asks directly. Under `docs/`, stage only `docs/context/`; the rest is gitignored.
5. **Never `git push` unprompted** — a `/create-pr` invocation or direct user request authorizes exactly one push. It does not create standing permission. Otherwise, commit locally and report the branch as ready.
6. **Keep documentation and tests current in the same PR.**
   - Update every `docs/context/` file the work invalidates. A rename or moved responsibility invalidates the component map; a dependency bump can retire a documented workaround.
   - Update tests for every code change.
   - Record every durable fact the work establishes in its tracked owner: `architecture.md` for the component map, gotchas, and standing choices; `evals.md` for the evaluation system and anything Langfuse beyond the bot's own tracing; `style-guide.md` for conventions Ruff does not enforce; `git-guide.md` for commit, hook, and CI-workflow process; `uv-guide.md` for dependencies and running the project; `AGENTS.md` for session process.

   A durable fact is anything a later session must not get wrong, such as an external-service constraint, settled choice, rejected review finding, or convention. Record it during the work; gitignored handoffs and agent-local memory are not substitutes. Treat these updates as mandatory, like the pre-commit hooks.

   Do not copy versions that Renovate bumps (`pyproject.toml` pins, `uv.lock`, `.python-version`, workflow actions) into docs — name the file that holds them, or the copy goes stale on the next bump. A version you observed rather than pinned, such as a cloud VM image's, carries the date you observed it.

   Date a fact only when it is an observation of an external system the repo cannot demonstrate (a provider's behaviour, a calibration, a VM image) or a real deadline; the date tells the reader when to re-check it. Name a version only where behaviour changed at it. Do not date what the code or a test already proves, and keep results snapshots and "next step" notes out of `docs/context/` — they are work logs.

   Keep code comments and docstrings to one or two lines; the explanation lives in `docs/context/` (see *Docstrings & Comments* in `style-guide.md`).

## Where Things Live

### Code

- `src/` — the bot. `architecture.md` maps it module by module.
- `tests/` — the pytest suite. Coverage rules are in `git-guide.md`.
- `scripts/` — standalone operational scripts, never imported by the bot. `scripts/eval/` is
  the evaluation harness; read `docs/context/evals.md` before touching it.

### Documentation

- `docs/context/` — reusable domain knowledge. Load only what the task needs; record durable facts here, not in agent-local memory. **(tracked)**
  - `architecture.md` — component map and data flow; update only on architectural change
  - `evals.md` — the evaluation system: datasets, scoring tiers, judges, and the
    `scripts/eval/` harness. `architecture.md` owns how the bot emits traces; this owns
    everything built on top of them
  - `style-guide.md` — coding conventions Ruff does not enforce
  - `git-guide.md` — commit format, pre-commit hooks, coverage, CI workflows
  - `uv-guide.md` — running the project and managing dependencies
- `docs/summaries/` — requested handoffs (`handoff-*.md`). **(gitignored)**
- `docs/archive/` — superseded handoffs, kept flat. Read only when explicitly told. **(gitignored)**
- `.claude/commands/handoff.md` — the `/handoff` routine and its template; agents without slash commands follow its steps directly.
