#!/usr/bin/env python3
"""Block apply_patch edits to tracked repo files while the checkout sits on main."""

import json
import subprocess
import sys
from pathlib import Path

PROTECTED_BRANCH = "main"
PATCH_HEADERS = (
    "*** Add File: ",
    "*** Update File: ",
    "*** Delete File: ",
    "*** Move to: ",
)
BLOCK_MESSAGE = (
    "Blocked: editing a repo file on the protected main branch. "
    "Create a feature branch first (git checkout -b <scope>-<short-desc>), then retry."
)


def git(cwd: Path, *args: str) -> str:
    """Run git in cwd, returning stripped stdout or an empty string on any failure."""
    try:
        result = subprocess.run(
            ["git", "-C", str(cwd), *args],
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        return ""
    return result.stdout.strip() if result.returncode == 0 else ""


def patched_paths(patch: str, cwd: Path) -> list[Path]:
    """Resolve every path an apply_patch envelope touches against the session cwd."""
    paths = []
    for line in patch.splitlines():
        stripped = line.strip()
        header = next((h for h in PATCH_HEADERS if stripped.startswith(h)), None)
        if header is not None:
            paths.append(cwd / stripped.removeprefix(header).strip())
    return paths


def nearest_existing_dir(path: Path) -> Path:
    """Walk up from the path's parent to the first directory that exists."""
    directory = path.parent
    while not directory.is_dir() and directory != directory.parent:
        directory = directory.parent
    return directory


def is_blocked(path: Path) -> bool:
    """Report whether this path is a tracked repo file on the protected branch."""
    root = git(nearest_existing_dir(path), "rev-parse", "--show-toplevel")
    if not root:
        return False
    repo = Path(root)
    if git(repo, "check-ignore", str(path)):
        return False
    return git(repo, "branch", "--show-current") == PROTECTED_BRANCH


def main() -> int:
    """Exit 2 with a reason on stderr when the patch would edit a repo file on main."""
    try:
        payload = json.load(sys.stdin)
    except ValueError:  # JSONDecodeError and UnicodeDecodeError both subclass it
        return 0
    command = payload.get("tool_input", {}).get("command", "")
    if not command:
        return 0
    cwd = Path(payload.get("cwd", "."))
    if any(is_blocked(path) for path in patched_paths(command, cwd)):
        sys.stderr.write(f"{BLOCK_MESSAGE}\n")
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
