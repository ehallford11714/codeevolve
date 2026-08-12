"""Git-safe worktree / branch loop for agent rounds."""

from __future__ import annotations

import os
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class GitSession:
    repo: str
    base_branch: str
    work_branch: str
    worktree_path: str | None = None
    created_worktree: bool = False
    commits: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "repo": self.repo,
            "base_branch": self.base_branch,
            "work_branch": self.work_branch,
            "worktree_path": self.worktree_path,
            "created_worktree": self.created_worktree,
            "commits": list(self.commits),
            "notes": list(self.notes),
        }


def _git(repo: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True,
        text=True,
        check=check,
    )


def is_git_repo(repo: Path | str) -> bool:
    p = Path(repo)
    try:
        r = _git(p, "rev-parse", "--is-inside-work-tree", check=False)
        return r.returncode == 0 and "true" in (r.stdout or "")
    except (OSError, subprocess.SubprocessError):
        return False


def dirty_files(repo: Path | str) -> list[str]:
    p = Path(repo)
    r = _git(p, "status", "--porcelain", check=False)
    if r.returncode != 0:
        return []
    out = []
    for line in (r.stdout or "").splitlines():
        if len(line) >= 4:
            out.append(line[3:].strip().replace("\\", "/"))
    return out


def current_branch(repo: Path | str) -> str:
    r = _git(Path(repo), "rev-parse", "--abbrev-ref", "HEAD", check=False)
    return (r.stdout or "HEAD").strip() or "HEAD"


def begin_session(
    repo: Path | str,
    *,
    use_worktree: bool = True,
    branch_prefix: str = "codeevolve/agent",
) -> GitSession:
    """Create a disposable branch (and optional worktree) for agent edits."""
    root = Path(repo).resolve()
    session = GitSession(
        repo=str(root),
        base_branch=current_branch(root),
        work_branch=f"{branch_prefix}-{time.strftime('%Y%m%d-%H%M%S')}",
    )
    if not is_git_repo(root):
        session.notes.append("not a git repo — session is no-op")
        return session

    dirty = dirty_files(root)
    if dirty:
        session.notes.append(f"base tree has {len(dirty)} dirty files; worktree isolates agent writes")

    # Create branch from HEAD
    _git(root, "branch", session.work_branch, check=False)

    if use_worktree:
        wt = root / ".codeevolve" / "worktrees" / session.work_branch.replace("/", "_")
        wt.parent.mkdir(parents=True, exist_ok=True)
        if wt.exists():
            session.worktree_path = str(wt)
            session.notes.append("worktree path exists; reusing")
        else:
            r = _git(root, "worktree", "add", str(wt), session.work_branch, check=False)
            if r.returncode == 0:
                session.worktree_path = str(wt)
                session.created_worktree = True
            else:
                session.notes.append(f"worktree add failed: {(r.stderr or '')[:200]}; using in-place branch checkout")
                _git(root, "checkout", session.work_branch, check=False)
    else:
        _git(root, "checkout", session.work_branch, check=False)

    return session


def working_root(session: GitSession) -> Path:
    if session.worktree_path:
        return Path(session.worktree_path)
    return Path(session.repo)


def commit_accepted(
    session: GitSession,
    *,
    message: str,
    paths: list[str] | None = None,
) -> str | None:
    """Stage agent paths and commit on the work branch. Returns sha or None."""
    root = working_root(session)
    if not is_git_repo(root):
        return None
    if paths:
        for p in paths:
            _git(root, "add", "--", p, check=False)
    else:
        _git(root, "add", "-A", check=False)
    # don't commit if nothing staged
    staged = _git(root, "diff", "--cached", "--name-only", check=False)
    if not (staged.stdout or "").strip():
        session.notes.append("nothing to commit")
        return None
    env = os.environ.copy()
    env.setdefault("GIT_AUTHOR_NAME", "CodeEvolve Agent")
    env.setdefault("GIT_AUTHOR_EMAIL", "agent@codeevolve.local")
    env.setdefault("GIT_COMMITTER_NAME", env["GIT_AUTHOR_NAME"])
    env.setdefault("GIT_COMMITTER_EMAIL", env["GIT_AUTHOR_EMAIL"])
    r = subprocess.run(
        ["git", "-C", str(root), "commit", "-m", message],
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )
    if r.returncode != 0:
        session.notes.append(f"commit failed: {(r.stderr or '')[:200]}")
        return None
    sha = _git(root, "rev-parse", "HEAD", check=False).stdout.strip()
    if sha:
        session.commits.append(sha)
    return sha or None


def end_session(
    session: GitSession,
    *,
    keep_branch: bool = True,
    restore_base: bool = True,
) -> None:
    """Remove disposable worktree; optionally leave branch for PR."""
    root = Path(session.repo)
    if session.created_worktree and session.worktree_path:
        _git(root, "worktree", "remove", "--force", session.worktree_path, check=False)
        session.notes.append("worktree removed")
    elif restore_base and session.base_branch and session.base_branch != "HEAD":
        # only if we checked out in-place
        if not session.worktree_path:
            _git(root, "checkout", session.base_branch, check=False)
    if not keep_branch and session.work_branch:
        _git(root, "branch", "-D", session.work_branch, check=False)
