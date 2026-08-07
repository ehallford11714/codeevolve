"""Git history ingestion via the git CLI."""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional


@dataclass
class CommitRecord:
    sha: str
    parents: list[str]
    author: str
    email: str
    timestamp: datetime
    subject: str
    body: str = ""
    is_revert: bool = False
    reverts_sha: Optional[str] = None
    files: list[str] = field(default_factory=list)
    insertions: int = 0
    deletions: int = 0
    renames: list[tuple[str, str]] = field(default_factory=list)  # (old, new)

    def to_dict(self) -> dict[str, Any]:
        return {
            "sha": self.sha,
            "parents": list(self.parents),
            "author": self.author,
            "email": self.email,
            "timestamp": self.timestamp.isoformat(),
            "subject": self.subject,
            "body": self.body,
            "is_revert": self.is_revert,
            "reverts_sha": self.reverts_sha,
            "files": list(self.files),
            "insertions": self.insertions,
            "deletions": self.deletions,
            "renames": [{"old": a, "new": b} for a, b in self.renames],
        }


_REVERT_RE = re.compile(r"revert(?:ed)?\s+(?:commit\s+)?([0-9a-f]{7,40})", re.I)
_SHA_RE = re.compile(r"\b([0-9a-f]{7,40})\b", re.I)


def _run_git(repo: Path, *args: str) -> str:
    proc = subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True,
        text=True,
        check=False,
        encoding="utf-8",
        errors="replace",
    )
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or f"git {' '.join(args)} failed")
    return proc.stdout


def assert_git_repo(repo: Path) -> Path:
    repo = Path(repo).resolve()
    try:
        top = _run_git(repo, "rev-parse", "--show-toplevel").strip()
        return Path(top)
    except Exception as exc:
        raise RuntimeError(f"not a git repository: {repo}") from exc


_RENAME_RE = re.compile(r"^\{(.+?)\s*=>\s*(.+?)\}$|^(.+?)\s*=>\s*(.+)$")


def _parse_rename_path(path: str) -> tuple[str, str | None]:
    """Return (current_path, old_path_or_None) for git rename notations."""
    # Forms: old => new  OR  dir/{old => new}/file
    if "=>" not in path:
        return path, None
    if "{" in path and "}" in path:
        pre, rest = path.split("{", 1)
        mid, post = rest.split("}", 1)
        m = re.match(r"^(.*?)\s*=>\s*(.*)$", mid.strip())
        if m:
            old = f"{pre}{m.group(1).strip()}{post}"
            new = f"{pre}{m.group(2).strip()}{post}"
            return new, old
    m = re.match(r"^(.*?)\s*=>\s*(.*)$", path)
    if m:
        return m.group(2).strip(), m.group(1).strip()
    return path, None


def _parse_numstat(repo: Path, sha: str) -> tuple[list[str], int, int, list[tuple[str, str]]]:
    try:
        raw = _run_git(repo, "show", "-M", "--numstat", "--format=", "--norelnotes", sha)
    except RuntimeError:
        try:
            raw = _run_git(repo, "show", "-M", "--numstat", "--format=", sha)
        except RuntimeError:
            return [], 0, 0, []
    files: list[str] = []
    renames: list[tuple[str, str]] = []
    ins = dels = 0
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        parts = line.split("\t")
        if len(parts) < 3:
            continue
        a, b, path = parts[0], parts[1], parts[2]
        if a.isdigit():
            ins += int(a)
        if b.isdigit():
            dels += int(b)
        current, old = _parse_rename_path(path)
        files.append(current)
        if old:
            renames.append((old, current))
    return files, ins, dels, renames


def resolve_rev(repo: Path | str, rev: str) -> str:
    """Resolve a ref/tag/SHA to a commit SHA (raises if missing)."""
    repo = assert_git_repo(Path(repo))
    return _run_git(repo, "rev-parse", "--verify", f"{rev}^{{commit}}").strip()


def ensure_rev(repo: Path | str, rev: str) -> str:
    """Resolve rev; try fetching tags/heads from origin if missing."""
    repo = assert_git_repo(Path(repo))
    try:
        return resolve_rev(repo, rev)
    except RuntimeError:
        pass
    subprocess.run(
        ["git", "-C", str(repo), "fetch", "--tags", "--force", "origin", f"+refs/tags/{rev}:refs/tags/{rev}"],
        capture_output=True,
        text=True,
        check=False,
    )
    subprocess.run(
        ["git", "-C", str(repo), "fetch", "origin", rev],
        capture_output=True,
        text=True,
        check=False,
    )
    return resolve_rev(repo, rev)


def load_commits(
    repo: Path | str,
    *,
    max_commits: int = 500,
    since: str | None = None,
    with_numstat: bool = True,
    rev: str | None = None,
) -> list[CommitRecord]:
    """Load commit metadata (and optional per-commit numstat).

    ``rev`` limits history to commits reachable from that ref (tag/branch/SHA).
    """
    repo = assert_git_repo(Path(repo))
    # RS=%x1e FS=%x1f
    fmt = "%H%x1f%P%x1f%an%x1f%ae%x1f%aI%x1f%s%x1f%b%x1e"
    args = ["log", f"--max-count={max_commits}", f"--pretty=format:{fmt}"]
    if since:
        args.append(f"--since={since}")
    if rev:
        args.append(rev)
    raw = _run_git(repo, *args)
    if not raw.strip():
        return []

    records: list[CommitRecord] = []
    for chunk in raw.split("\x1e"):
        chunk = chunk.strip()
        if not chunk:
            continue
        parts = chunk.split("\x1f")
        if len(parts) < 6:
            continue
        sha, parents_s, author, email, ts_s, subject = parts[:6]
        body = parts[6] if len(parts) > 6 else ""
        try:
            ts = datetime.fromisoformat(ts_s.replace("Z", "+00:00"))
        except ValueError:
            ts = datetime.now(timezone.utc)
        parents = [p for p in parents_s.split() if p]
        blob = f"{subject}\n{body}"
        is_revert = bool(re.search(r"\brevert\b", subject, re.I)) or bool(_REVERT_RE.search(blob))
        reverts_sha = None
        m = _REVERT_RE.search(blob)
        if m:
            reverts_sha = m.group(1)
        elif is_revert:
            m2 = _SHA_RE.search(body) or _SHA_RE.search(subject)
            if m2:
                reverts_sha = m2.group(1)

        files: list[str] = []
        ins = dels = 0
        renames: list[tuple[str, str]] = []
        if with_numstat:
            files, ins, dels, renames = _parse_numstat(repo, sha)

        records.append(
            CommitRecord(
                sha=sha.strip(),
                parents=parents,
                author=author,
                email=email,
                timestamp=ts,
                subject=subject,
                body=body.strip(),
                is_revert=is_revert,
                reverts_sha=reverts_sha,
                files=files,
                insertions=ins,
                deletions=dels,
                renames=renames,
            )
        )
    return records


def list_tracked_files(repo: Path | str) -> list[str]:
    repo = assert_git_repo(Path(repo))
    out = _run_git(repo, "ls-files")
    return [ln for ln in out.splitlines() if ln.strip()]


def show_file_at(repo: Path | str, sha: str, path: str, *, max_bytes: int = 200_000) -> str | None:
    """Return file contents at commit SHA, or None if missing."""
    repo = assert_git_repo(Path(repo))
    try:
        raw = _run_git(repo, "show", f"{sha}:{path}")
    except RuntimeError:
        return None
    if len(raw) > max_bytes:
        return raw[:max_bytes]
    return raw


def list_blobs_at(repo: Path | str, sha: str = "HEAD", *, max_entries: int = 5000) -> list[tuple[str, str]]:
    """Return (blob_sha, path) pairs at a tree-ish."""
    repo = assert_git_repo(Path(repo))
    try:
        raw = _run_git(repo, "ls-tree", "-r", sha)
    except RuntimeError:
        return []
    out: list[tuple[str, str]] = []
    for ln in raw.splitlines():
        # mode type sha\tpath
        parts = ln.split("\t", 1)
        if len(parts) != 2:
            continue
        meta, path = parts
        bits = meta.split()
        if len(bits) < 3 or bits[1] != "blob":
            continue
        out.append((bits[2], path))
        if len(out) >= max_entries:
            break
    return out
