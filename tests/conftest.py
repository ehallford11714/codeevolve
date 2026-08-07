"""Shared fixtures — tiny synthetic git repo."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest


def _git(repo: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        capture_output=True,
        text=True,
    )


@pytest.fixture
def sample_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "proj"
    repo.mkdir()
    _git(repo, "init")
    _git(repo, "config", "user.email", "dev@example.com")
    _git(repo, "config", "user.name", "Dev")

    (repo / "src").mkdir()
    (repo / "tests").mkdir()
    (repo / "src" / "app.py").write_text("def main():\n    return 1\n", encoding="utf-8")
    (repo / "tests" / "test_app.py").write_text("def test_main():\n    assert True\n", encoding="utf-8")
    (repo / "requirements.txt").write_text("pyyaml>=6\n", encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-m", "feat: initial app scaffold")

    (repo / "src" / "app.py").write_text(
        "def main():\n    return 2  # FIXME: tech debt\n# deprecated helper below\n",
        encoding="utf-8",
    )
    _git(repo, "add", "-A")
    _git(repo, "commit", "-m", "feat: bump return value")

    (repo / "src" / "utils.py").write_text("def helper():\n    pass\n", encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-m", "refactor: extract utils helper")

    (repo / "requirements.txt").write_text("pyyaml>=6\nrequests>=2\n", encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-m", "chore: add requests dependency")

    # revert the dependency commit
    sha = subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    _git(repo, "revert", "--no-edit", sha)

    (repo / "src" / "app.py").write_text(
        "def main():\n    return 3\n",
        encoding="utf-8",
    )
    _git(repo, "add", "-A")
    _git(repo, "commit", "-m", "fix: correct return behavior")

    return repo
