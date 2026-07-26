# Style Guide

Conventions that are **not** already enforced automatically. All formatting, naming, import
sorting, and line-length rules are enforced by Ruff (configured in `pyproject.toml` under
`[tool.ruff]`, `[tool.ruff.format]`, and `[tool.ruff.lint]`) — that file is the source of truth,
not this one. See `docs/context/git-guide.md` for how it runs at commit time.

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

- Public functions, classes, and methods use **Google-style** docstrings — define `Args:`,
  `Returns:`, and `Raises:` where applicable; keep descriptions concise.
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

## Classes

Service modules follow the class → module-singleton → method-alias pattern documented in
`docs/context/architecture.md` (Cross-cutting patterns). Beyond that:

- `@staticmethod` is reserved for **private** helpers (`_name`) that need no instance state.
  Public methods keep `self` even when they don't use it — they form the aliased singleton
  surface (`check_quota = quota_manager.check_quota`), so they must stay bound methods.
- Annotate class-level constants with `ClassVar`, e.g. `_DEFAULTS: ClassVar[dict[str, str]]` —
  without it Ruff (`RUF012`) reads a mutable class attribute as an un-annotated instance field.

## Testing

- **Files:** `test_*.py`. **Functions:** `test_<functionality>_<scenario>` (e.g.
  `test_process_message_with_empty_string`).
- Unit tests for isolated business logic, utilities, and validation; integration tests for database
  operations, API clients, and end-to-end flows. Aim for high coverage on core logic and edge cases.

## Documentation Paths

Write repo-relative paths **bare**, without a leading `./` — `docs/summaries/handoff.md`, not
`./docs/summaries/handoff.md`.
