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

- Public functions, classes, and methods use **Google-style** docstrings led by a one-line summary.
  Skip `Args:` — annotations are complete, so a param block only restates the signature; fold
  anything non-obvious into the summary instead. Keep `Raises:` (the `RetryError` contracts the
  `@retry` decorators create are not derivable from the body), and `Returns:` only where it says
  something the return type does not.
- Docstrings for private (`_method`) members are optional when behavior is obvious.
- Use inline `#` comments sparingly, and only to explain *why* non-obvious logic exists — not *what*
  the code does. Code should be self-documenting through naming.

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

## Agent Hook Scripts

`.codex/hooks/*.py` is the exception to everything above that assumes 3.14. The agent harness runs
these with whatever `python3` sits on `PATH` — macOS still ships 3.9 — outside the project venv, so
keep them **stdlib-only and 3.9-compatible**, and validate with `/usr/bin/python3`, not `uv run`.

Ruff lints and formats them anyway, at `target-version = "py314"`, which is a live trap: the PEP 758
rewrite above silently turns a parenthesized `except (A, B):` into `except A, B:`, a syntax error on
3.9, and `ruff format` obeys no `# noqa`. Catch one type instead of a tuple —
`except ValueError:` covers both `JSONDecodeError` and `UnicodeDecodeError` — rather than fighting
the formatter.

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
