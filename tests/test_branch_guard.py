"""Tests for the Codex PreToolUse hook in .codex/hooks/branch_guard.py."""

import json
import subprocess
import sys
from pathlib import Path

import pytest

GUARD = Path(__file__).resolve().parents[1] / ".codex" / "hooks" / "branch_guard.py"


def envelope(*lines):
    """Wrap apply_patch header lines in a Begin/End Patch envelope."""
    return "\n".join(["*** Begin Patch", *lines, "*** End Patch"])


def run_guard(cwd, patch):
    """Feed the hook a PreToolUse payload for patch and return the finished process."""
    payload = json.dumps(
        {"cwd": str(cwd), "tool_name": "apply_patch", "tool_input": {"command": patch}},
    )
    return subprocess.run(
        [sys.executable, str(GUARD)],
        input=payload,
        capture_output=True,
        text=True,
        check=False,
    )


@pytest.fixture
def repo(tmp_path):
    """Return a repo on main holding one tracked file and one gitignored directory."""
    git = ["git", "-C", str(tmp_path)]
    subprocess.run(["git", "init", "-q", "-b", "main", str(tmp_path)], check=True)
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "config.py").write_text("x = 1\n")
    (tmp_path / ".gitignore").write_text("docs/summaries/\n")
    (tmp_path / "docs" / "summaries").mkdir(parents=True)
    subprocess.run([*git, "add", "-A"], check=True)
    subprocess.run(
        [*git, "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "init"],
        check=True,
    )
    return tmp_path


def test_branch_guard_blocks_tracked_file_on_main(repo):
    """Test the hook denies a patch that edits a tracked file while main is checked out."""
    result = run_guard(repo, envelope("*** Update File: src/config.py"))

    assert result.returncode == 2
    assert "protected main branch" in result.stderr


@pytest.mark.parametrize(
    "header",
    ["*** Add File: src/new.py", "*** Delete File: src/config.py"],
)
def test_branch_guard_blocks_added_and_deleted_paths_on_main(repo, header):
    """Test the hook reads Add and Delete headers, not only Update."""
    assert run_guard(repo, envelope(header)).returncode == 2


def test_branch_guard_blocks_a_rename_out_of_an_ignored_directory(repo):
    """Test the hook checks a rename's destination, so ignored-to-tracked still blocks."""
    patch = envelope(
        "*** Update File: docs/summaries/handoff.md",
        "*** Move to: src/handoff.py",
    )

    assert run_guard(repo, patch).returncode == 2


def test_branch_guard_allows_gitignored_file_on_main(repo):
    """Test gitignored paths stay editable on main, matching the Claude Code hook."""
    patch = envelope("*** Update File: docs/summaries/handoff.md")

    assert run_guard(repo, patch).returncode == 0


def test_branch_guard_allows_tracked_file_on_a_feature_branch(repo):
    """Test the hook only guards main, so a feature branch edits freely."""
    subprocess.run(
        ["git", "-C", str(repo), "checkout", "-q", "-b", "codex-x"],
        check=True,
    )

    assert run_guard(repo, envelope("*** Update File: src/config.py")).returncode == 0


def test_branch_guard_allows_paths_outside_any_repository(tmp_path):
    """Test the hook stays out of the way when the patch lands outside a git repo."""
    assert run_guard(tmp_path, envelope("*** Add File: notes.txt")).returncode == 0


def test_branch_guard_ignores_a_malformed_payload():
    """Test the hook fails open rather than blocking when stdin is not JSON."""
    result = subprocess.run(
        [sys.executable, str(GUARD)],
        input="not json",
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0
