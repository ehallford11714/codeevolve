"""Real patch engine: unified hunks, fail-closed apply, symbol/CST fence."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from codeevolve.agent.workspace import FileEdit, PatchResult, Workspace
from codeevolve.taxonomy.symbols import SymbolNode, scan_symbols


@dataclass
class Hunk:
    old_start: int
    old_count: int
    new_start: int
    new_count: int
    lines: list[str]  # raw hunk lines including prefixes

    def to_dict(self) -> dict[str, Any]:
        return {
            "old_start": self.old_start,
            "old_count": self.old_count,
            "new_start": self.new_start,
            "new_count": self.new_count,
            "lines": list(self.lines),
        }


@dataclass
class FilePatch:
    path: str
    hunks: list[Hunk] = field(default_factory=list)
    is_new: bool = False
    is_delete: bool = False
    full_content: str | None = None  # whole-file fallback

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "hunks": [h.to_dict() for h in self.hunks],
            "is_new": self.is_new,
            "is_delete": self.is_delete,
            "full_content": self.full_content is not None,
        }


@dataclass
class SymbolFence:
    path: str
    qualname: str
    kind: str
    start_line: int
    end_line: int

    def contains_line(self, line: int) -> bool:
        return self.start_line <= line <= self.end_line

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "qualname": self.qualname,
            "kind": self.kind,
            "start_line": self.start_line,
            "end_line": self.end_line,
        }


_HUNK_HDR = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")


def parse_unified_patches(diff_text: str) -> list[FilePatch]:
    """Parse unified diffs into FilePatch objects (hunk-aware). Fail soft → []."""
    text = (diff_text or "").strip()
    if "```" in text:
        blocks = re.findall(r"```(?:diff|patch)?\n([\s\S]*?)```", text)
        if blocks:
            text = "\n\n".join(blocks)

    patches: list[FilePatch] = []

    # Whole-file FILE:/END FILE still supported as full_content patches
    for m in re.finditer(r"(?m)^FILE:\s*(?P<path>\S+)\n([\s\S]*?)^END FILE\s*$", text):
        patches.append(FilePatch(path=m.group("path").strip(), full_content=m.group(2)))

    # Standard unified diff
    parts = re.split(r"(?m)^diff --git ", text)
    for part in parts:
        if not part.strip():
            continue
        if not part.startswith("a/") and "--- " not in part:
            # may be fragment without diff --git header
            body = part
            path = None
        else:
            body = "diff --git " + part if not part.startswith("diff") else part
            mpath = re.search(r"^diff --git a/(.+?) b/(.+)$", body, re.M)
            path = mpath.group(2).strip() if mpath else None

        m_new = re.search(r"^\+\+\+ (?:b/(.+)|/dev/null)\s*$", body, re.M)
        m_old = re.search(r"^--- (?:a/(.+)|/dev/null)\s*$", body, re.M)
        if m_new and m_new.group(1):
            path = m_new.group(1).strip()
        if path is None and m_old and m_old.group(1):
            path = m_old.group(1).strip()
        if not path:
            continue

        is_new = bool(m_old and "/dev/null" in (m_old.group(0) or ""))
        is_delete = bool(m_new and "/dev/null" in (m_new.group(0) or ""))
        hunks: list[Hunk] = []
        lines = body.splitlines()
        i = 0
        while i < len(lines):
            hm = _HUNK_HDR.match(lines[i])
            if not hm:
                i += 1
                continue
            old_s, old_c = int(hm.group(1)), int(hm.group(2) or "1")
            new_s, new_c = int(hm.group(3)), int(hm.group(4) or "1")
            i += 1
            h_lines: list[str] = []
            while i < len(lines) and not lines[i].startswith("diff --git") and not _HUNK_HDR.match(lines[i]):
                if lines[i].startswith("--- ") or lines[i].startswith("+++ "):
                    break
                h_lines.append(lines[i])
                i += 1
            hunks.append(Hunk(old_s, old_c, new_s, new_c, h_lines))
        if hunks or is_new or is_delete:
            patches.append(FilePatch(path=path, hunks=hunks, is_new=is_new, is_delete=is_delete))

    return patches


def apply_hunks_to_text(original: str, hunks: list[Hunk]) -> tuple[str | None, str | None]:
    """Apply hunks to original text. Returns (new_text, error). Fail closed."""
    src = original.splitlines(keepends=True)
    # Normalize to lines without forcing keepends complexity
    lines = original.splitlines()
    # Ensure trailing newline behavior
    had_trailing = original.endswith("\n") if original else True

    # Apply from bottom to top so offsets stay valid
    for hunk in sorted(hunks, key=lambda h: -h.old_start):
        start = max(0, hunk.old_start - 1)
        old_lines: list[str] = []
        new_lines: list[str] = []
        for raw in hunk.lines:
            if raw.startswith("\\"):  # "\ No newline at end of file"
                continue
            if raw.startswith("+") and not raw.startswith("+++"):
                new_lines.append(raw[1:])
            elif raw.startswith("-") and not raw.startswith("---"):
                old_lines.append(raw[1:])
            elif raw.startswith(" "):
                old_lines.append(raw[1:])
                new_lines.append(raw[1:])
            elif raw.startswith("@@"):
                continue
            else:
                # context without prefix (tolerant)
                old_lines.append(raw)
                new_lines.append(raw)

        end = start + len(old_lines)
        chunk = lines[start:end]
        if chunk != old_lines:
            # try fuzzy: strip trailing spaces
            if [c.rstrip() for c in chunk] != [c.rstrip() for c in old_lines]:
                return None, (
                    f"hunk mismatch at line {hunk.old_start}: "
                    f"expected {old_lines[:3]!r} got {chunk[:3]!r}"
                )
        lines = lines[:start] + new_lines + lines[end:]

    out = "\n".join(lines)
    if had_trailing and (out and not out.endswith("\n")):
        out += "\n"
    return out, None


def symbol_fence_for(
    path: str,
    text: str,
    *,
    qualname: str | None = None,
    line: int | None = None,
) -> SymbolFence | None:
    """Build a symbol fence for a qualname or nearest symbol at line.

    Prefers stdlib AST (Python) or tree-sitter spans when available; falls back
    to regex start + next-symbol end estimate.
    """
    nodes, engine = scan_symbols(path, text)
    if not nodes:
        return None
    ordered = sorted(nodes, key=lambda n: n.line)
    ends: dict[str, int] = {}
    for i, n in enumerate(ordered):
        if n.end_line is not None:
            ends[n.qualname] = max(n.line, int(n.end_line))
        else:
            end = ordered[i + 1].line - 1 if i + 1 < len(ordered) else text.count("\n") + 1
            ends[n.qualname] = max(n.line, end)

    chosen: SymbolNode | None = None
    if qualname:
        for n in ordered:
            if (
                n.qualname == qualname
                or n.qualname.endswith(f"::{qualname}")
                or n.qualname.split("::")[-1] == qualname
            ):
                chosen = n
                break
    if chosen is None and line is not None:
        # innermost: latest start ≤ line whose end ≥ line when known
        for n in reversed(ordered):
            end = ends.get(n.qualname, n.line)
            if n.line <= line <= end:
                chosen = n
                break
        if chosen is None:
            for n in reversed(ordered):
                if n.line <= line:
                    chosen = n
                    break
    if chosen is None:
        chosen = ordered[0]
    fence = SymbolFence(
        path=path,
        qualname=chosen.qualname,
        kind=chosen.kind,
        start_line=chosen.line,
        end_line=ends.get(chosen.qualname, chosen.line),
    )
    # stash engine hint for callers via kind tag when useful
    _ = engine
    return fence


def hunks_respect_fence(hunks: list[Hunk], fence: SymbolFence) -> tuple[bool, str]:
    for h in hunks:
        # changed lines span old_start .. old_start+old_count
        lo, hi = h.old_start, h.old_start + max(h.old_count, 1) - 1
        if lo < fence.start_line or hi > fence.end_line:
            return False, (
                f"hunk {lo}-{hi} outside symbol fence "
                f"{fence.qualname} L{fence.start_line}-{fence.end_line}"
            )
    return True, ""


def apply_patches(
    workspace: Workspace,
    patches: list[FilePatch],
    *,
    snapshot_dir: Path | str | None = None,
    symbol_fence: SymbolFence | None = None,
    fail_closed: bool = True,
) -> PatchResult:
    """Apply parsed patches. On any hunk failure with fail_closed, apply nothing new after snapshot."""
    result = PatchResult()
    paths = [p.path for p in patches]
    if snapshot_dir is not None:
        result.snapshot_dir = str(workspace.snapshot(paths, snapshot_dir))

    pending: list[tuple[str, str, str]] = []  # path, content, mode
    for patch in patches:
        rel = workspace._norm(patch.path)
        if not workspace.allowed(rel):
            result.skipped.append(rel)
            result.errors.append(f"outside path fence: {rel}")
            if fail_closed:
                return _fail(result, workspace)
            continue
        if patch.is_delete:
            pending.append((rel, "", "delete"))
            continue
        if patch.full_content is not None:
            if symbol_fence and symbol_fence.path == rel:
                result.errors.append("full-file replace blocked by symbol fence")
                if fail_closed:
                    return _fail(result, workspace)
                continue
            pending.append((rel, patch.full_content, "write"))
            continue
        original = workspace.read_text(rel) if (workspace.root / rel).exists() else ""
        if symbol_fence and symbol_fence.path == rel and patch.hunks:
            ok, err = hunks_respect_fence(patch.hunks, symbol_fence)
            if not ok:
                result.errors.append(err)
                if fail_closed:
                    return _fail(result, workspace)
                continue
        new_text, err = apply_hunks_to_text(original, patch.hunks)
        if err or new_text is None:
            result.errors.append(f"{rel}: {err or 'apply failed'}")
            if fail_closed:
                return _fail(result, workspace)
            result.skipped.append(rel)
            continue
        pending.append((rel, new_text, "write"))

    if result.errors and fail_closed and not pending:
        return result

    edits = [FileEdit(path=p, content=c, mode=m) for p, c, m in pending]
    applied = workspace.apply_edits(edits, snapshot_dir=None)
    result.applied.extend(applied.applied)
    result.skipped.extend(applied.skipped)
    result.errors.extend(applied.errors)
    if fail_closed and result.errors and result.snapshot_dir:
        # roll back partial
        workspace.restore(result.snapshot_dir)
        result.applied = []
        result.errors.append("fail_closed: rolled back after patch errors")
    return result


def _fail(result: PatchResult, workspace: Workspace) -> PatchResult:
    if result.snapshot_dir:
        workspace.restore(result.snapshot_dir)
    result.applied = []
    result.errors.append("fail_closed: no patches applied")
    return result


def patches_to_file_edits(workspace: Workspace, patches: list[FilePatch]) -> list[FileEdit]:
    """Materialize patches to FileEdit list (for preview); does not write."""
    edits: list[FileEdit] = []
    for patch in patches:
        if patch.full_content is not None:
            edits.append(FileEdit(path=patch.path, content=patch.full_content, mode="write"))
            continue
        if patch.is_delete:
            edits.append(FileEdit(path=patch.path, content="", mode="delete"))
            continue
        original = workspace.read_text(patch.path)
        new_text, err = apply_hunks_to_text(original, patch.hunks)
        if new_text is not None and not err:
            edits.append(FileEdit(path=patch.path, content=new_text, mode="write"))
    return edits
