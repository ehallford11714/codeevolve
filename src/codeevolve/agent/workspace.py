"""Path fencing, snapshots, and bounded patch application for the agent."""

from __future__ import annotations

import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class FileEdit:
    path: str
    content: str
    mode: str = "write"  # write | create | delete

    def to_dict(self) -> dict[str, Any]:
        return {"path": self.path, "mode": self.mode, "bytes": len(self.content.encode("utf-8"))}


@dataclass
class PatchResult:
    applied: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    snapshot_dir: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "applied": list(self.applied),
            "skipped": list(self.skipped),
            "errors": list(self.errors),
            "snapshot_dir": self.snapshot_dir,
        }


class Workspace:
    """Repo-rooted workspace with path fence + rollback snapshots."""

    def __init__(self, root: Path | str, *, fence_paths: list[str] | None = None) -> None:
        self.root = Path(root).resolve()
        self.fence_paths = [self._norm(p) for p in (fence_paths or []) if p]

    def _norm(self, path: str) -> str:
        p = path.replace("\\", "/").lstrip("./")
        return p

    def resolve(self, path: str) -> Path:
        rel = self._norm(path)
        full = (self.root / rel).resolve()
        if self.root not in full.parents and full != self.root:
            raise ValueError(f"path escapes repo root: {path}")
        return full

    def allowed(self, path: str) -> bool:
        if not self.fence_paths:
            return True
        rel = self._norm(path)
        for fence in self.fence_paths:
            if rel == fence or rel.startswith(fence.rstrip("/") + "/") or fence.startswith(rel.rstrip("/") + "/"):
                return True
            # also allow if fence is a directory prefix of edit, or edit is under fence file's dir
            if fence.endswith(rel) or rel.endswith(fence):
                return True
        return False

    def read_text(self, path: str, *, max_chars: int = 120_000) -> str:
        full = self.resolve(path)
        if not full.is_file():
            return ""
        text = full.read_text(encoding="utf-8", errors="replace")
        return text[:max_chars]

    def snapshot(self, paths: list[str], dest: Path | str) -> Path:
        snap = Path(dest)
        snap.mkdir(parents=True, exist_ok=True)
        for path in paths:
            rel = self._norm(path)
            src = self.resolve(rel)
            if not src.exists():
                (snap / f"{rel}.MISSING").parent.mkdir(parents=True, exist_ok=True)
                (snap / f"{rel}.MISSING").write_text("", encoding="utf-8")
                continue
            target = snap / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            if src.is_file():
                shutil.copy2(src, target)
        return snap

    def restore(self, snapshot_dir: Path | str) -> list[str]:
        snap = Path(snapshot_dir)
        restored: list[str] = []
        if not snap.is_dir():
            return restored
        for missing in snap.rglob("*.MISSING"):
            rel = str(missing.relative_to(snap)).removesuffix(".MISSING").replace("\\", "/")
            full = self.resolve(rel)
            if full.exists():
                full.unlink()
                restored.append(rel)
        for f in snap.rglob("*"):
            if f.is_file() and not f.name.endswith(".MISSING"):
                rel = str(f.relative_to(snap)).replace("\\", "/")
                dest = self.resolve(rel)
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(f, dest)
                restored.append(rel)
        return restored

    def apply_edits(self, edits: list[FileEdit], *, snapshot_dir: Path | str | None = None) -> PatchResult:
        result = PatchResult()
        paths = [e.path for e in edits]
        if snapshot_dir is not None:
            result.snapshot_dir = str(self.snapshot(paths, snapshot_dir))
        for edit in edits:
            rel = self._norm(edit.path)
            if not self.allowed(rel):
                result.skipped.append(rel)
                result.errors.append(f"outside path fence: {rel}")
                continue
            try:
                full = self.resolve(rel)
                if edit.mode == "delete":
                    if full.exists():
                        full.unlink()
                    result.applied.append(rel)
                    continue
                full.parent.mkdir(parents=True, exist_ok=True)
                full.write_text(edit.content, encoding="utf-8")
                result.applied.append(rel)
            except (OSError, ValueError) as exc:
                result.errors.append(f"{rel}: {exc}")
                result.skipped.append(rel)
        return result


_UNIFIED_FILE_RE = re.compile(
    r"^diff --git a/(?P<a>.+?) b/(?P<b>.+?)\n(?:.*\n)*?"
    r"--- (?P<old>/(?:dev/null)|a/.+)\n"
    r"\+\+\+ (?P<new>/(?:dev/null)|b/.+)\n"
    r"(?P<body>(?:@@[\s\S]*?)(?=\ndiff --git |\Z))",
    re.MULTILINE,
)


def parse_unified_diff(diff_text: str) -> list[tuple[str, str]]:
    """Best-effort extract (path, new_file_content) from simple full-file style diffs.

    Prefers fenced ```diff blocks and ``*** Begin Patch`` / ``*** Update File`` forms
    used by coding models; falls back to whole-file replacement markers.
    """
    text = diff_text.strip()
    if "```" in text:
        blocks = re.findall(r"```(?:diff|patch)?\n([\s\S]*?)```", text)
        if blocks:
            text = "\n\n".join(blocks)

    edits: list[tuple[str, str]] = []

    # Cursor-style apply patch
    for m in re.finditer(
        r"\*\*\* (?:Update|Add) File: (?P<path>.+?)\n([\s\S]*?)(?=\n\*\*\* (?:Update|Add|Delete|End) |\Z)",
        text,
    ):
        path = m.group("path").strip()
        body = m.group(2)
        lines_out: list[str] = []
        for line in body.splitlines():
            if line.startswith("+") and not line.startswith("+++"):
                lines_out.append(line[1:])
            elif line.startswith("-") and not line.startswith("---"):
                continue
            elif line.startswith("@@"):
                continue
            elif line.startswith("***"):
                continue
            else:
                # context line may be prefixed with space
                lines_out.append(line[1:] if line.startswith(" ") else line)
        edits.append((path, "\n".join(lines_out) + ("\n" if lines_out else "")))

    if edits:
        return edits

    # Whole-file markers: FILE: path ... END FILE
    for m in re.finditer(
        r"(?m)^FILE:\s*(?P<path>\S+)\n([\s\S]*?)^END FILE\s*$",
        text,
    ):
        edits.append((m.group("path").strip(), m.group(2)))
    return edits


def edits_from_proposals(items: list[dict[str, Any]]) -> list[FileEdit]:
    out: list[FileEdit] = []
    for item in items:
        path = str(item.get("path") or "")
        if not path:
            continue
        mode = str(item.get("mode") or "write")
        content = str(item.get("content") or "")
        out.append(FileEdit(path=path, content=content, mode=mode))
    return out
