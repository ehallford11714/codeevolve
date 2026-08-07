"""Complexity proxies for hotspot scoring (heuristic + optional tree-sitter)."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

_DECISION_RE = re.compile(
    r"\b(if|elif|else|for|while|case|catch|except|switch|when|match|and|or)\b|"
    r"\?|&&|\|\|",
    re.I,
)


def heuristic_complexity(text: str) -> int:
    """Decision-point count (McCabe-ish) from source text."""
    if not text:
        return 1
    # strip comments roughly
    cleaned = re.sub(r"#.*$", "", text, flags=re.M)
    cleaned = re.sub(r"//.*$", "", cleaned, flags=re.M)
    cleaned = re.sub(r"/\*.*?\*/", "", cleaned, flags=re.S)
    n = 1 + len(_DECISION_RE.findall(cleaned))
    return min(500, n)


def treesitter_complexity(path: str, text: str) -> int | None:
    """Optional tree-sitter decision-node count for Python."""
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
    kinds = {
        "if_statement",
        "for_statement",
        "while_statement",
        "except_clause",
        "conditional_expression",
        "boolean_operator",
        "match_statement",
        "case_clause",
    }
    count = 1

    def walk(node: Any) -> None:
        nonlocal count
        if node.type in kinds:
            count += 1
        for ch in node.children:
            walk(ch)

    walk(tree.root_node)
    return min(500, count)


def file_complexity(path: str, text: str) -> tuple[int, str]:
    ts = treesitter_complexity(path, text)
    if ts is not None:
        return ts, "tree_sitter"
    return heuristic_complexity(text), "heuristic"


def enrich_hotspots(
    repo: Path | str,
    hot_files: list[dict[str, Any]],
    *,
    max_files: int = 20,
) -> list[dict[str, Any]]:
    """Attach complexity + hotspot_score = normalized(churn) × complexity."""
    root = Path(repo)
    out: list[dict[str, Any]] = []
    touches = [int(h.get("touches") or 0) for h in hot_files[:max_files]]
    max_t = max(touches) if touches else 1
    for h in hot_files[:max_files]:
        path = str(h.get("path") or "")
        t = int(h.get("touches") or 0)
        text = ""
        fp = root / path
        if fp.is_file():
            try:
                text = fp.read_text(encoding="utf-8", errors="replace")[:200_000]
            except OSError:
                text = ""
        cx, eng = file_complexity(path, text) if text else (1, "missing")
        churn_n = t / max_t
        score = round(churn_n * (cx / (cx + 20.0)), 4)  # soft-cap complexity
        row = dict(h)
        row.update(
            {
                "complexity": cx,
                "complexity_engine": eng,
                "churn_norm": round(churn_n, 4),
                "hotspot_score": score,
            }
        )
        out.append(row)
    out.sort(key=lambda r: -float(r.get("hotspot_score") or 0))
    return out
