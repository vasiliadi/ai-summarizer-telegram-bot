# Style Guide

Conventions that are **not** already enforced automatically. All formatting, naming, import
sorting, and line-length rules are enforced by Ruff (configured in `pyproject.toml` under
`[tool.ruff]`, `[tool.ruff.format]`, and `[tool.ruff.lint]`) — that file is the source of truth,
not this one. See `docs/context/git-guide.md` for how it runs at commit time.

## Minimal Fixes

Keep a correct fix minimal. Do not add defensive validation, extra flag variables,
expanded docstrings, or error-context enrichment to cover a theoretical concern the
simpler version already handles — suggestions of that shape have been rejected and
reverted more than once. When a review raises something technically valid but low-impact,
propose it rather than implementing it.

## Inline Suppressions

If a line must bypass a lint rule for a legitimate reason, use an inline suppression with the
specific rule code, and prefer it over restructuring code just to satisfy the linter — e.g. for
`C901`/`PLR0915`, add `# noqa` rather than extracting a tiny single-purpose helper only to drop the
count:

```python
result = eval(user_input)  # noqa: S307
```

Use `# noqa` sparingly and always specify the exact rule code.

## Docstrings & Comments

`docs/context/` is the single source of truth for design rationale, gotchas, and "do not" rules.
Comments and docstrings go stale unnoticed, so keep them short and let them point to the doc.
This applies to `src/` and `scripts/` alike.

- **Comments: at most two lines, and only *why*.** Never explain *what* the code does — naming does
  that. Anything longer (a provider's behaviour, a rejected alternative, a history of what broke)
  goes in the owning `docs/context/` file, and the comment names the section:
  `# See architecture.md → *OpenRouter calls identify the app*`. Name the section, not a line
  number, so the pointer survives edits to the doc.
- **Docstrings: a one-line summary**, Google style, for public functions, classes, and methods. A
  second sentence is fine when the summary cannot carry a non-obvious contract; longer explanations
  follow the comment rule above. Skip `Args:` — annotations are complete, so a param block only
  restates the signature. Keep `Raises:` (the `RetryError` contracts the `@retry` decorators create
  are not derivable from the body), and `Returns:` only where it says something the return type
  does not. Docstrings for private (`_method`) members are optional when behavior is obvious.
- Never describe another component in a comment (what a different script installs, what another
  module does): it goes stale the moment that component changes.
- Guard an invariant that must not regress with a test, not a comment — a test fails loudly, a
  comment rots quietly (e.g. `test_sentry_opts_into_log_collection`).
- A long existing comment is not deleted outright: move whatever it says that `docs/context/` does
  not already record, then shorten it.

## Error Handling & Logging

- **Custom exceptions** for domain-specific errors (e.g. `LimitExceededError`,
  `WebParseError`); inherit from `ValueError` or `Exception`.
- Only catch exceptions you can handle gracefully; let unexpected programming errors propagate.
  Never use a bare `except:`.
- **PEP 758 (Python 3.14+):** for a tuple of exception types with no `as` binding, `ruff format`
  normalizes to the unparenthesized form — `except ExceptionA, ExceptionB, ExceptionC:` — so that is
  the house style, not `except (ExceptionA, ExceptionB, ExceptionC):`. Parentheses are still required
  (and kept) when binding the exception, e.g. `except (ExceptionA, ExceptionB) as exc:`. This syntax
  is valid on the interpreter this repo targets, so validate with `uv run` (3.14), not a system
  `python3`.
- Use the stdlib `logging` module. Levels: `ERROR` (failures needing attention — include
  `exc_info=True`), `WARNING` (handled-but-unexpected, e.g. fallbacks/retries), `INFO` (important
  state changes), `DEBUG` (development diagnostics).
- **Never log sensitive data** (API keys, passwords).

## Type Annotations

100% annotation coverage for all function signatures and class attributes.

- Modern syntax: `|` over `Union`, `Type | None` over `Optional[Type]`, built-in generics
  (`dict[str, Any]`, `list[int]`).
- For circular-import types, use `from __future__ import annotations` and `if TYPE_CHECKING:` blocks.

## Classes

Collaborators arrive via `__init__` and are stored on private attributes (e.g. `self._client`);
`container.py`'s composition root does the wiring, once, from `config`'s clients (see
`docs/context/architecture.md`). No module-level service singletons or method aliases — a class
is the entire public surface.

- `@staticmethod` is reserved for **private** helpers (`_name`) that need no instance state.
- Annotate class-level constants with `ClassVar`, e.g. `_DEFAULTS: ClassVar[dict[str, str]]` —
  without it Ruff (`RUF012`) reads a mutable class attribute as an un-annotated instance field.

## Testing

- **Files:** `test_*.py`. **Functions:** `test_<functionality>_<scenario>` (e.g.
  `test_process_message_with_empty_string`).
- Unit tests for isolated business logic, utilities, and validation; integration tests for database
  operations, API clients, and end-to-end flows. Aim for high coverage on core logic and edge cases.

## Prompt Strings

Keep the indented triple-quoted strings in `src/prompts.py` raw; do not clean them at
definition time. `src/summary.py` already calls `dedent(...).strip()` at every call site,
and `prompt_version` hashes the raw string. Pre-cleaning therefore shifts every digest
at once while the suite stays green because no test pins a literal digest, making traces
recorded before and after the change appear to use different prompt versions.

## Documentation Paths

Write repo-relative paths **bare**, without a leading `./` — `docs/summaries/handoff.md`, not
`./docs/summaries/handoff.md`.
