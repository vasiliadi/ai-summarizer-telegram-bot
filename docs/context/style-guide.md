# Style Guide

## Introduction

This style guide establishes consistent coding conventions, documentation standards, and development practices for the AI Summarizer Telegram Bot project. It serves as the single source of truth for all code formatting, linting rules, documentation patterns, and workflow standards.

### Purpose

This guide ensures:

- Consistent Python code formatting across the entire codebase
- Clear documentation and docstring conventions
- Standardized Git commit messages and version control practices
- Uniform markdown documentation formatting
- Organized file and directory structure
- Predictable error handling and logging patterns
- Proper type annotations for static analysis
- Secure configuration and environment management
- Comprehensive testing practices

### Scope

This style guide covers all aspects of development for the AI Summarizer Telegram Bot project. It references existing configuration files (pyproject.toml, .markdownlint-cli2.jsonc) rather than duplicating their content, ensuring a single source of truth for each standard.

### Target Audience

This guide is intended for:

- Developers working on the AI Summarizer Telegram Bot project
- AI assistants generating code and documentation
- Code reviewers ensuring consistency and quality
- New contributors onboarding to the project

### How to Use This Guide

- Refer to specific sections when working on related code or documentation
- Use the examples provided as templates for your own work
- Check configuration files referenced in each section for detailed settings
- Follow the standards consistently to maintain codebase quality

## Table of Contents

1. [Python Code Formatting](#python-code-formatting)
2. [Code Quality and Linting](#code-quality-and-linting)
3. [Documentation Standards](#documentation-standards)
4. [Git Conventions](#git-conventions)
5. [Markdown Standards](#markdown-standards)
6. [File Organization](#file-organization)
7. [Error Handling](#error-handling)
8. [Type Annotations](#type-annotations)
9. [Configuration Management](#configuration-management)
10. [Testing Standards](#testing-standards)

## Python Code Formatting

This project follows strict Python formatting standards to ensure consistent, readable code across the entire codebase. All formatting rules are enforced automatically by Ruff, configured in `pyproject.toml`.

### Core Formatting Standards

**Line Length**: Maximum 88 characters per line

The project uses a line length limit of 88 characters, which balances readability with efficient use of screen space. This is the default for Black and is configured in `pyproject.toml`:

```python
# Good: Line stays within 88 characters
def process_user_message(user_id: int, message: str, timestamp: datetime) -> dict:
    """Process incoming user message and return response."""
    return {"user_id": user_id, "message": message, "timestamp": timestamp}

# Bad: Line exceeds 88 characters
def process_user_message(user_id: int, message: str, timestamp: datetime, metadata: dict, options: dict) -> dict:
    """Process incoming user message and return response."""
    return {"user_id": user_id, "message": message, "timestamp": timestamp, "metadata": metadata}
```

**Indentation**: 4 spaces (no tabs)

All indentation must use 4 spaces. Never use tabs. This is enforced by Ruff's formatter:

```python
# Good: 4 spaces for indentation
def calculate_summary_length(text: str) -> int:
    """Calculate the appropriate summary length."""
    if len(text) < 100:
        return 50
    elif len(text) < 500:
        return 100
    else:
        return 200

# Bad: Inconsistent or tab indentation (not shown, but avoid)
```

**Quote Style**: Double quotes for strings

Always use double quotes for strings unless the string contains double quotes. This is enforced by Ruff's formatter:

```python
# Good: Double quotes
message = "Hello, world!"
greeting = "Welcome to the AI Summarizer Bot"
error_msg = "An error occurred while processing your request"

# Good: Single quotes when string contains double quotes
quote = 'He said, "Hello!"'

# Bad: Single quotes without reason
message = 'Hello, world!'
```

**Python Version**: 3.13+

This project requires Python 3.13 or higher. Code should use modern Python features available in 3.13+. The target version is specified in `pyproject.toml`:

```python
# Good: Using modern Python 3.13+ features
def process_items(items: list[str]) -> dict[str, int]:
    """Process items and return counts."""
    return {item: len(item) for item in items}

# Good: Using type union syntax (Python 3.10+)
def get_value(key: str) -> str | None:
    """Get value or None if not found."""
    return data.get(key)
```

### Configuration Reference

All formatting standards are defined in `pyproject.toml` under `[tool.ruff]` and `[tool.ruff.format]`:

- `line-length = 88`
- `indent-width = 4`
- `target-version = "py313"`
- `quote-style = "double"`

Run `ruff format` to automatically format your code according to these standards. See [Testing Standards](#testing-standards) for pre-commit workflow.

### Naming Conventions

Python naming conventions ensure code is readable and follows community standards. These conventions are enforced by Ruff's pep8-naming rules.

**Variables and Functions**: snake_case

Use lowercase with underscores separating words for variable names and function names:

```python
# Good: snake_case for variables and functions
user_id = 12345
message_text = "Hello, world!"
total_count = 0

def process_message(message: str) -> str:
    """Process the incoming message."""
    return message.strip().lower()

def calculate_summary_length(text: str) -> int:
    """Calculate appropriate summary length based on text."""
    return min(len(text) // 10, 500)

# Bad: camelCase or PascalCase for variables/functions
userId = 12345
MessageText = "Hello, world!"

def ProcessMessage(message: str) -> str:
    return message.strip()
```

**Classes**: PascalCase

Use PascalCase (CapitalizedWords) for class names:

```python
# Good: PascalCase for classes
class MessageProcessor:
    """Processes incoming messages."""
    
    def __init__(self, bot_token: str):
        self.bot_token = bot_token
    
    def process(self, message: str) -> str:
        """Process a single message."""
        return message.strip()

class SummaryGenerator:
    """Generates summaries from text."""
    pass

class DatabaseConnection:
    """Manages database connections."""
    pass

# Bad: snake_case or other styles for classes
class message_processor:
    pass

class summary_Generator:
    pass
```

**Constants**: UPPER_SNAKE_CASE

Use uppercase with underscores for constants (module-level or class-level):

```python
# Good: UPPER_SNAKE_CASE for constants
MAX_MESSAGE_LENGTH = 4096
DEFAULT_TIMEOUT = 30
API_BASE_URL = "https://api.example.com"
RETRY_ATTEMPTS = 3

class Config:
    """Configuration constants."""
    DATABASE_URL = "postgresql://localhost/db"
    MAX_CONNECTIONS = 10
    CACHE_TTL = 3600

# Bad: lowercase or mixed case for constants
max_message_length = 4096
DefaultTimeout = 30
```

**Private Members**: _leading_underscore

Use a single leading underscore for internal/private attributes and methods:

```python
# Good: Leading underscore for private members
class MessageHandler:
    """Handles message processing."""
    
    def __init__(self):
        self._cache = {}  # Private attribute
        self._connection = None  # Private attribute
    
    def _validate_message(self, message: str) -> bool:
        """Private method for internal validation."""
        return len(message) > 0
    
    def process(self, message: str) -> str:
        """Public method."""
        if self._validate_message(message):
            return self._process_internal(message)
        return ""
    
    def _process_internal(self, message: str) -> str:
        """Private internal processing method."""
        return message.strip().lower()

# Bad: No underscore for private members
class MessageHandler:
    def __init__(self):
        self.cache = {}  # Looks public but intended as private
    
    def validate_message(self, message: str) -> bool:  # Looks public
        return len(message) > 0
```

**Note**: Double leading underscores (`__name`) trigger name mangling and should be used sparingly, typically only to avoid name conflicts in inheritance hierarchies.

### Import Ordering

Imports should be organized into three distinct groups, separated by blank lines. This organization is automatically enforced by Ruff's isort integration.

**Import Groups** (in order):

1. **Standard library imports** - Built-in Python modules
2. **Third-party imports** - External packages installed via pip
3. **Local imports** - Project-specific modules

Within each group, imports should be sorted alphabetically. Use `from` imports sparingly and prefer explicit imports for clarity.

**Example of Properly Ordered Imports**:

```python
# Standard library imports
import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Any

# Third-party imports
import requests
from sqlalchemy import create_engine
from telebot import TeleBot

# Local imports
from src.config import Config
from src.database import DatabaseConnection
from src.processors.message_processor import MessageProcessor
from src.utils.helpers import format_timestamp
```

**Automatic Enforcement**:

Ruff's isort functionality automatically organizes imports according to these rules. Run `ruff check --select I` to check import ordering, or `ruff check --select I --fix` to automatically fix import order issues.

**Configuration**:

Import ordering is configured in `pyproject.toml` under the Ruff lint rules with the `"I"` (isort) selector enabled.

## Code Quality and Linting

This project uses Ruff for code quality enforcement and linting. Ruff is a fast Python linter that combines the functionality of multiple tools (Flake8, isort, pyupgrade, and more) into a single, high-performance package. All linting rules are configured in `pyproject.toml`.

### Enabled Ruff Rules

The project enables a comprehensive set of lint rules to catch bugs, enforce best practices, and maintain code quality. Below are all enabled rule categories from `pyproject.toml`:

**Core Python Rules**:

- **E (pycodestyle errors)** - Enforces PEP 8 style guide errors (indentation, whitespace, line length violations)
- **F (Pyflakes)** - Detects various Python errors like unused imports, undefined names, and invalid syntax
- **W (pycodestyle warnings)** - Enforces PEP 8 style guide warnings (trailing whitespace, blank lines)
- **B (flake8-bugbear)** - Finds likely bugs and design problems (mutable default arguments, unused loop variables)
- **C90 (mccabe)** - Checks code complexity and warns about overly complex functions

**Import and Code Organization**:

- **I (isort)** - Enforces consistent import ordering (standard library, third-party, local)
- **TID (flake8-tidy-imports)** - Prevents banned imports and enforces import conventions
- **ICN (flake8-import-conventions)** - Enforces conventional import aliases (e.g., `import pandas as pd`)
- **INP (flake8-no-pep420)** - Requires `__init__.py` files in packages

**Code Modernization**:

- **UP (pyupgrade)** - Suggests modern Python syntax (f-strings, type hints, new union syntax)
- **FA (flake8-future-annotations)** - Enforces `from __future__ import annotations` for forward compatibility
- **FLY (flynt)** - Suggests converting old string formatting to f-strings

**Code Quality and Simplification**:

- **SIM (flake8-simplify)** - Suggests simpler alternatives for complex code patterns
- **C4 (flake8-comprehensions)** - Improves list/dict/set comprehensions
- **PIE (flake8-pie)** - Miscellaneous linting rules for cleaner code
- **PERF (Perflint)** - Detects performance anti-patterns
- **FURB (refurb)** - Suggests modern Python idioms and refactoring opportunities
- **RUF (Ruff-specific rules)** - Ruff's own custom linting rules

**Security**:

- **S (flake8-bandit)** - Detects common security issues (SQL injection, hardcoded passwords, unsafe functions)

**Testing**:

- **PT (flake8-pytest-style)** - Enforces pytest best practices and conventions

**Logging**:

- **LOG (flake8-logging)** - Enforces proper logging practices
- **G (flake8-logging-format)** - Checks logging format strings

**Type Checking and Annotations**:

- **ANN (flake8-annotations)** - Enforces type annotations on functions and methods
- **TCH (flake8-type-checking)** - Optimizes type checking imports with TYPE_CHECKING blocks
- **PYI (flake8-pyi)** - Enforces best practices for `.pyi` stub files

**Documentation**:

- **D (pydocstyle)** - Enforces docstring conventions (Google style in this project)
- **DOC (pydoclint)** - Validates docstring content matches function signatures

**Error Handling**:

- **EM (flake8-errmsg)** - Enforces proper exception message formatting
- **RET (flake8-return)** - Improves return statement patterns
- **RSE (flake8-raise)** - Improves exception raising patterns

**Code Cleanliness**:

- **ERA (eradicate)** - Detects commented-out code that should be removed
- **FIX (flake8-fixme)** - Detects TODO, FIXME, and XXX comments
- **T10 (flake8-debugger)** - Detects debugger statements (pdb, breakpoint)
- **T20 (flake8-print)** - Detects print statements that should use logging

**Best Practices**:

- **N (pep8-naming)** - Enforces PEP 8 naming conventions
- **A (flake8-builtins)** - Prevents shadowing Python builtins
- **ARG (flake8-unused-arguments)** - Detects unused function arguments
- **SLF (flake8-self)** - Detects private member access violations
- **SLOT (flake8-slots)** - Suggests using `__slots__` for memory optimization
- **COM (flake8-commas)** - Enforces trailing comma conventions
- **Q (flake8-quotes)** - Enforces consistent quote style (double quotes)
- **DTZ (flake8-datetimez)** - Enforces timezone-aware datetime usage
- **PTH (flake8-use-pathlib)** - Suggests using pathlib instead of os.path
- **ISC (flake8-implicit-str-concat)** - Detects implicit string concatenation issues
- **EXE (flake8-executable)** - Checks shebang lines in executable files
- **INT (flake8-gettext)** - Enforces internationalization best practices
- **ASYNC (flake8-async)** - Detects async/await anti-patterns

**Advanced Linting**:

- **PL (Pylint)** - Comprehensive linting rules from Pylint
- **PGH (pygrep-hooks)** - Additional pattern-based checks
- **CPY (flake8-copyright)** - Enforces copyright headers (if configured)

**Configuration Reference**:

All enabled rules are listed in `pyproject.toml` under `[tool.ruff.lint]` in the `select` array. Run `ruff check` to see all violations, or `ruff check --select RULE` to check specific rule categories.

For pre-commit workflow and quality checks, see [Testing Standards](#testing-standards).

### Ignored Rules and Rationale

While the project enables a comprehensive set of linting rules, certain rules are intentionally ignored because they conflict with project requirements or generate false positives. These ignored rules are configured in `pyproject.toml` under `[tool.ruff.lint]` in the `ignore` array.

**S603 - subprocess-without-shell-equals-true**:

This rule warns about using `subprocess` calls without explicitly setting `shell=True` or `shell=False`. It's ignored because:

- The project intentionally uses subprocess calls without shell expansion for security
- Explicitly setting `shell=False` is redundant when it's the default behavior
- The security concern (shell injection) is already mitigated by not using `shell=True`

```python
# This triggers S603 but is actually secure (shell=False is default)
import subprocess
result = subprocess.run(["yt-dlp", "--version"], capture_output=True)

# The rule wants this, but it's redundant
result = subprocess.run(["yt-dlp", "--version"], shell=False, capture_output=True)
```

**S607 - start-process-with-partial-executable-path**:

This rule warns about starting processes with partial executable paths (e.g., `"yt-dlp"` instead of `"/usr/bin/yt-dlp"`). It's ignored because:

- The project relies on executables being in the system PATH
- Using absolute paths would make the code less portable across different environments
- The executables used (yt-dlp, ffmpeg) are expected to be properly installed

```python
# This triggers S607 but is intentional for portability
subprocess.run(["yt-dlp", url], capture_output=True)

# The rule wants this, but it's not portable
subprocess.run(["/usr/local/bin/yt-dlp", url], capture_output=True)
```

**D100 - undocumented-public-module**:

This rule requires docstrings at the module level for all public modules. It's ignored because:

- Module-level docstrings are often redundant when the module name is self-explanatory
- Small utility modules don't always need extensive module documentation
- Function and class docstrings provide sufficient documentation in most cases

```python
# This triggers D100 but is acceptable for simple modules
# File: src/utils/helpers.py
import logging

def format_timestamp(timestamp: int) -> str:
    """Format Unix timestamp as human-readable string."""
    return datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d %H:%M:%S")

# The rule wants this, but it's often redundant
"""Helper utility functions for the AI Summarizer Bot.

This module contains various helper functions used throughout the application.
"""
import logging
# ... rest of code
```

**D401 - non-imperative-mood**:

This rule requires the first line of docstrings to be in imperative mood (e.g., "Return" instead of "Returns"). It's ignored because:

- AI-generated docstrings often use descriptive mood ("Returns", "Processes")
- The descriptive mood is more natural and equally clear
- Enforcing imperative mood would require manual editing of AI-generated docstrings

```python
# This triggers D401 but is acceptable (descriptive mood)
def calculate_summary_length(text: str) -> int:
    """Calculates the appropriate summary length based on text length."""
    return min(len(text) // 10, 500)

# The rule wants this (imperative mood)
def calculate_summary_length(text: str) -> int:
    """Calculate the appropriate summary length based on text length."""
    return min(len(text) // 10, 500)
```

**Why These Rules Are Ignored**:

These rules are ignored to balance code quality with practical development needs. The ignored rules either:

1. Generate false positives for intentionally secure code (S603, S607)
2. Require redundant documentation (D100)
3. Conflict with AI-generated documentation standards (D401)

The project still maintains high code quality through the 50+ other enabled rule categories.

### Inline Suppressions and Exclusions

Sometimes specific lines of code need to bypass linting rules for legitimate reasons. Ruff supports inline suppression comments and directory exclusions to handle these cases.

**When to Use Inline Suppressions**:

Use `# noqa: RULE_CODE` comments to suppress specific linting rules on individual lines when:

1. The violation is intentional and necessary for the code to work correctly
2. The rule generates a false positive for a specific case
3. Fixing the violation would make the code less readable or maintainable
4. External APIs or libraries require patterns that violate linting rules

**Inline Suppression Syntax**:

```python
# Suppress a single rule
result = eval(user_input)  # noqa: S307

# Suppress multiple rules
import os, sys  # noqa: E401, F401

# Suppress all rules on a line (use sparingly!)
complex_legacy_code()  # noqa

# Suppress rules for an entire file (at the top of the file)
# ruff: noqa: S603, S607
```

**Examples of Legitimate Inline Suppressions**:

```python
# Example 1: Intentional use of eval for configuration parsing
def parse_config_value(value: str) -> Any:
    """Parse configuration value that may contain Python expressions."""
    # We control the input source, so eval is safe here
    return eval(value)  # noqa: S307

# Example 2: Intentional print statement for CLI output
def display_results(results: list[str]) -> None:
    """Display results to console (CLI tool, not library)."""
    for result in results:
        print(result)  # noqa: T201

# Example 3: Complex type annotation that exceeds line length
def process_complex_data(
    data: dict[str, list[tuple[int, str, datetime]]],  # noqa: E501
) -> dict[str, list[tuple[int, str, datetime]]]:
    """Process complex nested data structure."""
    return data

# Example 4: Intentional TODO comment for future work
def calculate_advanced_metrics(data: list[int]) -> float:
    """Calculate advanced metrics from data."""
    # TODO: Implement advanced statistical analysis  # noqa: FIX002
    return sum(data) / len(data)
```

**When NOT to Use Inline Suppressions**:

Avoid using `# noqa` comments when:

- The code can be refactored to comply with the rule
- The violation indicates a real bug or security issue
- You're suppressing rules just to avoid fixing legitimate issues
- You're using `# noqa` without a specific rule code (suppresses all rules)

**Excluded Directories**:

Certain directories are excluded from linting entirely because they contain generated code, temporary files, or third-party code. These exclusions are configured in `pyproject.toml`:

**Excluded Directories**:

- **temp/** - Temporary files and scratch code not part of the main codebase
- **migrations/** - Database migration files (often auto-generated by Alembic)
- **scripts/** - Utility scripts that may not follow strict coding standards

**Configuration**:

```toml
# In pyproject.toml
[tool.ruff]
extend-exclude = ["temp", "migrations"]

[tool.ruff.lint]
exclude = ["scripts"]
```

**Why These Directories Are Excluded**:

- **temp/**: Contains experimental code, debugging scripts, and temporary files that don't need to meet production standards
- **migrations/**: Database migration files are often auto-generated and shouldn't be manually edited
- **scripts/**: Utility scripts may prioritize quick functionality over strict code quality

**Best Practices**:

1. Always specify the exact rule code when using `# noqa` (e.g., `# noqa: S307` not just `# noqa`)
2. Add a comment explaining why the suppression is necessary
3. Use inline suppressions sparingly - prefer fixing the code to comply with rules
4. Review suppressed violations periodically to see if they can be removed
5. Never suppress security rules (S*) without careful consideration and documentation

### Common Lint Violations and Fixes

Below are examples of common linting violations and how to fix them. These examples help you understand what Ruff is checking for and how to write compliant code.

#### Example 1: Unused Imports (F401)

**Violation**:

```python
import json
import logging
import requests  # Imported but never used

def process_data(data: dict) -> str:
    """Process data and return JSON string."""
    logging.info("Processing data")
    return json.dumps(data)
```

**Fix**:

```python
import json
import logging

def process_data(data: dict) -> str:
    """Process data and return JSON string."""
    logging.info("Processing data")
    return json.dumps(data)
```

**Explanation**: Remove imports that aren't used in the code. Unused imports clutter the namespace and slow down module loading.

#### Example 2: Mutable Default Arguments (B006)

**Violation**:

```python
def add_item(item: str, items: list = []) -> list:
    """Add item to list."""
    items.append(item)
    return items

# This causes bugs because the default list is shared across calls
result1 = add_item("first")   # ["first"]
result2 = add_item("second")  # ["first", "second"] - unexpected!
```

**Fix**:

```python
def add_item(item: str, items: list | None = None) -> list:
    """Add item to list."""
    if items is None:
        items = []
    items.append(item)
    return items

# Now each call gets its own list
result1 = add_item("first")   # ["first"]
result2 = add_item("second")  # ["second"] - correct!
```

**Explanation**: Never use mutable objects (lists, dicts, sets) as default arguments. Use `None` as the default and create the mutable object inside the function.

#### Example 3: Missing Type Annotations (ANN001, ANN201)

**Violation**:

```python
def calculate_total(prices, tax_rate):
    """Calculate total price with tax."""
    subtotal = sum(prices)
    return subtotal * (1 + tax_rate)
```

**Fix**:

```python
def calculate_total(prices: list[float], tax_rate: float) -> float:
    """Calculate total price with tax."""
    subtotal = sum(prices)
    return subtotal * (1 + tax_rate)
```

**Explanation**: Add type annotations to function parameters and return values. This enables static type checking and makes the code more self-documenting.

#### Example 4: Using Old String Formatting (UP031, UP032)

**Violation**:

```python
name = "Alice"
age = 30

# Old-style % formatting
message1 = "Hello, %s! You are %d years old." % (name, age)

# Old-style .format()
message2 = "Hello, {}! You are {} years old.".format(name, age)
```

**Fix**:

```python
name = "Alice"
age = 30

# Modern f-string
message = f"Hello, {name}! You are {age} years old."
```

**Explanation**: Use f-strings (Python 3.6+) instead of old-style string formatting. F-strings are more readable, faster, and less error-prone.

#### Example 5: Bare Exception Handling (E722, B001)

**Violation**:

```python
def fetch_data(url: str) -> dict:
    """Fetch data from URL."""
    try:
        response = requests.get(url)
        return response.json()
    except:  # Catches everything, including KeyboardInterrupt!
        return {}
```

**Fix**:

```python
def fetch_data(url: str) -> dict:
    """Fetch data from URL."""
    try:
        response = requests.get(url)
        return response.json()
    except requests.RequestException as e:
        logging.error(f"Failed to fetch data: {e}")
        return {}
```

**Explanation**: Never use bare `except:` clauses. Always specify the exception types you want to catch. Bare except catches system exceptions like `KeyboardInterrupt` and `SystemExit`, which should usually propagate.

#### Running Ruff

To check your code for violations:

```bash
# Check all files
ruff check

# Check specific files or directories
ruff check src/
ruff check src/processors/message_processor.py

# Auto-fix violations where possible
ruff check --fix

# Check specific rule categories
ruff check --select F,E  # Only check Pyflakes and pycodestyle errors
```

To format your code:

```bash
# Format all files
ruff format

# Format specific files
ruff format src/processors/message_processor.py

# Check formatting without making changes
ruff format --check
```

**Pre-Commit Workflow**:

Before committing code, always run:

1. `ruff check --fix` - Fix auto-fixable violations
2. `ruff format` - Format code consistently
3. `ruff check` - Verify no remaining violations
4. Review any remaining violations and fix manually or add `# noqa` with justification

## Documentation Standards

This project follows Google Docstrings Style for all Python documentation. Clear, consistent documentation helps developers understand code functionality, parameters, return values, and potential exceptions. All docstrings in this project are AI-generated following Google style conventions.

### Google Docstrings Style

**Standard Format**: Google Docstrings Style

The project uses Google Docstrings Style as the standard format for all Python docstrings. This style is widely adopted, highly readable, and well-supported by documentation tools like Sphinx (with the napoleon extension).

**Key Characteristics**:

- Clear section headers (Args, Returns, Raises, etc.)
- Readable indentation and formatting
- Concise but complete descriptions
- Type information in the description (though type hints are preferred in signatures)

**AI-Generated Docstrings**:

All docstrings in this project are AI-generated following Google style conventions. This ensures:

- Consistent formatting across the entire codebase
- Complete documentation for all public functions and classes
- Accurate descriptions that match the code implementation
- Proper documentation of parameters, return values, and exceptions

**Configuration**:

Google Docstrings Style is enforced by Ruff's pydocstyle rules (D* rules) configured in `pyproject.toml`. Note that rule D401 (imperative mood) is intentionally ignored to accommodate AI-generated docstrings that use descriptive mood.

For more on ignored rules, see [Code Quality and Linting](#code-quality-and-linting).

### Docstring Examples

Below are examples of properly formatted docstrings following Google style for both functions and classes.

#### Function Docstring Example

**Simple Function with Args and Returns**:

```python
def calculate_summary_length(text: str, max_length: int = 500) -> int:
    """Calculates the appropriate summary length based on text length.
    
    The function determines an optimal summary length by analyzing the input
    text length and applying a scaling factor, capped at the maximum length.
    
    Args:
        text: The input text to analyze for summary length calculation.
        max_length: The maximum allowed summary length. Defaults to 500.
    
    Returns:
        The calculated summary length as an integer, guaranteed to be
        less than or equal to max_length.
    
    Examples:
        >>> calculate_summary_length("Short text", max_length=100)
        50
        >>> calculate_summary_length("A" * 1000, max_length=200)
        200
    """
    base_length = len(text) // 10
    return min(base_length, max_length)
```

**Function with Raises Section**:

```python
def fetch_user_data(user_id: int, api_token: str) -> dict[str, Any]:
    """Fetches user data from the API.
    
    Retrieves complete user information including profile details,
    preferences, and activity history from the remote API endpoint.
    
    Args:
        user_id: The unique identifier for the user.
        api_token: The authentication token for API access.
    
    Returns:
        A dictionary containing user data with keys:
            - 'id': User ID (int)
            - 'name': User's full name (str)
            - 'email': User's email address (str)
            - 'created_at': Account creation timestamp (datetime)
    
    Raises:
        ValueError: If user_id is negative or zero.
        requests.HTTPError: If the API request fails.
        requests.Timeout: If the API request times out.
        KeyError: If the API response is missing required fields.
    
    Examples:
        >>> data = fetch_user_data(12345, "token_abc123")
        >>> print(data['name'])
        'John Doe'
    """
    if user_id <= 0:
        raise ValueError("user_id must be positive")
    
    response = requests.get(
        f"https://api.example.com/users/{user_id}",
        headers={"Authorization": f"Bearer {api_token}"},
        timeout=30
    )
    response.raise_for_status()
    
    data = response.json()
    if 'id' not in data or 'name' not in data:
        raise KeyError("API response missing required fields")
    
    return data
```

#### Class Docstring Example

**Class with Attributes and Methods**:

```python
class MessageProcessor:
    """Processes incoming messages and generates responses.
    
    This class handles message validation, content extraction, and response
    generation for the Telegram bot. It maintains internal state for caching
    and rate limiting.
    
    Attributes:
        bot_token: The Telegram bot authentication token.
        max_message_length: Maximum allowed message length in characters.
        cache: Internal cache for storing processed messages.
        rate_limiter: Rate limiting configuration for API calls.
    
    Examples:
        >>> processor = MessageProcessor(bot_token="abc123", max_length=4096)
        >>> response = processor.process("Hello, bot!")
        >>> print(response)
        'Message processed successfully'
    """
    
    def __init__(self, bot_token: str, max_length: int = 4096):
        """Initializes the MessageProcessor.
        
        Args:
            bot_token: The Telegram bot authentication token.
            max_length: Maximum message length. Defaults to 4096.
        
        Raises:
            ValueError: If bot_token is empty or max_length is not positive.
        """
        if not bot_token:
            raise ValueError("bot_token cannot be empty")
        if max_length <= 0:
            raise ValueError("max_length must be positive")
        
        self.bot_token = bot_token
        self.max_message_length = max_length
        self.cache: dict[str, str] = {}
        self.rate_limiter = RateLimiter(calls=30, period=60)
    
    def process(self, message: str) -> str:
        """Processes a single message and returns a response.
        
        Validates the message length, checks the cache for previous responses,
        and generates a new response if needed.
        
        Args:
            message: The incoming message text to process.
        
        Returns:
            The processed response text.
        
        Raises:
            ValueError: If message exceeds max_message_length.
            RateLimitError: If rate limit is exceeded.
        """
        if len(message) > self.max_message_length:
            raise ValueError(f"Message exceeds maximum length of {self.max_message_length}")
        
        # Check cache
        if message in self.cache:
            return self.cache[message]
        
        # Generate response
        response = self._generate_response(message)
        self.cache[message] = response
        return response
    
    def _generate_response(self, message: str) -> str:
        """Generates a response for the given message.
        
        Private method that handles the actual response generation logic.
        
        Args:
            message: The message to generate a response for.
        
        Returns:
            The generated response text.
        """
        # Response generation logic here
        return f"Processed: {message}"
```

**Key Elements in Examples**:

- **One-line summary**: Brief description of what the function/class does
- **Extended description**: More detailed explanation (optional but recommended)
- **Args section**: Each parameter with description
- **Returns section**: Description of return value and its structure
- **Raises section**: All exceptions that may be raised
- **Examples section**: Usage examples (optional but helpful)
- **Attributes section** (classes only): Class attributes and their purposes

### When Docstrings Are Required vs Optional

Understanding when to write docstrings helps maintain comprehensive documentation without over-documenting trivial code.

#### Docstrings Are Required For

**Public Functions and Methods**:

All public functions (those without a leading underscore) must have docstrings that document their purpose, parameters, return values, and exceptions.

```python
# Required: Public function needs docstring
def process_message(message: str, user_id: int) -> dict[str, Any]:
    """Processes incoming message and returns response data.
    
    Args:
        message: The message text to process.
        user_id: The ID of the user sending the message.
    
    Returns:
        Dictionary containing response data and metadata.
    """
    return {"response": message.upper(), "user_id": user_id}
```

**Public Classes**:

All public classes must have docstrings describing their purpose, responsibilities, and key attributes.

```python
# Required: Public class needs docstring
class DatabaseConnection:
    """Manages database connections and query execution.
    
    Attributes:
        connection_string: The database connection URL.
        pool_size: Maximum number of concurrent connections.
    """
    
    def __init__(self, connection_string: str, pool_size: int = 10):
        """Initializes the database connection.
        
        Args:
            connection_string: The database connection URL.
            pool_size: Maximum concurrent connections. Defaults to 10.
        """
        self.connection_string = connection_string
        self.pool_size = pool_size
```

**Complex Logic and Algorithms**:

Functions implementing complex algorithms, business logic, or non-obvious behavior must have detailed docstrings explaining the approach.

```python
# Required: Complex algorithm needs detailed docstring
def calculate_weighted_score(
    metrics: dict[str, float],
    weights: dict[str, float]
) -> float:
    """Calculates weighted score using normalized metrics and weights.
    
    The function normalizes all metric values to a 0-1 scale, applies
    the corresponding weights, and returns the sum. Metrics with missing
    weights are assigned a default weight of 1.0.
    
    Args:
        metrics: Dictionary mapping metric names to raw values.
        weights: Dictionary mapping metric names to weight values.
    
    Returns:
        The calculated weighted score as a float between 0 and 100.
    
    Raises:
        ValueError: If metrics dictionary is empty.
    """
    if not metrics:
        raise ValueError("metrics cannot be empty")
    
    # Normalization and calculation logic...
    return 0.0
```

**Public Module Functions**:

Any function defined at module level that's part of the public API must have a docstring.

#### Docstrings Are Optional For

**Private Functions and Methods**:

Private functions (those with a leading underscore) may omit docstrings if their purpose is clear from the name and they're simple.

```python
# Optional: Simple private method, purpose is clear
def _validate_input(self, value: str) -> bool:
    return len(value) > 0 and value.isalnum()

# But complex private methods should still have docstrings
def _calculate_internal_metrics(self, data: list[dict]) -> dict[str, float]:
    """Calculates internal performance metrics from raw data.
    
    This private method performs complex statistical analysis that's
    not obvious from the function name alone.
    
    Args:
        data: List of raw data dictionaries.
    
    Returns:
        Dictionary of calculated metric names to values.
    """
    # Complex calculation logic...
    return {}
```

**Simple Getters and Setters**:

Property getters and setters with obvious behavior may omit docstrings.

```python
class User:
    """Represents a user account."""
    
    def __init__(self, name: str, email: str):
        self._name = name
        self._email = email
    
    # Optional: Simple getter, purpose is obvious
    @property
    def name(self) -> str:
        return self._name
    
    # Optional: Simple setter, purpose is obvious
    @name.setter
    def name(self, value: str) -> None:
        self._name = value
    
    # Required: Getter with validation logic needs docstring
    @property
    def email(self) -> str:
        """Returns the user's email address.
        
        Returns:
            The validated email address.
        
        Raises:
            ValueError: If the stored email is invalid.
        """
        if not self._is_valid_email(self._email):
            raise ValueError("Invalid email address")
        return self._email
```

**Trivial Helper Functions**:

Very simple helper functions with self-explanatory names and obvious behavior may omit docstrings.

```python
# Optional: Trivial helper, purpose is completely obvious
def _is_empty(value: str) -> bool:
    return len(value) == 0

# Optional: Simple wrapper, purpose is clear
def _get_current_timestamp() -> int:
    return int(time.time())
```

**Test Functions**:

Test functions typically don't need docstrings because the test name should be descriptive enough.

```python
# Optional: Test function name is self-documenting
def test_process_message_returns_uppercase():
    result = process_message("hello", user_id=123)
    assert result["response"] == "HELLO"

# But complex test setups may benefit from docstrings
def test_database_connection_with_retry_logic():
    """Tests that database connections retry on transient failures.
    
    This test simulates network failures and verifies that the connection
    manager retries up to 3 times before raising an exception.
    """
    # Complex test setup and assertions...
    pass
```

### Inline Comment Standards

Inline comments explain complex logic within function bodies. Use them sparingly and only when the code's purpose isn't obvious.

**When to Use Inline Comments**:

Use inline comments for:

1. **Complex algorithms**: Explain non-obvious steps in calculations or logic
2. **Workarounds**: Document why unusual code patterns are necessary
3. **Performance optimizations**: Explain why code is written in a specific way
4. **Business logic**: Clarify domain-specific rules or requirements

**Good Inline Comments**:

```python
def calculate_discount(price: float, user_tier: str) -> float:
    """Calculates the discount amount based on user tier.
    
    Args:
        price: The original price.
        user_tier: The user's membership tier (bronze, silver, gold).
    
    Returns:
        The discount amount to subtract from the price.
    """
    # Base discount rates by tier (defined by business requirements)
    tier_rates = {"bronze": 0.05, "silver": 0.10, "gold": 0.15}
    base_discount = price * tier_rates.get(user_tier, 0.0)
    
    # Apply additional 5% discount for purchases over $100 (promotion rule)
    if price > 100:
        base_discount += price * 0.05
    
    # Cap discount at 30% of original price (business constraint)
    max_discount = price * 0.30
    return min(base_discount, max_discount)
```

**Bad Inline Comments** (avoid these):

```python
# Bad: Comment states the obvious
def process_items(items: list[str]) -> list[str]:
    # Loop through items
    for item in items:
        # Convert to uppercase
        item = item.upper()
        # Append to results
        results.append(item)
    # Return results
    return results

# Good: No comments needed, code is self-explanatory
def process_items(items: list[str]) -> list[str]:
    return [item.upper() for item in items]
```

**Inline Comment Style**:

- Use `#` followed by a single space
- Write complete sentences with proper capitalization and punctuation
- Place comments on the line before the code they explain (not at the end of the line)
- Keep comments concise but clear

```python
# Good: Comment on separate line, complete sentence
# Calculate the weighted average using the provided weights.
weighted_avg = sum(v * w for v, w in zip(values, weights)) / sum(weights)

# Bad: Comment at end of line, incomplete sentence
weighted_avg = sum(v * w for v, w in zip(values, weights)) / sum(weights)  # calc avg

# Bad: No capitalization or punctuation
# calculate weighted average
weighted_avg = sum(v * w for v, w in zip(values, weights)) / sum(weights)
```

**When NOT to Use Inline Comments**:

Avoid inline comments when:

- The code is self-explanatory from variable and function names
- The logic is straightforward and follows common patterns
- You're explaining what the code does (use docstrings instead)
- The comment would just repeat the code in English

**Refactor Instead of Commenting**:

Often, the need for a comment indicates that code should be refactored for clarity:

```python
# Bad: Comment needed because code is unclear
# Check if user has permission and is not banned and account is active
if u.p and not u.b and u.a:
    process_request()

# Good: Clear variable names eliminate need for comment
has_permission = user.has_permission
is_not_banned = not user.is_banned
is_active = user.is_active

if has_permission and is_not_banned and is_active:
    process_request()

# Even better: Extract to a well-named function
if user.can_process_request():
    process_request()
```

## Git Conventions

This project follows Conventional Commits specification for all Git commit messages. Consistent commit messages make the project history clear, enable automated changelog generation, and help team members understand changes at a glance.

### Conventional Commits Format

**Standard Format**: Conventional Commits

All commit messages in this project must follow the Conventional Commits specification. This format provides a structured way to communicate the nature of changes in the commit history.

**Commit Message Structure**:

```text
type(scope): subject

[optional body]

[optional footer]
```

**Components**:

1. **type** (required): The type of change being made (see valid types below)
2. **scope** (optional): The area of the codebase affected (e.g., auth, database, api)
3. **subject** (required): A brief description of the change in imperative mood
4. **body** (optional): A more detailed explanation of the change, its motivation, and context
5. **footer** (optional): Metadata such as breaking changes, issue references, or co-authors

**Type Field**:

The type must be one of the valid commit types (see next section). It communicates the intent of the change.

**Scope Field**:

The scope is optional but recommended for larger projects. It specifies which part of the codebase is affected:

- Use lowercase
- Keep it short and recognizable (e.g., `auth`, `database`, `telegram`, `summarizer`)
- Omit the scope for changes that affect multiple areas or the entire project

**Subject Line**:

The subject line is a brief summary of the change:

- Use imperative mood ("add" not "added" or "adds")
- Don't capitalize the first letter
- No period at the end
- Keep it under 50 characters when possible
- Be specific and descriptive

**Body Section**:

The body provides additional context about the change:

- Separate from subject with a blank line
- Wrap lines at 72 characters
- Explain what and why, not how (the code shows how)
- Use bullet points for multiple items
- Reference related issues or pull requests

**Footer Section**:

The footer contains metadata:

- Separate from body with a blank line
- Use for breaking changes: `BREAKING CHANGE: description`
- Reference issues: `Fixes #123`, `Closes #456`, `Refs #789`
- Credit co-authors: `Co-authored-by: Name <email@example.com>`

**Examples**:

```text
feat(telegram): add support for voice message transcription

Implements voice message handling using OpenAI Whisper API.
Users can now send voice messages and receive text transcriptions.

Refs #45
```

```text
fix(database): resolve connection pool exhaustion issue

The connection pool was not properly releasing connections after
failed queries, leading to pool exhaustion under high load.

This fix ensures connections are returned to the pool even when
exceptions occur during query execution.

Fixes #123
```

```text
docs: update installation instructions for Python 3.13

BREAKING CHANGE: Python 3.12 is no longer supported
```

### Commit Types and Gitmoji

**Valid Commit Types**:

The project recognizes the following commit types. Each type communicates a specific kind of change:

- **feat**: A new feature for the user or a significant addition to functionality
  - Example: `feat(summarizer): add support for PDF document summarization`
  - Use when: Adding new capabilities, endpoints, commands, or user-facing features

- **fix**: A bug fix that resolves incorrect behavior
  - Example: `fix(auth): prevent token expiration during active sessions`
  - Use when: Fixing bugs, errors, crashes, or incorrect behavior

- **docs**: Documentation changes only (no code changes)
  - Example: `docs(readme): add troubleshooting section for common errors`
  - Use when: Updating README, docstrings, comments, or documentation files

- **style**: Code style changes that don't affect functionality (formatting, whitespace, etc.)
  - Example: `style: apply ruff formatting to all Python files`
  - Use when: Running formatters, fixing linting issues, adjusting whitespace

- **refactor**: Code changes that neither fix bugs nor add features (restructuring)
  - Example: `refactor(database): extract query logic into separate module`
  - Use when: Improving code structure, extracting functions, renaming variables

- **test**: Adding or updating tests (no production code changes)
  - Example: `test(summarizer): add property tests for text length validation`
  - Use when: Adding unit tests, integration tests, or test fixtures

- **chore**: Maintenance tasks, dependency updates, build changes (no production code changes)
  - Example: `chore: update dependencies to latest versions`
  - Use when: Updating dependencies, modifying build scripts, changing CI configuration

**Optional Gitmoji Usage**:

Gitmoji are emoji that provide visual categorization of commits. Their use is optional but can make commit history more scannable and visually appealing.

**Common Gitmoji for Each Type**:

- **feat**: ✨ `:sparkles:` - Introduce new features
- **fix**: 🐛 `:bug:` - Fix a bug
- **docs**: 📝 `:memo:` - Add or update documentation
- **style**: 🎨 `:art:` - Improve structure/format of code
- **refactor**: ♻️ `:recycle:` - Refactor code
- **test**: ✅ `:white_check_mark:` - Add or update tests
- **chore**: 🔧 `:wrench:` - Add or update configuration files

**Additional Useful Gitmoji**:

- 🚀 `:rocket:` - Deploy stuff
- 🔒 `:lock:` - Fix security issues
- ⚡ `:zap:` - Improve performance
- 🔥 `:fire:` - Remove code or files
- 🚑 `:ambulance:` - Critical hotfix
- 💄 `:lipstick:` - Add or update UI and style files
- 🌐 `:globe_with_meridians:` - Internationalization and localization
- 🔖 `:bookmark:` - Release / Version tags

**Using Gitmoji in Commits**:

When using gitmoji, place it at the beginning of the commit message, before the type:

```text
✨ feat(telegram): add voice message transcription support
🐛 fix(database): resolve connection pool exhaustion
📝 docs: update installation instructions
```

Or use the emoji code in the commit message:

```text
:sparkles: feat(telegram): add voice message transcription support
:bug: fix(database): resolve connection pool exhaustion
:memo: docs: update installation instructions
```

**Gitmoji Best Practices**:

- Use gitmoji consistently across the project (all commits or none)
- Choose the most appropriate emoji for the change
- Don't use multiple emoji in a single commit message
- Ensure emoji don't obscure the commit type and message
- Remember that gitmoji are optional - clear commit messages are more important

**Reference**: For a complete list of gitmoji, see [gitmoji.dev](https://gitmoji.dev)

### Commit Message Examples

Below are examples of properly formatted commit messages demonstrating various scenarios, with and without scope, body, and footer sections.

#### Example 1: Simple Feature Addition (No Scope)

```text
feat: add user authentication system

Implements JWT-based authentication for API endpoints.
Users can now register, login, and access protected resources.

Refs #12
```

#### Example 2: Bug Fix with Scope

```text
fix(telegram): handle rate limiting errors gracefully

Previously, rate limiting errors from Telegram API would crash
the bot. Now they are caught and retried with exponential backoff.

Fixes #67
```

#### Example 3: Documentation Update (Minimal)

```text
docs: add API usage examples to README
```

#### Example 4: Refactoring with Detailed Body

```text
refactor(summarizer): extract text preprocessing into separate module

The summarizer module was becoming too large and handling multiple
responsibilities. This change extracts all text preprocessing logic
(cleaning, tokenization, normalization) into a dedicated module.

Benefits:
- Improved testability of preprocessing logic
- Better separation of concerns
- Easier to add new preprocessing steps

No functional changes to the summarization behavior.
```

#### Example 5: Breaking Change with Footer

```text
feat(api): migrate to v2 API endpoints

Updates all API endpoints to use the new v2 structure with improved
response formats and better error handling.

BREAKING CHANGE: All API endpoints now use /api/v2/ prefix instead of
/api/v1/. Clients must update their endpoint URLs. The response format
has changed from snake_case to camelCase for JSON fields.

Migration guide: docs/migration-v1-to-v2.md
```

#### Example 6: Chore with Gitmoji

```text
🔧 chore: update Python dependencies to latest versions

Updates all dependencies in pyproject.toml to their latest compatible
versions. All tests pass with the updated dependencies.

Updated packages:
- requests: 2.31.0 -> 2.32.0
- sqlalchemy: 2.0.23 -> 2.0.25
- telebot: 4.14.0 -> 4.15.0
```

#### Example 7: Multiple Issue References

```text
fix(database): prevent duplicate entries in message cache

Adds unique constraint on (user_id, message_hash) to prevent duplicate
cache entries. Also adds database migration for existing data.

Fixes #89
Closes #102
Refs #95
```

#### Example 8: Co-authored Commit

```text
feat(summarizer): implement multi-language support

Adds support for summarizing text in 15 languages using language-specific
models. Automatically detects input language and selects appropriate model.

Supported languages: English, Spanish, French, German, Italian, Portuguese,
Russian, Chinese, Japanese, Korean, Arabic, Hindi, Turkish, Polish, Dutch

Co-authored-by: Jane Smith <jane@example.com>
Co-authored-by: Bob Johnson <bob@example.com>
```

#### Example 9: Style Change (Minimal)

```text
style: apply ruff formatting to all source files
```

#### Example 10: Test Addition with Scope

```text
✅ test(auth): add property tests for token validation

Implements property-based tests using Hypothesis to verify token
validation logic across a wide range of inputs.

Tests cover:
- Valid tokens with various expiration times
- Malformed tokens
- Expired tokens
- Tokens with invalid signatures
```

**Key Takeaways from Examples**:

- **Subject line**: Always clear, concise, and in imperative mood
- **Scope**: Used when change affects a specific module or component
- **Body**: Provides context, motivation, and details when needed
- **Footer**: Contains metadata like issue references and breaking changes
- **Gitmoji**: Optional but can improve visual scanning of commit history
- **Consistency**: All commits follow the same structure and conventions

**Commit Message Checklist**:

Before committing, verify your message:

- [ ] Starts with a valid type (feat, fix, docs, style, refactor, test, chore)
- [ ] Includes scope if change affects a specific component
- [ ] Subject line is in imperative mood and under 50 characters
- [ ] Subject line doesn't end with a period
- [ ] Body (if present) explains what and why, not how
- [ ] Body lines are wrapped at 72 characters
- [ ] Footer includes issue references if applicable
- [ ] Breaking changes are clearly marked with `BREAKING CHANGE:`
- [ ] Gitmoji (if used) is appropriate for the change type

## Markdown Standards

This project follows strict markdown formatting standards to ensure consistent, readable documentation across all markdown files. All markdown linting rules are enforced by markdownlint, configured in `.markdownlint-cli2.jsonc`.

### Markdownlint Configuration

**Configuration File**: `.markdownlint-cli2.jsonc`

The project uses markdownlint to enforce markdown formatting standards. The configuration file defines all markdown linting rules and specifies which files to ignore during linting.

**Current Configuration**:

The `.markdownlint-cli2.jsonc` file enables the default markdownlint ruleset, which includes comprehensive checks for:

- Heading hierarchy and structure
- List formatting and consistency
- Code block formatting
- Link formatting
- Line length limits
- Trailing whitespace
- Blank line requirements
- And many other markdown best practices

**Ignored Files**:

Certain files are excluded from markdown linting:

- `**/CLAUDE.md` - Session management files with custom formatting

**Running Markdownlint**:

To check markdown files for violations:

```bash
# Check all markdown files
markdownlint-cli2 "**/*.md"

# Check specific files
markdownlint-cli2 "docs/*.md"

# Fix auto-fixable issues
markdownlint-cli2 --fix "**/*.md"
```

**Configuration Reference**:

For details on all enabled rules, see the [markdownlint rules documentation](https://github.com/DavidAnson/markdownlint/blob/main/doc/Rules.md). The default ruleset is comprehensive and follows widely-accepted markdown best practices.

For pre-commit workflow, see [Testing Standards](#testing-standards).

### Heading Hierarchy

Proper heading hierarchy ensures documents are well-structured, accessible, and easy to navigate.

**Single H1 Per Document**:

Each markdown document should have exactly one level-1 heading (`#`) at the top, serving as the document title:

```markdown
# Style Guide

## Introduction

### Purpose

This is the correct heading hierarchy.
```

**Proper Nesting**:

Headings should be nested in order without skipping levels. Don't jump from H1 to H3:

```markdown
# Good: Proper heading hierarchy
# Document Title

## Section 1

### Subsection 1.1

#### Sub-subsection 1.1.1

## Section 2

### Subsection 2.1
```

```markdown
# Bad: Skips heading levels
# Document Title

### Subsection (skipped H2!)

##### Sub-subsection (skipped H3 and H4!)
```

**Heading Content**:

- Use sentence case or title case consistently throughout the document
- Keep headings concise and descriptive
- Avoid punctuation at the end of headings (no periods, colons, etc.)
- Use meaningful headings that describe the content

```markdown
# Good: Clear, concise headings
## Python Code Formatting
### Naming Conventions
#### Variables and Functions

# Bad: Vague or poorly formatted headings
## Code stuff:
### things
#### Some Random Notes...
```

**Heading Spacing**:

Surround headings with blank lines for readability:

```markdown
# Good: Blank lines around headings

Some content here.

## Next Section

More content here.

# Bad: No blank lines
Some content here.
## Next Section
More content here.
```

### Code Blocks

Code blocks should always include language identifiers for proper syntax highlighting and clarity.

**Fenced Code Blocks with Language Identifiers**:

Always specify the language after the opening backticks:

````markdown
# Good: Language identifier specified
```python
def hello_world():
    """Print hello world."""
    print("Hello, world!")
```

```bash
# Run the application
python main.py
```

```json
{
  "name": "example",
  "version": "1.0.0"
}
```

# Bad: No language identifier
```
def hello_world():
    print("Hello, world!")
```
````

**Common Language Identifiers**:

- `python` - Python code
- `bash` or `sh` - Shell commands
- `json` - JSON data
- `yaml` - YAML configuration
- `toml` - TOML configuration
- `markdown` or `md` - Markdown examples
- `text` - Plain text (when no syntax highlighting is needed)
- `sql` - SQL queries
- `javascript` or `js` - JavaScript code
- `typescript` or `ts` - TypeScript code

**Inline Code**:

Use single backticks for inline code references:

```markdown
# Good: Inline code with backticks
The `process_message()` function handles incoming messages.
Set the `MAX_LENGTH` constant to 4096.
Run `ruff check` to verify code quality.

# Bad: No backticks for code references
The process_message() function handles incoming messages.
Set the MAX_LENGTH constant to 4096.
```

**Code Block Spacing**:

Surround code blocks with blank lines:

````markdown
# Good: Blank lines around code blocks

Here's an example:

```python
def example():
    pass
```

The code above demonstrates...

# Bad: No blank lines

Here's an example:
```python
def example():
    pass
```
The code above demonstrates...
````

### Link Formatting

Consistent link formatting improves readability and maintainability of markdown documents.

**Inline Links**:

Use inline links for most references:

```markdown
# Good: Inline links
See the [Python documentation](https://docs.python.org/) for details.
Check out [Ruff](https://github.com/astral-sh/ruff) for linting.
Read the [style guide](docs/style-guide.md) for conventions.

# Bad: Bare URLs
See https://docs.python.org/ for details.
```

**Reference-Style Links**:

Use reference-style links for repeated URLs or to improve readability in dense text:

```markdown
# Good: Reference-style links for repeated URLs
The [Ruff documentation][ruff] provides detailed information.
See the [Ruff GitHub repository][ruff] for source code.

[ruff]: https://github.com/astral-sh/ruff

# Also good: Numbered references
Check the [Python docs][1] and [Ruff docs][2] for more information.

[1]: https://docs.python.org/
[2]: https://github.com/astral-sh/ruff
```

**Link Text**:

- Use descriptive link text that makes sense out of context
- Avoid generic text like "click here" or "this link"
- Keep link text concise but meaningful

```markdown
# Good: Descriptive link text
Read the [installation guide](docs/installation.md) to get started.
See [Conventional Commits specification](https://www.conventionalcommits.org/) for commit format details.

# Bad: Generic link text
Click [here](docs/installation.md) to get started.
See [this link](https://www.conventionalcommits.org/) for details.
```

**Internal Links**:

Use relative paths for internal project links:

```markdown
# Good: Relative paths for internal links
See [style-guide.md](docs/style-guide.md) for coding conventions.
Check [README.md](README.md) for project overview.

# Bad: Absolute paths or URLs for internal links
See [style-guide.md](https://github.com/user/repo/blob/main/docs/style-guide.md)
```

**Anchor Links**:

Use anchor links to reference sections within the same document:

```markdown
# Good: Anchor links for internal navigation
See [Python Code Formatting](#python-code-formatting) for details.
Jump to [Error Handling](#error-handling) section.

# Note: Anchors are lowercase with hyphens replacing spaces
```

### List Formatting

Consistent list formatting ensures readability and proper rendering across different markdown viewers.

**Unordered Lists**:

Use `-` (hyphen) for unordered list markers consistently:

```markdown
# Good: Consistent hyphen markers
- First item
- Second item
- Third item
  - Nested item
  - Another nested item
- Fourth item

# Bad: Mixed markers
- First item
* Second item
+ Third item
```

**Ordered Lists**:

Use `1.` for all ordered list items (auto-numbering):

```markdown
# Good: Sequential numbering
1. First step
2. Second step
3. Third step
   1. Nested step
   2. Another nested step
4. Fourth step

# Also acceptable: All 1s (auto-numbered by markdown)
1. First step
1. Second step
1. Third step
```

**List Spacing**:

Surround lists with blank lines and use consistent spacing within lists:

```markdown
# Good: Blank lines around lists

Here's a list of items:

- Item one
- Item two
- Item three

The list above shows...

# Bad: No blank lines
Here's a list of items:
- Item one
- Item two
- Item three
The list above shows...
```

**List Indentation**:

Use 2 spaces for nested list items:

```markdown
# Good: 2-space indentation for nested items
- Top level item
  - Nested item
    - Deeply nested item
  - Another nested item
- Another top level item

# Bad: Inconsistent indentation
- Top level item
    - Nested item (4 spaces)
      - Deeply nested item (6 spaces)
```

**Multi-Paragraph List Items**:

Indent continuation paragraphs to align with the list item text:

```markdown
# Good: Proper indentation for multi-paragraph items
1. First item with a long description.

   This is a continuation paragraph that belongs to the first item.
   It's indented to align with the item text.

2. Second item.

   Another continuation paragraph.
```

**Task Lists**:

Use `- [ ]` for unchecked tasks and `- [x]` for checked tasks:

```markdown
# Good: Task list formatting
- [x] Completed task
- [ ] Pending task
- [ ] Another pending task
  - [x] Completed subtask
  - [ ] Pending subtask
```

### Tables vs Lists

Choose between tables and lists based on the data structure and readability requirements.

**Use Tables When**:

- Presenting structured data with multiple columns
- Comparing items across multiple attributes
- Showing relationships between data points
- Data has a clear tabular structure

```markdown
# Good: Table for structured data
| Feature | Python 3.12 | Python 3.13 |
|---------|-------------|-------------|
| Performance | Fast | Faster |
| Type hints | Good | Better |
| Pattern matching | Yes | Yes |
```

**Use Lists When**:

- Presenting a simple sequence of items
- Items don't have multiple attributes to compare
- Hierarchical or nested information
- Narrative or descriptive content

```markdown
# Good: List for simple sequence
Supported features:

- User authentication
- Message processing
- Summary generation
- Database caching
```

**Table Formatting**:

When using tables, follow these conventions:

```markdown
# Good: Well-formatted table with alignment
| Column 1 | Column 2 | Column 3 |
|----------|----------|----------|
| Value 1  | Value 2  | Value 3  |
| Value 4  | Value 5  | Value 6  |

# Good: Alignment indicators
| Left aligned | Center aligned | Right aligned |
|:-------------|:--------------:|--------------:|
| Text         | Text           | 123           |
| More text    | More text      | 456           |

# Bad: Inconsistent spacing
| Column 1|Column 2 |Column 3|
|---|---|---|
|Value 1|Value 2|Value 3|
```

**When to Avoid Tables**:

- For simple key-value pairs (use definition lists or bullet points)
- When content is too wide and causes horizontal scrolling
- For deeply nested or hierarchical data (use nested lists)
- When items have varying numbers of attributes

```markdown
# Good: Simple list instead of single-column table
Configuration options:

- `MAX_LENGTH`: Maximum message length (default: 4096)
- `TIMEOUT`: Request timeout in seconds (default: 30)
- `RETRY_ATTEMPTS`: Number of retry attempts (default: 3)

# Bad: Unnecessary table for simple list
| Configuration Option | Description |
|---------------------|-------------|
| MAX_LENGTH | Maximum message length (default: 4096) |
| TIMEOUT | Request timeout in seconds (default: 30) |
| RETRY_ATTEMPTS | Number of retry attempts (default: 3) |
```

**Complex Data**:

For complex data that doesn't fit well in either tables or lists, consider:

- Breaking into multiple smaller tables or lists
- Using code blocks with structured formats (JSON, YAML)
- Creating separate documentation pages
- Using diagrams or visual representations

## File Organization

This project follows a structured directory layout to organize source code, documentation, configuration files, and supporting resources. Understanding this organization helps developers locate files quickly and maintain consistency when adding new code.

### Directory Structure

The project uses a standard Python project layout with clearly defined purposes for each top-level directory.

#### src/ - Application Source Code

**Purpose**: Contains all production Python code for the AI Summarizer Telegram Bot application.

**Contents**:

- Core application modules and packages
- Business logic and domain models
- API clients and integrations
- Database models and queries
- Utility functions and helpers

**Organization**:

- Use packages (directories with `__init__.py`) to group related modules
- Keep module files focused on a single responsibility
- Place shared utilities in `src/utils/`
- Place database models in `src/models/` or `src/database/`

**Example Structure**:

```text
src/
├── __init__.py
├── main.py                 # Application entry point
├── config.py               # Configuration management
├── bot/                    # Telegram bot logic
│   ├── __init__.py
│   ├── handlers.py         # Message handlers
│   └── commands.py         # Bot commands
├── summarizer/             # Summarization logic
│   ├── __init__.py
│   ├── processor.py        # Text processing
│   └── generator.py        # Summary generation
├── database/               # Database layer
│   ├── __init__.py
│   ├── models.py           # SQLAlchemy models
│   └── queries.py          # Database queries
└── utils/                  # Shared utilities
    ├── __init__.py
    └── helpers.py          # Helper functions
```

**Best Practices**:

- All production code goes in `src/`, never in the project root
- Use meaningful package names that reflect functionality
- Keep the `src/` directory clean - no test files, docs, or configs
- Import from `src` using absolute imports: `from src.bot.handlers import process_message`

#### docs/ - Documentation Files

**Purpose**: Contains all project documentation including guides, specifications, and reference materials.

**Contents**:

- README files and getting started guides
- Architecture documentation
- API documentation
- Style guides and coding standards
- Design documents and specifications
- User guides and tutorials

**Organization**:

- Use markdown format for all documentation
- Create subdirectories for different documentation types if needed
- Keep documentation close to the code it describes
- Use clear, descriptive filenames

**Example Structure**:

```text
docs/
├── style-guide.md          # This document
├── architecture.md         # System architecture
├── api-reference.md        # API documentation
├── deployment.md           # Deployment guide
└── development.md          # Development setup
```

**Best Practices**:

- Keep documentation up-to-date with code changes
- Use relative links when referencing other docs or code files
- Include code examples in documentation
- Follow markdown standards defined in this style guide

#### scripts/ - Utility Scripts

**Purpose**: Contains standalone utility scripts for development, deployment, and maintenance tasks.

**Contents**:

- Database migration scripts
- Data import/export scripts
- Development setup scripts
- Deployment automation scripts
- One-off maintenance tasks

**Organization**:

- Use descriptive script names that indicate their purpose
- Add shebang lines (`#!/usr/bin/env python3`) for executable scripts
- Include docstrings explaining what each script does
- Make scripts executable: `chmod +x scripts/script_name.py`

**Example Structure**:

```text
scripts/
├── setup_dev_env.sh        # Development environment setup
├── migrate_database.py     # Database migration helper
├── import_data.py          # Data import utility
└── deploy.sh               # Deployment script
```

**Best Practices**:

- Scripts should be runnable from the project root
- Use command-line arguments for script configuration
- Include usage instructions in script docstrings or comments
- Scripts are excluded from linting (see Code Quality section)
- Prefer scripts over manual commands for repeatable tasks

#### migrations/ - Database Migrations

**Purpose**: Contains database migration files managed by Alembic or similar migration tools.

**Contents**:

- Auto-generated migration scripts
- Schema version history
- Migration configuration

**Organization**:

- Never manually edit migration files after they're created
- Use descriptive migration messages: `alembic revision -m "add user table"`
- Keep migrations in chronological order
- Test migrations in development before applying to production

**Example Structure**:

```text
migrations/
├── versions/               # Migration version files
│   ├── 001_initial.py
│   ├── 002_add_user_table.py
│   └── 003_add_message_index.py
└── env.py                  # Alembic environment config
```

**Best Practices**:

- Migrations are excluded from linting (see Code Quality section)
- Always review auto-generated migrations before committing
- Test both upgrade and downgrade paths
- Never modify committed migrations - create new ones instead
- Keep migrations small and focused on single changes

#### templates/ - Template Files

**Purpose**: Contains template files for code generation, documentation, or message formatting.

**Contents**:

- Message templates for bot responses
- Email templates
- Code generation templates
- Configuration file templates

**Organization**:

- Use appropriate file extensions for template types (`.jinja2`, `.txt`, `.html`)
- Group templates by purpose in subdirectories
- Use clear, descriptive template names

**Example Structure**:

```text
templates/
├── messages/               # Bot message templates
│   ├── welcome.txt
│   ├── error.txt
│   └── summary.txt
└── emails/                 # Email templates
    └── notification.html
```

**Best Practices**:

- Keep templates separate from code logic
- Use template engines (Jinja2) for complex templates
- Document template variables and their expected types
- Test templates with sample data

#### temp/ - Temporary Files

**Purpose**: Contains temporary files, scratch work, and files that should not be committed to version control.

**Contents**:

- Downloaded files during processing
- Temporary data files
- Debug output files
- Experimental code and prototypes

**Organization**:

- This directory is gitignored - nothing here is committed
- Clean up temp files regularly
- Use unique filenames to avoid conflicts
- Consider using system temp directories for truly temporary files

**Example Structure**:

```text
temp/
├── downloads/              # Downloaded files
├── cache/                  # Cached data
└── debug/                  # Debug output
```

**Best Practices**:

- Never commit files from `temp/` to version control
- Temp directory is excluded from linting (see Code Quality section)
- Application code should handle missing temp directory gracefully
- Consider using Python's `tempfile` module for temporary files
- Clean up temp files after processing to avoid disk space issues

### File and Module Naming Conventions

Consistent naming conventions make the codebase more navigable and predictable.

#### Python Module Naming

**Standard**: Use lowercase with underscores (snake_case) for all Python module and package names.

**Rules**:

- Module names should be short, lowercase, and descriptive
- Use underscores to separate words for readability
- Avoid using hyphens (not valid in Python imports)
- Avoid single-letter module names except for very common abbreviations

**Examples**:

```text
# Good: Clear, descriptive module names
message_processor.py
database_connection.py
text_summarizer.py
api_client.py
user_authentication.py

# Bad: Incorrect naming styles
MessageProcessor.py         # PascalCase (use for classes, not modules)
message-processor.py        # Hyphens (not importable)
mp.py                       # Too abbreviated
messageprocessor.py         # No underscores (hard to read)
```

**Package Naming**:

Packages (directories with `__init__.py`) follow the same rules as modules:

```text
# Good: Package names
src/
├── bot/
├── summarizer/
├── database/
└── utils/

# Bad: Package names
src/
├── Bot/                    # PascalCase
├── text-summarizer/        # Hyphens
└── db/                     # Too abbreviated
```

**Import Examples**:

```python
# Good: Imports with proper module names
from src.message_processor import MessageProcessor
from src.database_connection import DatabaseConnection
import src.text_summarizer as summarizer

# Bad: Would fail due to incorrect naming
from src.message-processor import MessageProcessor  # Syntax error
from src.MessageProcessor import MessageProcessor   # Module not found
```

#### Test File Naming Standards

**Standard**: Test files should be named `test_*.py` or `*_test.py` to be automatically discovered by pytest.

**Preferred Pattern**: `test_<module_name>.py`

This pattern makes it clear which module each test file covers and groups test files together when sorted alphabetically.

**Rules**:

- Test files must start with `test_` or end with `_test.py`
- Test file names should mirror the module they test
- Place test files in a `tests/` directory at the project root
- Mirror the `src/` structure within `tests/` for organization

**Examples**:

```text
# Good: Test file naming
tests/
├── test_message_processor.py      # Tests src/message_processor.py
├── test_database_connection.py    # Tests src/database_connection.py
├── test_text_summarizer.py        # Tests src/text_summarizer.py
└── bot/
    ├── test_handlers.py            # Tests src/bot/handlers.py
    └── test_commands.py            # Tests src/bot/commands.py

# Also acceptable: Alternative pattern
tests/
├── message_processor_test.py
├── database_connection_test.py
└── text_summarizer_test.py

# Bad: Test file naming
tests/
├── message_processor.py            # Missing test_ prefix
├── test_mp.py                      # Abbreviated name
├── MessageProcessorTest.py         # PascalCase
└── test-message-processor.py       # Hyphens
```

**Test Function Naming**:

Test functions within test files should follow the pattern `test_<functionality>_<scenario>`:

```python
# Good: Descriptive test function names
def test_process_message_returns_uppercase():
    """Test that process_message converts text to uppercase."""
    result = process_message("hello")
    assert result == "HELLO"

def test_process_message_handles_empty_string():
    """Test that process_message handles empty input."""
    result = process_message("")
    assert result == ""

def test_process_message_raises_error_on_none():
    """Test that process_message raises TypeError for None input."""
    with pytest.raises(TypeError):
        process_message(None)

# Bad: Vague or poorly named test functions
def test1():                        # No description
def test_process():                 # Missing scenario
def testProcessMessage():           # camelCase
def test_it_works():                # Too vague
```

#### Temporary and Generated Files

**Standards**: Temporary and generated files should follow clear naming patterns and be properly gitignored.

**Temporary Files**:

- Use `.tmp` extension for temporary files
- Include timestamps or unique IDs in filenames to avoid conflicts
- Store in the `temp/` directory
- Clean up after processing

**Examples**:

```text
# Good: Temporary file naming
temp/download_20240115_143022.tmp
temp/cache_user_12345.tmp
temp/processing_a3f2b1c4.tmp

# Bad: Temporary file naming
download.txt                        # No .tmp extension, unclear purpose
temp1.tmp                           # Non-descriptive name
user_cache.tmp                      # Missing unique identifier
```

**Generated Files**:

- Use clear naming that indicates the file is generated
- Include `.generated` in the filename or use a `generated/` directory
- Add comments at the top of generated files warning against manual edits
- Gitignore generated files that can be recreated

**Examples**:

```text
# Good: Generated file naming
src/database/models.generated.py
docs/api-reference.generated.md
config/settings.generated.json

# Or use a dedicated directory
generated/
├── api_client.py
├── database_schema.py
└── config.json
```

**Gitignore Patterns**:

Ensure temporary and generated files are properly gitignored:

```gitignore
# Temporary files
temp/
*.tmp
*.temp
*.cache

# Generated files
*.generated.*
generated/
__pycache__/
*.pyc
.pytest_cache/
.coverage
htmlcov/

# Build artifacts
dist/
build/
*.egg-info/
```

**Best Practices**:

- Always clean up temporary files after use
- Document which files are generated and how to regenerate them
- Never manually edit generated files
- Use Python's `tempfile` module for system-managed temporary files
- Include generation timestamps in generated files for tracking

## Error Handling

This project follows consistent error handling and logging practices to ensure robust, maintainable, and debuggable code. Proper exception handling prevents crashes, provides meaningful error messages, and helps diagnose issues in production. Structured logging enables monitoring, debugging, and auditing of application behavior.

### Exception Handling Patterns

Python's exception handling mechanism allows code to gracefully handle errors and unexpected conditions. This section documents when and how to use exceptions effectively.

#### When to Create Custom Exception Classes

Custom exception classes provide semantic meaning to errors and enable precise exception handling. Create custom exception classes when:

**1. Domain-Specific Errors**:

Create custom exceptions for errors specific to your application domain:

```python
# Good: Custom exceptions for domain-specific errors
class MessageTooLongError(ValueError):
    """Raised when a message exceeds the maximum allowed length."""
    
    def __init__(self, message_length: int, max_length: int):
        self.message_length = message_length
        self.max_length = max_length
        super().__init__(
            f"Message length {message_length} exceeds maximum {max_length}"
        )

class SummarizationError(Exception):
    """Base exception for summarization-related errors."""
    pass

class ModelNotAvailableError(SummarizationError):
    """Raised when the requested summarization model is not available."""
    pass

class InsufficientTextError(SummarizationError):
    """Raised when text is too short to summarize meaningfully."""
    pass

# Usage
def process_message(message: str, max_length: int = 4096) -> str:
    """Process incoming message."""
    if len(message) > max_length:
        raise MessageTooLongError(len(message), max_length)
    return message.strip()
```

**2. Error Hierarchies**:

Create exception hierarchies to enable catching related errors at different levels of specificity:

```python
# Good: Exception hierarchy for related errors
class DatabaseError(Exception):
    """Base exception for database-related errors."""
    pass

class ConnectionError(DatabaseError):
    """Raised when database connection fails."""
    pass

class QueryError(DatabaseError):
    """Raised when a database query fails."""
    pass

class TransactionError(DatabaseError):
    """Raised when a database transaction fails."""
    pass

# Usage: Catch specific errors or the entire category
try:
    execute_query(sql)
except QueryError as e:
    logging.error(f"Query failed: {e}")
    # Handle query-specific error
except DatabaseError as e:
    logging.error(f"Database error: {e}")
    # Handle any database error
```

**3. Adding Context to Standard Exceptions**:

Extend standard exceptions to add application-specific context:

```python
# Good: Custom exception with additional context
class ConfigurationError(ValueError):
    """Raised when configuration is invalid."""
    
    def __init__(self, key: str, value: Any, reason: str):
        self.key = key
        self.value = value
        self.reason = reason
        super().__init__(
            f"Invalid configuration for '{key}': {reason} (value: {value})"
        )

# Usage
def load_config(config: dict[str, Any]) -> Config:
    """Load and validate configuration."""
    if "api_token" not in config:
        raise ConfigurationError("api_token", None, "required field missing")
    
    if not isinstance(config["api_token"], str):
        raise ConfigurationError(
            "api_token",
            config["api_token"],
            "must be a string"
        )
    
    return Config(api_token=config["api_token"])
```

**When NOT to Create Custom Exceptions**:

Don't create custom exceptions when standard Python exceptions are sufficient:

```python
# Bad: Unnecessary custom exception
class InvalidInputError(Exception):
    """Raised when input is invalid."""
    pass

def process_value(value: int) -> int:
    if value < 0:
        raise InvalidInputError("Value must be non-negative")
    return value * 2

# Good: Use standard ValueError
def process_value(value: int) -> int:
    if value < 0:
        raise ValueError("Value must be non-negative")
    return value * 2
```

**Custom Exception Location**:

Define custom exceptions in a dedicated module for easy importing:

```python
# src/exceptions.py
"""Custom exception classes for the AI Summarizer Bot."""

class MessageTooLongError(ValueError):
    """Raised when a message exceeds the maximum allowed length."""
    pass

class SummarizationError(Exception):
    """Base exception for summarization-related errors."""
    pass

# Other modules import from exceptions
from src.exceptions import MessageTooLongError, SummarizationError
```

#### When to Use Try-Except vs Letting Exceptions Propagate

Deciding whether to catch exceptions or let them propagate is crucial for clean error handling architecture.

**Use Try-Except When**:

**1. You Can Handle the Error Meaningfully**:

Catch exceptions when you can take corrective action or provide a meaningful alternative:

```python
# Good: Catching exception to provide fallback behavior
def load_user_preferences(user_id: int) -> dict[str, Any]:
    """Load user preferences from database, with defaults as fallback."""
    try:
        return database.get_user_preferences(user_id)
    except DatabaseError as e:
        logging.warning(f"Failed to load preferences for user {user_id}: {e}")
        # Return sensible defaults when database is unavailable
        return {"language": "en", "notifications": True}

# Good: Catching exception to retry with different approach
def fetch_summary(text: str) -> str:
    """Fetch summary using primary model, fallback to secondary."""
    try:
        return primary_model.summarize(text)
    except ModelNotAvailableError:
        logging.info("Primary model unavailable, using secondary model")
        return secondary_model.summarize(text)
```

**2. You Need to Add Context or Transform the Exception**:

Catch exceptions to add context or convert to a more appropriate exception type:

```python
# Good: Adding context to exception
def process_user_message(user_id: int, message: str) -> dict[str, Any]:
    """Process user message and return response."""
    try:
        result = summarizer.summarize(message)
        return {"user_id": user_id, "summary": result}
    except SummarizationError as e:
        # Add user context to the error
        raise SummarizationError(
            f"Failed to process message for user {user_id}: {e}"
        ) from e

# Good: Converting exception type
def parse_config_file(path: str) -> dict[str, Any]:
    """Parse configuration file."""
    try:
        with open(path) as f:
            return json.load(f)
    except FileNotFoundError as e:
        raise ConfigurationError("config_file", path, "file not found") from e
    except json.JSONDecodeError as e:
        raise ConfigurationError("config_file", path, f"invalid JSON: {e}") from e
```

**3. You Need to Clean Up Resources**:

Use try-except-finally or context managers to ensure resource cleanup:

```python
# Good: Ensuring cleanup with finally
def process_file(path: str) -> str:
    """Process file and ensure cleanup."""
    file_handle = None
    try:
        file_handle = open(path)
        return file_handle.read()
    except IOError as e:
        logging.error(f"Failed to read file {path}: {e}")
        raise
    finally:
        if file_handle:
            file_handle.close()

# Better: Use context manager (automatic cleanup)
def process_file(path: str) -> str:
    """Process file with automatic cleanup."""
    try:
        with open(path) as f:
            return f.read()
    except IOError as e:
        logging.error(f"Failed to read file {path}: {e}")
        raise
```

**4. You're at an API Boundary**:

Catch exceptions at API boundaries (HTTP endpoints, CLI commands) to provide user-friendly error responses:

```python
# Good: Catching exceptions at API boundary
@app.route("/api/summarize", methods=["POST"])
def summarize_endpoint():
    """API endpoint for text summarization."""
    try:
        text = request.json.get("text")
        if not text:
            return {"error": "Missing 'text' field"}, 400
        
        summary = summarizer.summarize(text)
        return {"summary": summary}, 200
    
    except MessageTooLongError as e:
        return {"error": str(e)}, 400
    
    except SummarizationError as e:
        logging.error(f"Summarization failed: {e}")
        return {"error": "Failed to generate summary"}, 500
    
    except Exception as e:
        logging.exception("Unexpected error in summarize endpoint")
        return {"error": "Internal server error"}, 500
```

**Let Exceptions Propagate When**:

**1. You Can't Handle the Error**:

Don't catch exceptions if you can't do anything meaningful with them:

```python
# Bad: Catching exception without handling it
def calculate_average(numbers: list[float]) -> float:
    """Calculate average of numbers."""
    try:
        return sum(numbers) / len(numbers)
    except ZeroDivisionError:
        # Can't handle this meaningfully, just re-raising
        raise

# Good: Let it propagate naturally
def calculate_average(numbers: list[float]) -> float:
    """Calculate average of numbers.
    
    Raises:
        ZeroDivisionError: If numbers list is empty.
    """
    return sum(numbers) / len(numbers)
```

**2. The Error Indicates a Programming Bug**:

Let programming errors (TypeError, AttributeError, KeyError from unexpected sources) propagate to surface bugs:

```python
# Bad: Hiding programming errors
def process_data(data: dict[str, Any]) -> str:
    """Process data dictionary."""
    try:
        # If this raises KeyError, it's a bug in our code
        return data["required_field"].upper()
    except KeyError:
        return ""  # Silently hiding a bug!

# Good: Let programming errors propagate
def process_data(data: dict[str, Any]) -> str:
    """Process data dictionary.
    
    Args:
        data: Dictionary with 'required_field' key.
    
    Raises:
        KeyError: If 'required_field' is missing (indicates bug).
    """
    return data["required_field"].upper()
```

**3. The Caller Is Better Positioned to Handle It**:

Let exceptions propagate when the caller has more context to handle them appropriately:

```python
# Good: Let caller handle the exception
def fetch_user_data(user_id: int) -> dict[str, Any]:
    """Fetch user data from database.
    
    Raises:
        DatabaseError: If database query fails.
    """
    # Don't catch DatabaseError here - let caller decide how to handle
    return database.query("SELECT * FROM users WHERE id = ?", user_id)

# Caller handles based on context
def display_user_profile(user_id: int) -> str:
    """Display user profile page."""
    try:
        user_data = fetch_user_data(user_id)
        return render_template("profile.html", user=user_data)
    except DatabaseError:
        # Caller knows to show error page to user
        return render_template("error.html", message="Profile unavailable")
```

**Exception Handling Anti-Patterns to Avoid**:

```python
# Bad: Bare except clause (catches everything, including KeyboardInterrupt)
try:
    process_data()
except:
    pass

# Bad: Catching Exception without re-raising
try:
    critical_operation()
except Exception:
    logging.error("Something went wrong")
    # Error is swallowed, caller doesn't know it failed!

# Bad: Logging and re-raising (creates duplicate log entries)
try:
    process_data()
except ValueError as e:
    logging.error(f"Error: {e}")
    raise  # This will be logged again at a higher level

# Good: Either log OR re-raise, not both
try:
    process_data()
except ValueError as e:
    # Transform and raise with context
    raise ProcessingError(f"Failed to process data: {e}") from e
```

#### Exception Handling Examples

**Example 1: Retry Logic with Exponential Backoff**:

```python
import time
from typing import Callable, TypeVar

T = TypeVar("T")

def retry_with_backoff(
    func: Callable[[], T],
    max_attempts: int = 3,
    initial_delay: float = 1.0,
) -> T:
    """Retry function with exponential backoff.
    
    Args:
        func: Function to retry.
        max_attempts: Maximum number of retry attempts.
        initial_delay: Initial delay in seconds between retries.
    
    Returns:
        The result of the function call.
    
    Raises:
        The last exception if all retries fail.
    """
    delay = initial_delay
    last_exception = None
    
    for attempt in range(max_attempts):
        try:
            return func()
        except (ConnectionError, TimeoutError) as e:
            last_exception = e
            if attempt < max_attempts - 1:
                logging.warning(
                    f"Attempt {attempt + 1} failed: {e}. "
                    f"Retrying in {delay}s..."
                )
                time.sleep(delay)
                delay *= 2  # Exponential backoff
            else:
                logging.error(f"All {max_attempts} attempts failed")
    
    raise last_exception  # type: ignore
```

**Example 2: Context Manager for Resource Management**:

```python
from contextlib import contextmanager
from typing import Generator

@contextmanager
def database_transaction() -> Generator[DatabaseConnection, None, None]:
    """Context manager for database transactions with automatic rollback.
    
    Yields:
        Database connection with active transaction.
    
    Raises:
        DatabaseError: If transaction fails.
    """
    conn = database.get_connection()
    try:
        conn.begin_transaction()
        yield conn
        conn.commit()
        logging.info("Transaction committed successfully")
    except Exception as e:
        conn.rollback()
        logging.error(f"Transaction rolled back due to error: {e}")
        raise DatabaseError(f"Transaction failed: {e}") from e
    finally:
        conn.close()

# Usage
def transfer_funds(from_account: int, to_account: int, amount: float) -> None:
    """Transfer funds between accounts."""
    with database_transaction() as conn:
        conn.execute("UPDATE accounts SET balance = balance - ? WHERE id = ?", 
                     amount, from_account)
        conn.execute("UPDATE accounts SET balance = balance + ? WHERE id = ?", 
                     amount, to_account)
```

### Logging Standards

Structured logging is essential for monitoring application behavior, debugging issues, and auditing operations. This project uses Python's built-in `logging` module with consistent practices across all code.

#### Logging Level Usage

Python's logging module provides five standard logging levels. Each level serves a specific purpose and should be used consistently.

**ERROR - Failures Requiring Attention**:

Use ERROR level for failures that require immediate attention or indicate the application cannot perform a requested operation:

```python
import logging

# Good: ERROR for failures requiring attention
try:
    result = process_payment(user_id, amount)
except PaymentProcessingError as e:
    logging.error(
        f"Payment processing failed for user {user_id}: {e}",
        extra={"user_id": user_id, "amount": amount}
    )
    raise

# Good: ERROR for critical resource failures
try:
    conn = database.connect()
except ConnectionError as e:
    logging.error(f"Failed to connect to database: {e}")
    raise

# Good: ERROR for data integrity issues
if user.balance < 0:
    logging.error(
        f"User {user.id} has negative balance: {user.balance}",
        extra={"user_id": user.id, "balance": user.balance}
    )
```

**When to use ERROR**:

- Failed operations that cannot be recovered
- Critical resource unavailability (database, API, file system)
- Data integrity violations
- Security violations or authentication failures
- Unhandled exceptions at API boundaries

**WARNING - Unexpected But Handled Situations**:

Use WARNING level for unexpected situations that are handled gracefully but may indicate potential issues:

```python
# Good: WARNING for degraded functionality
try:
    cache.set(key, value)
except CacheError as e:
    logging.warning(f"Cache write failed, continuing without cache: {e}")
    # Application continues without cache

# Good: WARNING for deprecated features
def old_api_method(data: dict) -> str:
    """Legacy API method (deprecated)."""
    logging.warning(
        "old_api_method is deprecated, use new_api_method instead",
        extra={"caller": inspect.stack()[1].function}
    )
    return new_api_method(data)

# Good: WARNING for configuration issues with fallbacks
if not config.get("api_key"):
    logging.warning("API key not configured, using limited functionality")
    api_client = LimitedAPIClient()
else:
    api_client = FullAPIClient(config["api_key"])

# Good: WARNING for rate limiting
if request_count > rate_limit:
    logging.warning(
        f"Rate limit exceeded for user {user_id}: {request_count}/{rate_limit}",
        extra={"user_id": user_id, "request_count": request_count}
    )
    return rate_limit_response()
```

**When to use WARNING**:

- Recoverable errors with fallback behavior
- Deprecated feature usage
- Configuration issues with defaults applied
- Resource constraints (rate limiting, quota warnings)
- Unexpected but valid input
- Performance degradation

**INFO - Important State Changes**:

Use INFO level for significant application events and state changes that are part of normal operation:

```python
# Good: INFO for application lifecycle events
logging.info("Application started successfully")
logging.info("Database connection pool initialized with 10 connections")
logging.info("Telegram bot connected and listening for messages")

# Good: INFO for important business operations
logging.info(
    f"User {user_id} subscribed to premium plan",
    extra={"user_id": user_id, "plan": "premium"}
)

logging.info(
    f"Summary generated for document {doc_id} ({len(text)} chars -> {len(summary)} chars)",
    extra={"doc_id": doc_id, "input_length": len(text), "output_length": len(summary)}
)

# Good: INFO for configuration changes
logging.info(
    f"Configuration reloaded from {config_path}",
    extra={"config_path": config_path}
)

# Good: INFO for scheduled task execution
logging.info("Starting daily cleanup task")
logging.info(f"Cleanup completed: removed {count} expired entries")
```

**When to use INFO**:

- Application startup and shutdown
- Service initialization and connection establishment
- Important business operations (user actions, transactions)
- Configuration loading and changes
- Scheduled task execution
- Significant state transitions

**DEBUG - Detailed Diagnostic Information**:

Use DEBUG level for detailed information useful during development and troubleshooting:

```python
# Good: DEBUG for detailed execution flow
def process_message(message: str) -> str:
    """Process incoming message."""
    logging.debug(f"Processing message: {message[:50]}...")
    
    cleaned = clean_text(message)
    logging.debug(f"Cleaned text length: {len(cleaned)}")
    
    tokens = tokenize(cleaned)
    logging.debug(f"Tokenized into {len(tokens)} tokens")
    
    result = generate_summary(tokens)
    logging.debug(f"Generated summary: {result[:50]}...")
    
    return result

# Good: DEBUG for variable values during debugging
def calculate_score(metrics: dict[str, float]) -> float:
    """Calculate weighted score."""
    logging.debug(f"Input metrics: {metrics}")
    
    weights = get_weights()
    logging.debug(f"Weights: {weights}")
    
    score = sum(metrics[k] * weights.get(k, 1.0) for k in metrics)
    logging.debug(f"Calculated score: {score}")
    
    return score

# Good: DEBUG for API request/response details
def fetch_data(url: str) -> dict:
    """Fetch data from API."""
    logging.debug(f"Sending GET request to {url}")
    
    response = requests.get(url)
    logging.debug(f"Response status: {response.status_code}")
    logging.debug(f"Response headers: {response.headers}")
    logging.debug(f"Response body: {response.text[:200]}...")
    
    return response.json()
```

**When to use DEBUG**:

- Detailed execution flow and control flow
- Variable values and intermediate calculations
- API request and response details
- Database query details
- Algorithm step-by-step execution
- Performance timing information

**Logging Level Summary**:

| Level   | Purpose                             | Examples                                                                          |
|---------|-------------------------------------|-----------------------------------------------------------------------------------|
| ERROR   | Failures requiring attention        | Database connection failed, payment processing error, unhandled exception         |
| WARNING | Unexpected but handled situations   | Cache unavailable, deprecated feature used, rate limit approaching                |
| INFO    | Important state changes             | Application started, user subscribed, summary generated                           |
| DEBUG   | Detailed diagnostic information     | Variable values, execution flow, API request details                              |

#### Logging Message Formatting Standards

Consistent log message formatting makes logs easier to read, search, and analyze. Follow these standards for all log messages.

**Message Structure**:

Log messages should follow this structure:

```text
<Action/Event> <Subject> <Context>: <Details>
```

**Examples**:

```python
# Good: Clear structure
logging.info("User 12345 subscribed to premium plan")
logging.error("Failed to connect to database: connection timeout after 30s")
logging.warning("Cache write failed for key 'user:12345': cache server unavailable")

# Bad: Vague or poorly structured
logging.info("Something happened")
logging.error("Error!")
logging.warning("Problem with cache")
```

**Use Structured Logging with Extra Fields**:

Include structured data using the `extra` parameter for better log analysis:

```python
# Good: Structured logging with extra fields
logging.info(
    "Summary generated successfully",
    extra={
        "user_id": user_id,
        "document_id": doc_id,
        "input_length": len(text),
        "output_length": len(summary),
        "processing_time_ms": elapsed_ms,
    }
)

# Good: Error logging with context
logging.error(
    "Payment processing failed",
    extra={
        "user_id": user_id,
        "amount": amount,
        "currency": currency,
        "error_code": error.code,
    },
    exc_info=True  # Include exception traceback
)
```

**Include Relevant Context**:

Always include enough context to understand what happened:

```python
# Bad: Missing context
logging.error("Query failed")

# Good: Includes query details and error
logging.error(
    f"Database query failed: {e}",
    extra={"query": sql, "params": params, "error": str(e)}
)

# Bad: Missing user context
logging.info("Subscription created")

# Good: Includes user and subscription details
logging.info(
    f"User {user_id} subscribed to {plan_name}",
    extra={"user_id": user_id, "plan": plan_name, "duration": duration}
)
```

**Use f-strings for Message Formatting**:

Use f-strings for readable, efficient log message formatting:

```python
# Good: f-string formatting
logging.info(f"Processing message from user {user_id}: {message[:50]}...")
logging.error(f"Failed to load config from {config_path}: {error}")

# Bad: Old-style formatting
logging.info("Processing message from user %s: %s..." % (user_id, message[:50]))
logging.error("Failed to load config from {}: {}".format(config_path, error))
```

**Include Exception Information**:

Use `exc_info=True` to include exception tracebacks in error logs:

```python
# Good: Include exception traceback
try:
    result = process_data(data)
except Exception as e:
    logging.error(
        f"Data processing failed: {e}",
        exc_info=True,  # Includes full traceback
        extra={"data_size": len(data)}
    )
    raise

# Alternative: Use logging.exception() for ERROR level with traceback
try:
    result = process_data(data)
except Exception as e:
    logging.exception(f"Data processing failed: {e}")
    raise
```

**Avoid Logging Sensitive Information**:

Never log sensitive data like passwords, tokens, or personal information:

```python
# Bad: Logging sensitive information
logging.info(f"User logged in with password: {password}")
logging.debug(f"API request with token: {api_token}")

# Good: Redact or omit sensitive information
logging.info(f"User {user_id} logged in successfully")
logging.debug(f"API request with token: {api_token[:8]}...")  # Only first 8 chars

# Good: Use placeholders for sensitive data
logging.info(
    "User authenticated",
    extra={"user_id": user_id, "auth_method": "password"}
)
```

**Performance Considerations**:

Avoid expensive operations in log messages that may not be emitted:

```python
# Bad: Expensive operation always executed
logging.debug(f"Data: {json.dumps(large_object, indent=2)}")

# Good: Use lazy evaluation
if logging.getLogger().isEnabledFor(logging.DEBUG):
    logging.debug(f"Data: {json.dumps(large_object, indent=2)}")

# Better: Let logging handle it with lazy formatting
logging.debug("Data: %s", lambda: json.dumps(large_object, indent=2))
```

**Logger Configuration Example**:

```python
import logging
import sys

# Configure logging at application startup
def configure_logging(level: str = "INFO") -> None:
    """Configure application logging.
    
    Args:
        level: Logging level (DEBUG, INFO, WARNING, ERROR).
    """
    logging.basicConfig(
        level=getattr(logging, level.upper()),
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler("app.log"),
        ]
    )
    
    # Set third-party library log levels
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("requests").setLevel(logging.WARNING)

# Use module-level loggers
logger = logging.getLogger(__name__)

def process_message(message: str) -> str:
    """Process incoming message."""
    logger.info(f"Processing message: {message[:50]}...")
    # Processing logic...
    return result
```

**Logging Best Practices Summary**:

- Use appropriate log levels (ERROR, WARNING, INFO, DEBUG)
- Include structured data with `extra` parameter
- Provide sufficient context in log messages
- Use f-strings for formatting
- Include exception tracebacks with `exc_info=True`
- Never log sensitive information
- Use module-level loggers (`logging.getLogger(__name__)`)
- Configure logging once at application startup
- Avoid expensive operations in log messages

## Type Annotations

This project requires type annotations for all function signatures and class attributes to enable static type checking and improve code maintainability. Type annotations make code more self-documenting, catch type-related bugs early, and improve IDE support for autocompletion and refactoring.

### Type Annotation Requirements

Type annotations are enforced by Ruff's flake8-annotations rules (ANN* rules) configured in `pyproject.toml`. The project uses Python 3.13+ type hint syntax, including modern union syntax (`|` instead of `Union`).

**When Type Annotations Are Required**:

1. **Function Signatures** - All function parameters and return values must be annotated
2. **Class Attributes** - All class-level attributes must be annotated
3. **Instance Attributes** - Instance attributes should be annotated in `__init__` or as class attributes

**When Type Annotations Are Optional**:

- Local variables within functions (type inference usually works well)
- Lambda functions (though consider using regular functions for complex lambdas)
- Private helper functions in test files (though still recommended)

#### Function Signature Examples

**Basic Function with Type Annotations**:

```python
# Good: All parameters and return value are annotated
def calculate_total(price: float, quantity: int, tax_rate: float) -> float:
    """Calculates the total price including tax."""
    subtotal = price * quantity
    return subtotal * (1 + tax_rate)

# Good: Function with no return value
def log_message(message: str, level: str) -> None:
    """Logs a message at the specified level."""
    logging.log(getattr(logging, level.upper()), message)

# Bad: Missing type annotations
def calculate_total(price, quantity, tax_rate):
    """Calculates the total price including tax."""
    subtotal = price * quantity
    return subtotal * (1 + tax_rate)
```

**Function with Default Arguments**:

```python
# Good: Default arguments with type annotations
def fetch_data(
    url: str,
    timeout: int = 30,
    retries: int = 3,
    headers: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Fetches data from URL with retry logic."""
    if headers is None:
        headers = {}
    # Implementation here
    return {"status": "success"}

# Good: Using modern union syntax (Python 3.10+)
def get_user(user_id: int) -> dict[str, Any] | None:
    """Gets user data or None if not found."""
    return database.query(user_id)
```

**Function with Multiple Return Types**:

```python
# Good: Union type for multiple return types
def parse_value(value: str) -> int | float | str:
    """Parses a string value into int, float, or returns as string."""
    try:
        return int(value)
    except ValueError:
        try:
            return float(value)
        except ValueError:
            return value

# Good: Optional return type (value or None)
def find_user(username: str) -> User | None:
    """Finds user by username or returns None."""
    return database.query(User).filter_by(username=username).first()
```

#### Class Attribute Examples

**Class with Type Annotations**:

```python
# Good: All attributes are annotated
class MessageProcessor:
    """Processes incoming messages."""
    
    # Class-level attributes
    max_retries: int = 3
    timeout: int = 30
    
    def __init__(self, bot_token: str, api_url: str) -> None:
        """Initializes the message processor."""
        # Instance attributes annotated in __init__
        self.bot_token: str = bot_token
        self.api_url: str = api_url
        self.retry_count: int = 0
        self.cache: dict[str, Any] = {}
    
    def process(self, message: str) -> dict[str, Any]:
        """Processes a message and returns result."""
        return {"message": message, "status": "processed"}

# Alternative: Annotate instance attributes as class attributes
class MessageProcessor:
    """Processes incoming messages."""
    
    # Class-level constants
    max_retries: int = 3
    timeout: int = 30
    
    # Instance attributes (no default values)
    bot_token: str
    api_url: str
    retry_count: int
    cache: dict[str, Any]
    
    def __init__(self, bot_token: str, api_url: str) -> None:
        """Initializes the message processor."""
        self.bot_token = bot_token
        self.api_url = api_url
        self.retry_count = 0
        self.cache = {}
```

**Dataclass with Type Annotations**:

```python
from dataclasses import dataclass
from datetime import datetime

# Good: Dataclass with full type annotations
@dataclass
class UserMessage:
    """Represents a user message."""
    user_id: int
    message_text: str
    timestamp: datetime
    metadata: dict[str, Any]
    is_processed: bool = False
    retry_count: int = 0
```

### Complex Type Handling

Python's typing module provides powerful tools for expressing complex type relationships. This section covers advanced type annotation patterns used in the project.

#### Union Types

Union types represent values that can be one of several types. Python 3.10+ supports the modern `|` syntax, which is preferred over `typing.Union`.

```python
# Good: Modern union syntax (Python 3.10+)
def process_input(value: int | float | str) -> str:
    """Processes input of multiple types."""
    return str(value)

# Good: Union with None (optional value)
def get_config(key: str) -> str | None:
    """Gets configuration value or None if not found."""
    return os.environ.get(key)

# Old style (avoid): Using typing.Union
from typing import Union

def process_input(value: Union[int, float, str]) -> str:
    """Processes input of multiple types."""
    return str(value)
```

#### Optional Types

Optional types represent values that can be a specific type or `None`. Use `Type | None` instead of `Optional[Type]`.

```python
# Good: Modern optional syntax
def find_user(user_id: int) -> User | None:
    """Finds user by ID or returns None."""
    return database.get(User, user_id)

def parse_date(date_str: str | None) -> datetime | None:
    """Parses date string or returns None."""
    if date_str is None:
        return None
    return datetime.fromisoformat(date_str)

# Old style (avoid): Using typing.Optional
from typing import Optional

def find_user(user_id: int) -> Optional[User]:
    """Finds user by ID or returns None."""
    return database.get(User, user_id)
```

#### Collection Types

Use built-in collection types (`list`, `dict`, `set`, `tuple`) with type parameters instead of importing from `typing`.

```python
# Good: Built-in collection types (Python 3.9+)
def process_items(items: list[str]) -> dict[str, int]:
    """Processes items and returns counts."""
    return {item: len(item) for item in items}

def get_coordinates() -> tuple[float, float]:
    """Returns latitude and longitude coordinates."""
    return (37.7749, -122.4194)

def get_unique_ids(data: list[dict[str, Any]]) -> set[int]:
    """Extracts unique IDs from data."""
    return {item["id"] for item in data}

# Good: Nested collection types
def group_messages(
    messages: list[dict[str, Any]]
) -> dict[int, list[dict[str, Any]]]:
    """Groups messages by user ID."""
    result: dict[int, list[dict[str, Any]]] = {}
    for message in messages:
        user_id = message["user_id"]
        if user_id not in result:
            result[user_id] = []
        result[user_id].append(message)
    return result

# Old style (avoid): Importing from typing
from typing import List, Dict, Set, Tuple

def process_items(items: List[str]) -> Dict[str, int]:
    """Processes items and returns counts."""
    return {item: len(item) for item in items}
```

#### List, Dict, and Tuple Details

**List Types**:

```python
# Homogeneous list (all elements same type)
def get_names() -> list[str]:
    """Returns list of names."""
    return ["Alice", "Bob", "Charlie"]

# List with union type (multiple element types)
def get_mixed_values() -> list[int | str]:
    """Returns list with mixed types."""
    return [1, "two", 3, "four"]

# Empty list with type annotation
def initialize_cache() -> list[dict[str, Any]]:
    """Initializes empty cache."""
    return []
```

**Dict Types**:

```python
# Simple dict with string keys and int values
def count_words(text: str) -> dict[str, int]:
    """Counts word occurrences."""
    return {word: text.count(word) for word in text.split()}

# Dict with complex value types
def get_user_data() -> dict[str, str | int | list[str]]:
    """Returns user data with mixed value types."""
    return {
        "name": "Alice",
        "age": 30,
        "roles": ["admin", "user"],
    }

# Dict with Any for unknown value types
def parse_json(json_str: str) -> dict[str, Any]:
    """Parses JSON string into dict."""
    return json.loads(json_str)
```

**Tuple Types**:

```python
# Fixed-length tuple with specific types
def get_user_info() -> tuple[str, int, bool]:
    """Returns username, age, and active status."""
    return ("alice", 30, True)

# Variable-length tuple (all elements same type)
def get_numbers() -> tuple[int, ...]:
    """Returns variable number of integers."""
    return (1, 2, 3, 4, 5)

# Tuple for multiple return values
def divide_with_remainder(a: int, b: int) -> tuple[int, int]:
    """Returns quotient and remainder."""
    return (a // b, a % b)
```

#### Forward References

Forward references allow you to reference types that are defined later in the file or create self-referential types. Use string literals for forward references.

```python
# Good: Forward reference using string literal
class TreeNode:
    """Represents a node in a tree structure."""
    
    def __init__(self, value: int, parent: "TreeNode | None" = None) -> None:
        """Initializes tree node."""
        self.value: int = value
        self.parent: TreeNode | None = parent
        self.children: list["TreeNode"] = []
    
    def add_child(self, child: "TreeNode") -> None:
        """Adds a child node."""
        self.children.append(child)
        child.parent = self

# Good: Self-referential type
class LinkedListNode:
    """Represents a node in a linked list."""
    
    def __init__(self, value: Any, next_node: "LinkedListNode | None" = None) -> None:
        """Initializes linked list node."""
        self.value: Any = value
        self.next: LinkedListNode | None = next_node
```

**Using `from __future__ import annotations`**:

Python 3.7+ supports postponed evaluation of annotations, which eliminates the need for string literals in most cases:

```python
from __future__ import annotations

# Good: No string literals needed with future annotations
class TreeNode:
    """Represents a node in a tree structure."""
    
    def __init__(self, value: int, parent: TreeNode | None = None) -> None:
        """Initializes tree node."""
        self.value: int = value
        self.parent: TreeNode | None = parent
        self.children: list[TreeNode] = []
    
    def add_child(self, child: TreeNode) -> None:
        """Adds a child node."""
        self.children.append(child)
        child.parent = self
```

**Note**: The project uses Ruff's flake8-future-annotations (FA) rules, which encourage using `from __future__ import annotations` for cleaner code.

#### TYPE_CHECKING Imports

The `TYPE_CHECKING` constant from the `typing` module is `False` at runtime but `True` during static type checking. Use it to avoid circular import issues and reduce runtime overhead.

**When to Use TYPE_CHECKING**:

1. **Circular Imports** - When two modules need to reference each other's types
2. **Expensive Imports** - When importing types from large modules only needed for type checking
3. **Runtime Performance** - When imports are only needed for type annotations, not runtime logic

**TYPE_CHECKING Examples**:

```python
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    # These imports only happen during type checking, not at runtime
    from src.database import DatabaseConnection
    from src.processors.message_processor import MessageProcessor
    from src.models import User, Message

# Runtime imports
import logging
from datetime import datetime

class BotHandler:
    """Handles bot operations."""
    
    def __init__(
        self,
        db: DatabaseConnection,  # Type available due to TYPE_CHECKING import
        processor: MessageProcessor,
    ) -> None:
        """Initializes bot handler."""
        self.db = db
        self.processor = processor
    
    def get_user(self, user_id: int) -> User | None:
        """Gets user by ID."""
        return self.db.query(User).filter_by(id=user_id).first()
    
    def process_message(self, message: Message) -> dict[str, Any]:
        """Processes incoming message."""
        return self.processor.process(message)
```

**Avoiding Circular Imports**:

```python
# File: src/models/user.py
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.models.message import Message  # Avoid circular import

class User:
    """Represents a user."""
    
    def __init__(self, user_id: int, username: str) -> None:
        """Initializes user."""
        self.user_id = user_id
        self.username = username
        self.messages: list[Message] = []  # Type hint works due to TYPE_CHECKING
    
    def add_message(self, message: Message) -> None:
        """Adds a message to user's message list."""
        self.messages.append(message)

# File: src/models/message.py
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.models.user import User  # Avoid circular import

class Message:
    """Represents a message."""
    
    def __init__(self, text: str, author: User) -> None:
        """Initializes message."""
        self.text = text
        self.author: User = author  # Type hint works due to TYPE_CHECKING
```

**Best Practices**:

1. Always use `from __future__ import annotations` at the top of files with TYPE_CHECKING imports
2. Import only types (classes, type aliases) in TYPE_CHECKING blocks, never runtime dependencies
3. Keep TYPE_CHECKING imports organized and alphabetically sorted
4. Use TYPE_CHECKING for expensive imports that are only needed for type hints
5. Document why TYPE_CHECKING is used if the reason isn't obvious (e.g., "Avoid circular import")

**Configuration**:

TYPE_CHECKING usage is encouraged by Ruff's flake8-type-checking (TCH) rules configured in `pyproject.toml`. These rules help identify imports that should be moved into TYPE_CHECKING blocks.

For more on Ruff configuration, see [Code Quality and Linting](#code-quality-and-linting).

## Configuration Management

This project uses environment variables for runtime configuration and various file formats for static configuration. Proper configuration management ensures security, portability, and maintainability across different environments (development, staging, production).

### Environment Variables

Environment variables are used for runtime configuration, especially for sensitive information like API keys, database credentials, and environment-specific settings. The project uses a `.env` file for local development and environment variables in production.

#### .env File Structure

The `.env` file contains key-value pairs for environment-specific configuration. This file should never be committed to version control (it's listed in `.gitignore`).

**Required Variables**:

The following environment variables are required for the application to function:

```bash
# Telegram Bot Configuration
TG_API_TOKEN="your_telegram_bot_token_here"

# AI/ML Service API Keys
GEMINI_API_KEY="your_gemini_api_key_here"
REPLICATE_API_TOKEN="your_replicate_api_token_here"

# Database Configuration
DSN="postgresql+psycopg2://user:password@host:port/database"
REDIS_URL="rediss://default:password@host:port"

# Monitoring and Logging
SENTRY_DSN="https://your_sentry_dsn_here"
LOG_LEVEL="DEBUG"  # Options: DEBUG, INFO, WARNING, ERROR, CRITICAL

# Modal.com Configuration (for serverless deployment)
MODAL_TOKEN_ID="your_modal_token_id"
MODAL_TOKEN_SECRET="your_modal_token_secret"
```

**Optional Variables**:

These variables have defaults or are only needed in specific environments:

```bash
# Proxy Configuration (optional)
PROXY=""  # HTTP/HTTPS proxy URL if needed
WEB_SCRAPE_PROXY=""  # Proxy for web scraping operations

# Environment Indicator (optional, defaults to development)
ENV="PROD"  # Set to "PROD" for production environment
```

**Example .env File**:

```bash
# Development environment configuration
TG_API_TOKEN="1234567890:ABCdefGHIjklMNOpqrsTUVwxyz"
GEMINI_API_KEY="AIzaSyABC123def456GHI789jkl"
REPLICATE_API_TOKEN="r8_ABC123def456"
DSN="postgresql+psycopg2://postgres:password@localhost:5432/summarizer_dev"
REDIS_URL="redis://localhost:6379"
SENTRY_DSN="https://abc123@o123456.ingest.sentry.io/789012"
LOG_LEVEL="DEBUG"
MODAL_TOKEN_ID="ak-ABC123"
MODAL_TOKEN_SECRET="as-DEF456"
PROXY=""
WEB_SCRAPE_PROXY=""
```

#### Loading Environment Variables

Environment variables are loaded using the `python-dotenv` package in development and directly from the system environment in production:

```python
import os
from dotenv import load_dotenv

# Load .env file only in non-production environments
if os.environ.get("ENV") != "PROD":
    load_dotenv()

# Access environment variables
api_token = os.environ["TG_API_TOKEN"]  # Required variable
log_level = os.environ.get("LOG_LEVEL", "ERROR")  # Optional with default
```

**Best Practices**:

- Use `os.environ["VAR"]` for required variables (raises KeyError if missing)
- Use `os.environ.get("VAR", "default")` for optional variables with defaults
- Load environment variables at the top of your configuration module
- Never use `load_dotenv()` in production (set variables in the deployment environment)

#### Handling Sensitive Information

Sensitive information like API keys, tokens, passwords, and database credentials must be handled securely:

**Security Rules**:

1. **Never commit sensitive data to version control**
   - Add `.env` to `.gitignore`
   - Use `.env.example` with placeholder values for documentation
   - Review commits to ensure no secrets are included

2. **Use environment variables for all secrets**
   - API keys: `GEMINI_API_KEY`, `REPLICATE_API_TOKEN`
   - Authentication tokens: `TG_API_TOKEN`, `MODAL_TOKEN_SECRET`
   - Database credentials: Include in `DSN` connection string
   - Service credentials: `SENTRY_DSN`, `REDIS_URL`

3. **Rotate credentials regularly**
   - Change API keys and tokens periodically
   - Update credentials immediately if compromised
   - Use different credentials for each environment

4. **Use secure connection strings**
   - Always use SSL/TLS for database connections (`postgresql+psycopg2://` with SSL)
   - Use `rediss://` (Redis with SSL) instead of `redis://` in production
   - Include authentication in connection strings

**Example .env.example File**:

Create a `.env.example` file with placeholder values for documentation:

```bash
# Telegram Bot Configuration
TG_API_TOKEN="your_telegram_bot_token_here"

# AI/ML Service API Keys
GEMINI_API_KEY="your_gemini_api_key_here"
REPLICATE_API_TOKEN="your_replicate_api_token_here"

# Database Configuration
DSN="postgresql+psycopg2://user:password@host:port/database"
REDIS_URL="rediss://default:password@host:port"

# Monitoring and Logging
SENTRY_DSN="https://your_sentry_dsn_here"
LOG_LEVEL="DEBUG"

# Modal.com Configuration
MODAL_TOKEN_ID="your_modal_token_id"
MODAL_TOKEN_SECRET="your_modal_token_secret"

# Proxy Configuration (optional)
PROXY=""
WEB_SCRAPE_PROXY=""
```

**Accessing Secrets in Code**:

```python
# Good: Load secrets from environment variables
import os

api_key = os.environ["GEMINI_API_KEY"]
db_password = os.environ["DSN"]

# Bad: Hardcoded secrets (NEVER do this!)
api_key = "AIzaSyABC123def456GHI789jkl"  # NEVER!
db_password = "my_secret_password"  # NEVER!
```

#### Default Values and Validation

Provide sensible defaults for optional configuration and validate required variables at startup:

**Default Values**:

```python
import os

# Optional variables with defaults
LOG_LEVEL = os.environ.get("LOG_LEVEL", "ERROR").upper()
PROXY = os.environ.get("PROXY", "")
ENV = os.environ.get("ENV", "DEV")

# Required variables (no default)
TG_API_TOKEN = os.environ["TG_API_TOKEN"]  # Raises KeyError if missing
GEMINI_API_KEY = os.environ["GEMINI_API_KEY"]
```

**Configuration Validation**:

Validate configuration at application startup to fail fast with clear error messages:

```python
import os
import sys
import logging

def validate_config() -> None:
    """Validates required configuration variables are set.
    
    Raises:
        SystemExit: If required configuration is missing or invalid.
    """
    required_vars = [
        "TG_API_TOKEN",
        "GEMINI_API_KEY",
        "REPLICATE_API_TOKEN",
        "DSN",
        "REDIS_URL",
        "SENTRY_DSN",
    ]
    
    missing_vars = [var for var in required_vars if not os.environ.get(var)]
    
    if missing_vars:
        logging.error(f"Missing required environment variables: {', '.join(missing_vars)}")
        sys.exit(1)
    
    # Validate LOG_LEVEL is valid
    log_level = os.environ.get("LOG_LEVEL", "ERROR").upper()
    valid_levels = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
    if log_level not in valid_levels:
        logging.warning(f"Invalid LOG_LEVEL '{log_level}', using 'ERROR'")

# Call validation at startup
validate_config()
```

**Type Conversion and Validation**:

```python
import os

# Convert string to integer with validation
def get_int_env(var_name: str, default: int) -> int:
    """Gets integer environment variable with validation."""
    value = os.environ.get(var_name)
    if value is None:
        return default
    try:
        return int(value)
    except ValueError:
        logging.warning(f"Invalid integer for {var_name}: {value}, using default {default}")
        return default

# Convert string to boolean
def get_bool_env(var_name: str, default: bool = False) -> bool:
    """Gets boolean environment variable."""
    value = os.environ.get(var_name, "").lower()
    if value in ("true", "1", "yes", "on"):
        return True
    if value in ("false", "0", "no", "off"):
        return False
    return default

# Usage
MAX_RETRIES = get_int_env("MAX_RETRIES", 3)
DEBUG_MODE = get_bool_env("DEBUG_MODE", False)
```

### Configuration Files

Configuration files are used for static configuration that doesn't change between environments or doesn't contain sensitive information. The project uses different file formats depending on the use case.

#### Configuration File Formats

**TOML for Python Projects**:

Use TOML (Tom's Obvious, Minimal Language) for Python project configuration. TOML is the standard format for Python projects (PEP 518) and is used in `pyproject.toml`.

**Example - pyproject.toml**:

```toml
[project]
name = "ai-summarizer-telegram-bot"
version = "0.8.6"
description = "Bot to summarize video from youtube.com and podcasts"
requires-python = ">=3.13"
dependencies = [
    "beautifulsoup4>=4.13.4",
    "google-genai>=1.25.0",
    "psycopg2-binary>=2.9.10",
]

[tool.ruff]
line-length = 88
indent-width = 4
target-version = "py313"

[tool.ruff.lint]
select = ["E", "F", "B", "I", "W"]
ignore = ["S603", "S607", "D100", "D401"]
```

**When to use TOML**:

- Python project metadata (`pyproject.toml`)
- Tool configuration (Ruff, Black, pytest)
- Package dependencies and build configuration
- Static application settings that don't change between environments

**JSON for Tool Configuration**:

Use JSON for tool configuration files, especially when the tool expects JSON or when you need strict structure validation.

**Example - .markdownlint-cli2.jsonc**:

```json
{
  "config": {
    "default": true,
    "MD013": false,
    "MD033": {
      "allowed_elements": ["br", "details", "summary"]
    },
    "MD041": false
  },
  "globs": ["**/*.md"],
  "ignores": ["node_modules", ".venv"]
}
```

**When to use JSON**:

- Tool configuration files (markdownlint, ESLint, TSConfig)
- API response/request schemas
- Data interchange between systems
- Configuration that needs to be parsed by multiple languages

**YAML When Needed**:

Use YAML sparingly, only when required by specific tools or when human readability of complex nested structures is critical.

**Example - Docker Compose (compose.yaml)**:

```yaml
services:
  bot:
    build: .
    environment:
      - TG_API_TOKEN=${TG_API_TOKEN}
      - GEMINI_API_KEY=${GEMINI_API_KEY}
    volumes:
      - ./src:/app/src
    depends_on:
      - postgres
      - redis

  postgres:
    image: postgres:16
    environment:
      POSTGRES_PASSWORD: ${DB_PASSWORD}
    volumes:
      - postgres_data:/var/lib/postgresql/data

  redis:
    image: redis:7-alpine
    volumes:
      - redis_data:/data

volumes:
  postgres_data:
  redis_data:
```

**When to use YAML**:

- Docker Compose configuration
- CI/CD pipeline configuration (GitHub Actions, GitLab CI)
- Kubernetes manifests
- Configuration with complex nested structures

**INI for Legacy Tools**:

Use INI format only when required by legacy tools like Alembic.

**Example - alembic.ini**:

```ini
[alembic]
script_location = migrations
prepend_sys_path = .
version_path_separator = os

[loggers]
keys = root,sqlalchemy,alembic

[handlers]
keys = console

[formatters]
keys = generic
```

**When to use INI**:

- Alembic database migrations
- Legacy tools that require INI format
- Simple key-value configuration without nesting

#### Configuration File Locations

Configuration files should be placed in standard locations based on their purpose:

**Project Root** (for project-wide configuration):

- `pyproject.toml` - Python project metadata and tool configuration
- `.env` - Environment variables (never commit!)
- `.env.example` - Example environment variables (commit this)
- `.gitignore` - Git ignore patterns
- `.markdownlint-cli2.jsonc` - Markdown linting configuration
- `compose.yaml` - Docker Compose configuration
- `alembic.ini` - Database migration configuration

**Configuration Directory** (for complex applications):

For larger projects, create a `config/` directory:

```text
config/
├── __init__.py
├── base.py          # Base configuration
├── development.py   # Development-specific config
├── production.py    # Production-specific config
└── settings.toml    # Static application settings
```

**Example - config/base.py**:

```python
"""Base configuration shared across all environments."""
import os

class BaseConfig:
    """Base configuration class."""
    
    # Application settings
    APP_NAME = "AI Summarizer Bot"
    APP_VERSION = "0.8.6"
    
    # API settings
    API_TIMEOUT = 30
    MAX_RETRIES = 3
    
    # Feature flags
    ENABLE_CACHING = True
    ENABLE_RATE_LIMITING = True
    
    @classmethod
    def from_env(cls) -> "BaseConfig":
        """Creates configuration from environment variables."""
        config = cls()
        config.LOG_LEVEL = os.environ.get("LOG_LEVEL", "ERROR")
        return config
```

**Tool-Specific Configuration**:

Some tools expect configuration in specific locations:

- `.github/workflows/` - GitHub Actions workflows
- `.vscode/` - VS Code workspace settings
- `tests/` - Test configuration files
- `docs/` - Documentation configuration

**Best Practices**:

1. Keep configuration files in the project root unless they're tool-specific
2. Use descriptive names (`.markdownlint-cli2.jsonc` not `config.json`)
3. Document configuration options in comments or README
4. Separate environment-specific config from static config
5. Use version control for configuration files (except `.env`)

#### Configuration Examples

**Example 1: Loading TOML Configuration**:

```python
import tomllib
from pathlib import Path

def load_toml_config(config_path: str = "config/settings.toml") -> dict:
    """Loads configuration from TOML file.
    
    Args:
        config_path: Path to TOML configuration file.
    
    Returns:
        Dictionary containing configuration values.
    
    Raises:
        FileNotFoundError: If configuration file doesn't exist.
        tomllib.TOMLDecodeError: If TOML file is invalid.
    """
    config_file = Path(config_path)
    if not config_file.exists():
        raise FileNotFoundError(f"Configuration file not found: {config_path}")
    
    with config_file.open("rb") as f:
        return tomllib.load(f)

# Usage
config = load_toml_config()
max_retries = config["api"]["max_retries"]
timeout = config["api"]["timeout"]
```

**Example 2: Loading JSON Configuration**:

```python
import json
from pathlib import Path

def load_json_config(config_path: str) -> dict:
    """Loads configuration from JSON file.
    
    Args:
        config_path: Path to JSON configuration file.
    
    Returns:
        Dictionary containing configuration values.
    
    Raises:
        FileNotFoundError: If configuration file doesn't exist.
        json.JSONDecodeError: If JSON file is invalid.
    """
    config_file = Path(config_path)
    if not config_file.exists():
        raise FileNotFoundError(f"Configuration file not found: {config_path}")
    
    with config_file.open("r") as f:
        return json.load(f)

# Usage
config = load_json_config(".markdownlint-cli2.jsonc")
rules = config["config"]
```

**Example 3: Combining Environment Variables and Config Files**:

```python
import os
import tomllib
from pathlib import Path
from dataclasses import dataclass

@dataclass
class AppConfig:
    """Application configuration combining env vars and config files."""
    
    # From environment variables
    api_token: str
    database_url: str
    log_level: str
    
    # From config file
    max_retries: int
    timeout: int
    cache_ttl: int
    
    @classmethod
    def load(cls, config_file: str = "config/settings.toml") -> "AppConfig":
        """Loads configuration from environment and config file.
        
        Args:
            config_file: Path to TOML configuration file.
        
        Returns:
            AppConfig instance with loaded configuration.
        
        Raises:
            KeyError: If required environment variable is missing.
            FileNotFoundError: If configuration file doesn't exist.
        """
        # Load from environment variables
        api_token = os.environ["TG_API_TOKEN"]
        database_url = os.environ["DSN"]
        log_level = os.environ.get("LOG_LEVEL", "ERROR")
        
        # Load from config file
        config_path = Path(config_file)
        if config_path.exists():
            with config_path.open("rb") as f:
                file_config = tomllib.load(f)
            max_retries = file_config["api"]["max_retries"]
            timeout = file_config["api"]["timeout"]
            cache_ttl = file_config["cache"]["ttl"]
        else:
            # Use defaults if config file doesn't exist
            max_retries = 3
            timeout = 30
            cache_ttl = 3600
        
        return cls(
            api_token=api_token,
            database_url=database_url,
            log_level=log_level,
            max_retries=max_retries,
            timeout=timeout,
            cache_ttl=cache_ttl,
        )

# Usage
config = AppConfig.load()
print(f"Log level: {config.log_level}")
print(f"Max retries: {config.max_retries}")
```

**Example 4: Environment-Specific Configuration**:

```python
import os
from typing import Type

class BaseConfig:
    """Base configuration."""
    DEBUG = False
    TESTING = False
    MAX_RETRIES = 3

class DevelopmentConfig(BaseConfig):
    """Development configuration."""
    DEBUG = True
    LOG_LEVEL = "DEBUG"
    DATABASE_URL = "postgresql://localhost/dev_db"

class ProductionConfig(BaseConfig):
    """Production configuration."""
    DEBUG = False
    LOG_LEVEL = "ERROR"
    DATABASE_URL = os.environ["DSN"]

class TestingConfig(BaseConfig):
    """Testing configuration."""
    TESTING = True
    LOG_LEVEL = "DEBUG"
    DATABASE_URL = "postgresql://localhost/test_db"

def get_config() -> Type[BaseConfig]:
    """Gets configuration based on environment.
    
    Returns:
        Configuration class for current environment.
    """
    env = os.environ.get("ENV", "DEV").upper()
    
    config_map = {
        "DEV": DevelopmentConfig,
        "PROD": ProductionConfig,
        "TEST": TestingConfig,
    }
    
    return config_map.get(env, DevelopmentConfig)

# Usage
Config = get_config()
print(f"Debug mode: {Config.DEBUG}")
print(f"Log level: {Config.LOG_LEVEL}")
```

**Configuration Best Practices Summary**:

1. Use environment variables for secrets and environment-specific settings
2. Use TOML for Python project configuration and tool settings
3. Use JSON for tool configuration that expects JSON format
4. Use YAML only when required by specific tools (Docker, CI/CD)
5. Keep configuration files in standard locations (project root or config/)
6. Validate configuration at application startup
7. Provide sensible defaults for optional configuration
8. Document all configuration options
9. Never commit sensitive information to version control
10. Use type hints and dataclasses for configuration objects

## Testing Standards

This project maintains high code quality through comprehensive testing practices. Tests ensure that code works correctly, catches regressions early, and provides documentation of expected behavior. This section defines naming conventions, test types, coverage expectations, and pre-commit quality checks.

### Test Naming Conventions

Consistent test naming makes it easy to identify test files, understand what functionality is being tested, and locate tests for specific features.

#### Test File Naming

Test files should follow one of these two naming patterns:

##### Pattern 1: test_*.py (Recommended)

Place the `test_` prefix at the beginning of the filename:

```text
test_message_processor.py
test_database_connection.py
test_summary_generator.py
test_api_client.py
```

##### Pattern 2: *_test.py (Alternative)

Place the `_test` suffix at the end of the filename:

```text
message_processor_test.py
database_connection_test.py
summary_generator_test.py
api_client_test.py
```

**Recommendation**: Use the `test_*.py` pattern (Pattern 1) for consistency with pytest conventions and better alphabetical grouping of test files.

**Test File Location**:

- Place test files in a `tests/` directory at the project root, or
- Co-locate test files with source files in the same directory (for smaller projects)

**Examples**:

```text
# Option 1: Separate tests directory
project/
├── src/
│   ├── processors/
│   │   └── message_processor.py
│   └── database/
│       └── connection.py
└── tests/
    ├── test_message_processor.py
    └── test_database_connection.py

# Option 2: Co-located tests
project/
└── src/
    ├── processors/
    │   ├── message_processor.py
    │   └── test_message_processor.py
    └── database/
        ├── connection.py
        └── test_database_connection.py
```

#### Test Function Naming

Test function names should follow the pattern: `test_<functionality>_<scenario>`

This pattern makes it immediately clear:

- What functionality is being tested
- What specific scenario or condition is being verified

**Format**: `test_<functionality>_<scenario>`

**Components**:

- `test_` - Required prefix for pytest to discover the test
- `<functionality>` - The function, method, or feature being tested
- `<scenario>` - The specific condition, input, or expected behavior

**Examples**:

```python
# Testing a message processing function
def test_process_message_with_valid_input():
    """Test that process_message handles valid input correctly."""
    result = process_message("Hello, world!")
    assert result == "hello, world!"

def test_process_message_with_empty_string():
    """Test that process_message handles empty strings."""
    result = process_message("")
    assert result == ""

def test_process_message_with_special_characters():
    """Test that process_message preserves special characters."""
    result = process_message("Hello! @#$%")
    assert result == "hello! @#$%"

# Testing a class method
def test_summary_generator_generate_with_short_text():
    """Test that SummaryGenerator handles short text correctly."""
    generator = SummaryGenerator()
    summary = generator.generate("Short text")
    assert len(summary) <= len("Short text")

def test_summary_generator_generate_with_long_text():
    """Test that SummaryGenerator truncates long text."""
    generator = SummaryGenerator()
    long_text = "A" * 1000
    summary = generator.generate(long_text)
    assert len(summary) < len(long_text)

def test_summary_generator_generate_raises_on_none():
    """Test that SummaryGenerator raises TypeError for None input."""
    generator = SummaryGenerator()
    with pytest.raises(TypeError):
        generator.generate(None)

# Testing error conditions
def test_fetch_user_data_raises_on_invalid_user_id():
    """Test that fetch_user_data raises ValueError for invalid user ID."""
    with pytest.raises(ValueError):
        fetch_user_data(user_id=-1, api_token="valid_token")

def test_fetch_user_data_raises_on_missing_token():
    """Test that fetch_user_data raises ValueError for missing token."""
    with pytest.raises(ValueError):
        fetch_user_data(user_id=123, api_token="")
```

**Naming Best Practices**:

1. Use descriptive scenario names that explain the test condition
2. Keep function names readable (use underscores to separate words)
3. Be specific about what's being tested and what's expected
4. Use consistent terminology across related tests
5. Avoid abbreviations unless they're widely understood

**Common Scenario Patterns**:

- `_with_valid_input` / `_with_invalid_input`
- `_with_empty_string` / `_with_none` / `_with_missing_data`
- `_returns_expected_value` / `_returns_none` / `_returns_empty_list`
- `_raises_value_error` / `_raises_type_error`
- `_when_user_exists` / `_when_user_not_found`
- `_on_success` / `_on_failure`

### Test Types and Coverage

Different types of tests serve different purposes. Understanding when to write unit tests versus integration tests helps maintain a balanced test suite that catches bugs efficiently.

#### Unit Tests

**Purpose**: Test individual functions, methods, or classes in isolation.

**Characteristics**:

- Fast execution (milliseconds per test)
- Test a single unit of code (one function or method)
- Mock or stub external dependencies (databases, APIs, file systems)
- Focus on logic and edge cases
- Should not require external resources

**When to Write Unit Tests**:

- For pure functions that transform inputs to outputs
- For business logic and algorithms
- For data validation and parsing functions
- For utility functions and helpers
- For class methods with clear inputs and outputs

**Unit Test Example**:

```python
import pytest
from src.processors.message_processor import MessageProcessor

def test_process_message_strips_whitespace():
    """Test that process_message removes leading/trailing whitespace."""
    processor = MessageProcessor()
    result = processor.process("  Hello, world!  ")
    assert result == "Hello, world!"

def test_process_message_converts_to_lowercase():
    """Test that process_message converts text to lowercase."""
    processor = MessageProcessor()
    result = processor.process("HELLO, WORLD!")
    assert result == "hello, world!"

def test_process_message_handles_empty_string():
    """Test that process_message handles empty strings correctly."""
    processor = MessageProcessor()
    result = processor.process("")
    assert result == ""

def test_process_message_handles_none():
    """Test that process_message raises TypeError for None input."""
    processor = MessageProcessor()
    with pytest.raises(TypeError):
        processor.process(None)

def test_calculate_summary_length_with_short_text():
    """Test summary length calculation for short text."""
    from src.utils.helpers import calculate_summary_length
    result = calculate_summary_length("Short text", max_length=100)
    assert result == 1  # len("Short text") // 10 = 1

def test_calculate_summary_length_respects_max_length():
    """Test that summary length never exceeds max_length."""
    from src.utils.helpers import calculate_summary_length
    long_text = "A" * 10000
    result = calculate_summary_length(long_text, max_length=200)
    assert result == 200
```

#### Integration Tests

**Purpose**: Test how multiple components work together.

**Characteristics**:

- Slower execution (seconds per test)
- Test interactions between multiple units
- May use real external resources (test databases, file systems)
- Focus on component integration and data flow
- Verify that components work together correctly

**When to Write Integration Tests**:

- For database operations (queries, transactions, migrations)
- For API endpoints (request/response handling)
- For file I/O operations
- For external service integrations (third-party APIs)
- For workflows that span multiple components

**Integration Test Example**:

```python
import pytest
from src.database.connection import DatabaseConnection
from src.models.user import User

@pytest.fixture
def test_db():
    """Provide a test database connection."""
    db = DatabaseConnection(database_url="sqlite:///:memory:")
    db.create_tables()
    yield db
    db.close()

def test_user_creation_and_retrieval(test_db):
    """Test creating and retrieving a user from the database."""
    # Create a user
    user = User(name="Alice", email="alice@example.com")
    test_db.save(user)
    
    # Retrieve the user
    retrieved_user = test_db.get_user_by_email("alice@example.com")
    
    # Verify the user data
    assert retrieved_user is not None
    assert retrieved_user.name == "Alice"
    assert retrieved_user.email == "alice@example.com"

def test_user_update(test_db):
    """Test updating a user in the database."""
    # Create a user
    user = User(name="Bob", email="bob@example.com")
    test_db.save(user)
    
    # Update the user
    user.name = "Robert"
    test_db.save(user)
    
    # Verify the update
    retrieved_user = test_db.get_user_by_email("bob@example.com")
    assert retrieved_user.name == "Robert"

def test_api_endpoint_returns_user_data(test_client):
    """Test that the /users endpoint returns user data."""
    # Make a request to the API
    response = test_client.get("/users/123")
    
    # Verify the response
    assert response.status_code == 200
    data = response.json()
    assert "id" in data
    assert "name" in data
    assert data["id"] == 123
```

#### Code Coverage Expectations

**Coverage Goals**:

- Aim for 80%+ code coverage for core business logic
- Aim for 90%+ coverage for critical paths (authentication, data processing, API endpoints)
- 100% coverage is not always necessary or practical

**What to Prioritize**:

1. Core business logic and algorithms
2. Error handling and edge cases
3. Public APIs and interfaces
4. Data validation and parsing
5. Security-critical code

**What Not to Prioritize**:

1. Simple getters and setters
2. Configuration and constants
3. Third-party library wrappers (test your usage, not the library)
4. Trivial utility functions

**Measuring Coverage**:

Use `pytest-cov` to measure code coverage:

```bash
# Run tests with coverage report
pytest --cov=src --cov-report=html

# Run tests with coverage report in terminal
pytest --cov=src --cov-report=term-missing

# Fail if coverage is below threshold
pytest --cov=src --cov-fail-under=80
```

**Coverage Report Example**:

```text
Name                                Stmts   Miss  Cover   Missing
-----------------------------------------------------------------
src/__init__.py                         0      0   100%
src/processors/message_processor.py    45      3    93%   78-80
src/database/connection.py             67      8    88%   45, 89-95
src/utils/helpers.py                   23      0   100%
-----------------------------------------------------------------
TOTAL                                 135     11    92%
```

**Best Practices**:

1. Write tests for new code before merging
2. Don't chase 100% coverage at the expense of test quality
3. Focus on meaningful tests that catch real bugs
4. Use coverage reports to identify untested code paths
5. Review coverage trends over time to ensure quality doesn't degrade

### Pre-Commit Quality Checks

Before committing code, run a series of quality checks to ensure code meets project standards. These checks catch issues early and maintain codebase quality.

#### Running Ruff Checks

**Check for Linting Violations**:

Run `ruff check` to identify code quality issues:

```bash
# Check all files
ruff check

# Check specific files or directories
ruff check src/
ruff check src/processors/message_processor.py

# Auto-fix violations where possible
ruff check --fix

# Check specific rule categories
ruff check --select F,E  # Only Pyflakes and pycodestyle errors
```

**Example Output**:

```text
src/processors/message_processor.py:15:1: F401 [*] `logging` imported but unused
src/processors/message_processor.py:23:5: E501 Line too long (95 > 88 characters)
src/utils/helpers.py:8:1: D103 Missing docstring in public function
Found 3 errors.
[*] 1 fixable with the `--fix` option.
```

**Fix Issues**:

```bash
# Automatically fix issues where possible
ruff check --fix

# Review remaining issues and fix manually
ruff check
```

#### Running Ruff Format

**Format Code Automatically**:

Run `ruff format` to automatically format code according to project standards:

```bash
# Format all files
ruff format

# Format specific files
ruff format src/processors/message_processor.py

# Check formatting without making changes (dry run)
ruff format --check

# Show diff of what would change
ruff format --diff
```

**Example Output**:

```text
2 files reformatted, 8 files left unchanged
```

**What Ruff Format Does**:

- Enforces line length (88 characters)
- Fixes indentation (4 spaces)
- Normalizes quote style (double quotes)
- Adds/removes blank lines for consistency
- Formats imports and function signatures

#### Complete Pre-Commit Checklist

Run these checks before every commit:

**1. Format Code**:

```bash
ruff format
```

**2. Fix Auto-Fixable Linting Issues**:

```bash
ruff check --fix
```

**3. Check for Remaining Linting Issues**:

```bash
ruff check
```

**4. Run Tests**:

```bash
# Run all tests
pytest

# Run tests with coverage
pytest --cov=src --cov-report=term-missing

# Run specific test file
pytest tests/test_message_processor.py
```

**5. Check Type Annotations** (if using mypy):

```bash
mypy src/
```

**6. Review Changes**:

```bash
git diff
```

**7. Stage and Commit**:

```bash
git add .
git commit -m "feat: add message processing functionality"
```

#### Automated Pre-Commit Hooks

Consider using `pre-commit` hooks to automate quality checks:

**Install pre-commit**:

```bash
pip install pre-commit
```

**Create .pre-commit-config.yaml**:

```yaml
repos:
  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.1.6
    hooks:
      - id: ruff
        args: [--fix]
      - id: ruff-format

  - repo: https://github.com/pre-commit/pre-commit-hooks
    rev: v4.5.0
    hooks:
      - id: trailing-whitespace
      - id: end-of-file-fixer
      - id: check-yaml
      - id: check-added-large-files
```

**Install hooks**:

```bash
pre-commit install
```

**Run hooks manually**:

```bash
pre-commit run --all-files
```

Now pre-commit will automatically run these checks before every commit, preventing commits that don't meet quality standards.

#### Summary of Pre-Commit Checks

| Check               | Command                 | Purpose                              |
|---------------------|-------------------------|--------------------------------------|
| Format code         | `ruff format`           | Ensure consistent code formatting    |
| Fix linting issues  | `ruff check --fix`      | Auto-fix code quality issues         |
| Check linting       | `ruff check`            | Verify no remaining violations       |
| Run tests           | `pytest`                | Ensure code works correctly          |
| Check coverage      | `pytest --cov=src`      | Verify test coverage                 |
| Type checking       | `mypy src/`             | Verify type annotations              |
| Review changes      | `git diff`              | Manually review all changes          |

**Best Practices**:

1. Run checks frequently during development, not just before committing
2. Fix issues as they arise rather than accumulating technical debt
3. Don't commit code with failing tests or linting violations
4. Use pre-commit hooks to automate checks and prevent mistakes
5. Keep the feedback loop fast - run quick checks (format, lint) often
