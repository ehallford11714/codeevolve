"""Clone genealogy across commit windows (Kim-style patterns)."""

from __future__ import annotations

import hashlib
import re
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from codeevolve.gitlog import CommitRecord, show_file_at

_FN_RE = re.compile(
    r"(?:(?:async\s+)?def\s+([A-Za-z_][\w]*)\s*\()|"
    r"(?:(?:export\s+)?(?:async\s+)?function\s+([A-Za-z_][\w]*)\s*\()|"
    r"(?:(?:pub\s+)?(?:async\s+)?fn\s+([A-Za-z_][\w]*)\s*[<(])",
    re.M,
)


@dataclass
class CloneGenealogyReport:
    genealogies: list[dict[str, Any]] = field(default_factory=list)
    pattern_counts: dict[str, int] = field(default_factory=dict)
    summary: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "genealogies": list(self.genealogies[:40]),
            "pattern_counts": dict(self.pattern_counts),
            "summary": self.summary,
        }


def _snippets(path: str, text: str) -> list[tuple[str, str]]:
    """Return (qualname, body_hash) for functions found in text."""
    out: list[tuple[str, str]] = []
    for m in _FN_RE.finditer(text):
        name = m.group(1) or m.group(2) or m.group(3)
        if not name:
            continue
        start = m.start()
        # take ~40 lines of body for fingerprint
        chunk = text[start : start + 800]
        h = hashlib.sha1(chunk.encode("utf-8", errors="replace")).hexdigest()[:12]
        out.append((f"{path}::{name}", h))
    return out


def analyze_clone_genealogy(
    repo: Path | str,
    commits: list[CommitRecord],
    *,
    windows: int = 4,
    max_paths: int = 40,
) -> CloneGenealogyReport:
    """Track clone-group fingerprints across time windows."""
    if not commits:
        return CloneGenealogyReport(summary="No commits")

    ordered = sorted(commits, key=lambda c: c.timestamp)
    # focus paths that appear often
    touches: dict[str, int] = defaultdict(int)
    for c in ordered:
        for f in c.files:
            if Path(f).suffix.lower() in {".py", ".js", ".ts", ".tsx", ".go", ".rs"}:
                touches[f] += 1
    paths = [p for p, _ in sorted(touches.items(), key=lambda x: -x[1])[:max_paths]]
    if not paths:
        return CloneGenealogyReport(summary="No source paths for clone genealogy")

    n = len(ordered)
    chunk = max(1, n // windows)
    samples: list[tuple[str, dict[str, set[str]]]] = []  # (label, hash -> qualnames)
    for i in range(windows):
        part = ordered[i * chunk : (i + 1) * chunk] if i < windows - 1 else ordered[i * chunk :]
        if not part:
            continue
        sha = part[-1].sha
        hash_to_names: dict[str, set[str]] = defaultdict(set)
        for path in paths:
            text = show_file_at(repo, sha, path)
            if not text:
                continue
            for qn, h in _snippets(path, text):
                hash_to_names[h].add(qn)
        # keep only groups with ≥2 members (true clones)
        clones = {h: ns for h, ns in hash_to_names.items() if len(ns) >= 2}
        samples.append((f"w{i}", clones))

    # Track hash lineages across windows
    all_hashes = set()
    for _, clones in samples:
        all_hashes |= set(clones)

    genealogies: list[dict[str, Any]] = []
    patterns: dict[str, int] = defaultdict(int)
    for h in list(all_hashes)[:200]:
        presence: list[bool] = []
        sizes: list[int] = []
        members_over_time: list[set[str]] = []
        for _, clones in samples:
            ns = clones.get(h, set())
            presence.append(bool(ns))
            sizes.append(len(ns))
            members_over_time.append(ns)

        if not any(presence):
            continue
        first = next(i for i, p in enumerate(presence) if p)
        last = max(i for i, p in enumerate(presence) if p)
        born = first
        died = last < len(presence) - 1
        # consistent: same member set while present
        present_sets = [s for s, p in zip(members_over_time, presence) if p]
        consistent = len(present_sets) >= 2 and all(s == present_sets[0] for s in present_sets)
        # diverge: membership changed while hash lineage "alive"
        diverge = len(present_sets) >= 2 and not consistent
        # late proliferation: size grew in later windows
        proliferate = len(sizes) >= 2 and max(sizes) > sizes[first] and sizes[-1] >= sizes[first] + 1

        if died and last - born <= 1:
            pattern = "short_lived"
        elif consistent:
            pattern = "consistent_coevolution"
        elif diverge:
            pattern = "divergent"
        elif proliferate:
            pattern = "late_proliferation"
        else:
            pattern = "stable"
        patterns[pattern] += 1
        genealogies.append(
            {
                "fingerprint": h,
                "pattern": pattern,
                "born_window": born,
                "died": died,
                "sizes": sizes,
                "members": sorted(present_sets[-1])[:12] if present_sets else [],
            }
        )

    genealogies.sort(key=lambda g: (0 if g["pattern"] == "divergent" else 1, -max(g["sizes"] or [0])))
    top = ", ".join(f"{k}:{v}" for k, v in sorted(patterns.items())) or "none"
    return CloneGenealogyReport(
        genealogies=genealogies,
        pattern_counts=dict(patterns),
        summary=f"{len(genealogies)} clone genealogies; patterns {top}",
    )
