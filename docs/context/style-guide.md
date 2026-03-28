# Style Guide

This style guide establishes consistent coding conventions, documentation standards, and development practices for the AI Summarizer Telegram Bot project. It serves as the single source of truth for all code formatting, linting rules, and workflow standards.

## Table of Contents

1. [Python Code Formatting](#python-code-formatting)
2. [Code Quality and Linting](#code-quality-and-linting)
3. [Documentation Standards](#documentation-standards)
4. [Error Handling & Logging](#error-handling--logging)
5. [Type Annotations](#type-annotations)
6. [Testing Standards](#testing-standards)

---

## Python Code Formatting

This project follows PEP 8 and modern Python best practices.

We do not manually enforce line lengths, quote types, or import sorting rules in this document. **All formatting rules are enforced automatically by Ruff**, configured in `pyproject.toml` under `[tool.ruff]` and `[tool.ruff.format]`.

### Naming Conventions (PEP 8)

* **Variables, Functions, Methods, Modules:** `snake_case`
* **Classes:** `PascalCase`
* **Constants:** `UPPER_SNAKE_CASE`
* **Private Members:** `_leading_underscore`

---

## Code Quality and Linting

This project uses **Ruff** for code quality enforcement and linting. Ruff is a fast Python linter that combines the functionality of multiple tools (Flake8, isort, pyupgrade, and more) into a single, high-performance package.

All active linting rules, ignored rules, and directory exclusions are explicitly configured in `pyproject.toml` under `[tool.ruff.lint]`. This file is the absolute source of truth for code style.

### Inline Suppressions

If a specific line of code must bypass a linting rule for a legitimate reason, use an inline suppression comment with the specific rule code:

```python
result = eval(user_input)  # noqa: S307
```

*Note: Use `# noqa` sparingly and always specify the exact rule code.*

**Workflow:** Run `ruff check --fix` to automatically resolve fixable linting errors.

---

## Documentation Standards

### Google Docstrings Style

All public functions, classes, and methods must have docstrings formatted in **Google Docstrings Style**.

* Keep descriptions concise.
* Clearly define `Args:`, `Returns:`, and `Raises:` where applicable.
* Docstrings for private methods (`_method`) are optional if the behavior is obvious.

### Inline Comments

Use inline comments (`#`) sparingly. Code should be self-documenting through clear variable and function naming. Only use inline comments to explain *why* complex or non-obvious logic was implemented, not *what* the code is doing.

---

## Error Handling & Logging

### Exceptions

* **Create Custom Exceptions** for domain-specific errors (e.g., `MessageTooLongError`, `SummarizationError`). Inherit from standard exceptions like `ValueError` or `Exception`.
* **Try-Except Blocks:** Only catch exceptions you can handle gracefully. Let unexpected programming errors propagate. Never use bare `except:` clauses.

### Logging

Use Python's built-in `logging` module.

* `ERROR`: Failures requiring attention (include `exc_info=True` to capture tracebacks).
* `WARNING`: Unexpected but handled situations (e.g., fallbacks, retries).
* `INFO`: Important state changes (e.g., application started, summary generated).
* `DEBUG`: Detailed diagnostic information for development.

Include context in logs using f-strings or the `extra` parameter. **Never log sensitive data** (API keys, passwords).

---

## Type Annotations

This project requires **100% type annotation coverage** for all function signatures (parameters and return values) and class attributes.

* **Modern Syntax:** Use Python 3.10+ syntax (`|` instead of `Union`, `list` instead of `List`).
* **Collections:** Use built-in types with parameters (e.g., `dict[str, Any]`, `list[int]`).
* **Optional:** Use `Type | None` instead of `Optional[Type]`.
* **Circular Imports:** Use `from __future__ import annotations` and `if TYPE_CHECKING:` blocks to handle types that would otherwise cause circular imports.

---

## Testing Standards

### Naming Conventions

* **Files:** Must use the `test_*.py` prefix.
* **Functions:** Must use the `test_<functionality>_<scenario>` pattern (e.g., `test_process_message_with_empty_string`).

### Principles

* Write **Unit Tests** for isolated business logic, utilities, and data validation.
* Write **Integration Tests** for database operations, API clients, and end-to-end flows.
* Aim for high coverage on core business logic and edge cases.
