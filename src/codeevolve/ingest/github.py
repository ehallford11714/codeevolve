"""Resolve local paths or GitHub URLs into a local git checkout."""

from __future__ import annotations

import hashlib
import re
import subprocess
from pathlib import Path

from codeevolve.gitlog import assert_git_repo

_GH_RE = re.compile(
    r"^(?:https?://)?(?:www\.)?github\.com/([^/]+)/([^/]+?)(?:\.git)?/?$",
    re.I,
)
_GH_SSH_RE = re.compile(r"^git@github\.com:([^/]+)/([^/]+?)(?:\.git)?$", re.I)


def _cache_root() -> Path:
    root = Path.home() / ".codeevolve" / "repos"
    root.mkdir(parents=True, exist_ok=True)
    return root


def parse_github_url(spec: str) -> tuple[str, str] | None:
    s = spec.strip().rstrip("/")
    m = _GH_RE.match(s) or _GH_SSH_RE.match(s)
    if not m:
        return None
    owner, repo = m.group(1), m.group(2)
    if repo.endswith(".git"):
        repo = repo[:-4]
    return owner, repo


def clone_or_update(owner: str, repo: str, *, depth: int = 200) -> Path:
    key = hashlib.sha1(f"{owner}/{repo}".encode()).hexdigest()[:12]
    dest = _cache_root() / f"{owner}__{repo}__{key}"
    url = f"https://github.com/{owner}/{repo}.git"
    if (dest / ".git").is_dir():
        subprocess.run(
            ["git", "-C", str(dest), "fetch", "--depth", str(depth), "origin"],
            capture_output=True,
            text=True,
            check=False,
        )
        subprocess.run(
            ["git", "-C", str(dest), "checkout", "-f", "FETCH_HEAD"],
            capture_output=True,
            text=True,
            check=False,
        )
        # Prefer default branch tip if fetch left us detached
        subprocess.run(
            ["git", "-C", str(dest), "pull", "--ff-only"],
            capture_output=True,
            text=True,
            check=False,
        )
        return assert_git_repo(dest)

    dest.parent.mkdir(parents=True, exist_ok=True)
    proc = subprocess.run(
        ["git", "clone", f"--depth={depth}", url, str(dest)],
        capture_output=True,
        text=True,
        check=False,
        encoding="utf-8",
        errors="replace",
    )
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or f"git clone failed for {url}")
    return assert_git_repo(dest)


def resolve_repo(spec: str | Path, *, depth: int = 200) -> tuple[Path, str]:
    """
    Return (local_repo_path, display_name).

    ``spec`` may be a filesystem path or a github.com URL / owner/repo shorthand.
    """
    raw = str(spec).strip()
    gh = parse_github_url(raw)
    if gh is None and re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", raw):
        parts = raw.split("/", 1)
        gh = (parts[0], parts[1])
    if gh is not None:
        path = clone_or_update(gh[0], gh[1], depth=depth)
        return path, f"https://github.com/{gh[0]}/{gh[1]}"
    path = assert_git_repo(Path(raw))
    return path, str(path)
