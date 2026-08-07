"""CST / node-type evolution metrics across commit windows (GitEvo-style)."""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from codeevolve.gitlog import CommitRecord, show_file_at

# Regex node-type proxies when tree-sitter unavailable
_NODE_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("function", re.compile(r"\b(?:def|function|fn)\s+[A-Za-z_]", re.M)),
    ("class", re.compile(r"\bclass\s+[A-Za-z_]", re.M)),
    ("async", re.compile(r"\basync\b")),
    ("import", re.compile(r"^\s*(?:import|from|require\(|use\s)", re.M)),
    ("if", re.compile(r"\bif\b")),
    ("for", re.compile(r"\bfor\b")),
    ("try", re.compile(r"\b(?:try|catch|except)\b")),
    ("decorator", re.compile(r"^\s*@", re.M)),
    ("type_hint", re.compile(r"->\s*[A-Za-z_\[]|:\s*[A-Za-z_][\w\[\], ]*=", re.M)),
]


@dataclass
class CstEvolutionReport:
    windows: list[dict[str, Any]] = field(default_factory=list)
    deltas: list[dict[str, Any]] = field(default_factory=list)
    engine: str = "regex"
    summary: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "engine": self.engine,
            "windows": list(self.windows),
            "deltas": list(self.deltas[:40]),
            "summary": self.summary,
        }


def _regex_hist(text: str) -> Counter[str]:
    c: Counter[str] = Counter()
    for name, rx in _NODE_PATTERNS:
        c[name] += len(rx.findall(text))
    return c


def _treesitter_hist(path: str, text: str) -> Counter[str] | None:
    if Path(path).suffix.lower() != ".py":
        return None
    try:
        from tree_sitter_languages import get_parser  # type: ignore
    except Exception:
        return None
    try:
        parser = get_parser("python")
        tree = parser.parse(text.encode("utf-8", errors="replace"))
    except Exception:
        return None
    c: Counter[str] = Counter()

    def walk(node: Any) -> None:
        c[node.type] += 1
        for ch in node.children:
            walk(ch)

    walk(tree.root_node)
    # keep informative subset
    keep = {
        "function_definition",
        "class_definition",
        "if_statement",
        "for_statement",
        "while_statement",
        "try_statement",
        "decorated_definition",
        "import_statement",
        "import_from_statement",
        "async",
        "type",
        "typed_parameter",
    }
    return Counter({k: v for k, v in c.items() if k in keep or v >= 5})


def analyze_cst_evolution(
    repo: Path | str,
    commits: list[CommitRecord],
    *,
    windows: int = 4,
    max_paths: int = 35,
) -> CstEvolutionReport:
    if not commits:
        return CstEvolutionReport(summary="No commits")

    ordered = sorted(commits, key=lambda c: c.timestamp)
    touches: dict[str, int] = defaultdict(int)
    for c in ordered:
        for f in c.files:
            if Path(f).suffix.lower() in {".py", ".js", ".ts", ".tsx", ".go", ".rs"}:
                touches[f] += 1
    paths = [p for p, _ in sorted(touches.items(), key=lambda x: -x[1])[:max_paths]]

    n = len(ordered)
    chunk = max(1, n // windows)
    engine = "regex"
    win_rows: list[dict[str, Any]] = []
    prev: Counter[str] | None = None
    deltas: list[dict[str, Any]] = []

    for i in range(windows):
        part = ordered[i * chunk : (i + 1) * chunk] if i < windows - 1 else ordered[i * chunk :]
        if not part:
            continue
        sha = part[-1].sha
        hist: Counter[str] = Counter()
        for path in paths:
            text = show_file_at(repo, sha, path)
            if not text:
                continue
            ts = _treesitter_hist(path, text)
            if ts is not None:
                engine = "tree_sitter+regex"
                hist.update(ts)
            else:
                hist.update(_regex_hist(text))
        row = {"window": f"w{i}", "sha": sha[:10], "counts": dict(hist.most_common(40))}
        win_rows.append(row)
        if prev is not None:
            keys = set(prev) | set(hist)
            for k in sorted(keys):
                d = hist.get(k, 0) - prev.get(k, 0)
                if d != 0:
                    deltas.append({"from": f"w{i-1}", "to": f"w{i}", "node": k, "delta": d})
        prev = hist

    deltas.sort(key=lambda d: -abs(d["delta"]))
    return CstEvolutionReport(
        windows=win_rows,
        deltas=deltas,
        engine=engine,
        summary=f"{len(win_rows)} CST windows ({engine}); {len(deltas)} node deltas",
    )
