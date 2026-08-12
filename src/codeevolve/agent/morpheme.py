"""Morpheme analysis — identifier/path morphology linked to CodeEvolve ontology."""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from codeevolve.embeddings import tokenize
from codeevolve.taxonomy.keywords import CODE_TYPE_ONTOLOGY


_CAMEL = re.compile(r"(?<=[a-z])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])")
_SPLIT = re.compile(r"[/\\._\-\s]+")


@dataclass
class Morpheme:
    surface: str
    stem: str
    kind: str  # path | ident | keyword | ontology
    ontology_path: list[str] = field(default_factory=list)
    weight: float = 1.0
    examples: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "surface": self.surface,
            "stem": self.stem,
            "kind": self.kind,
            "ontology_path": list(self.ontology_path),
            "weight": self.weight,
            "examples": list(self.examples)[:6],
        }


def split_morphemes(text: str) -> list[str]:
    """Split identifiers / paths into morphological tokens."""
    parts: list[str] = []
    for piece in _SPLIT.split(text or ""):
        if not piece:
            continue
        camel = _CAMEL.sub(" ", piece)
        for tok in tokenize(camel) or [piece.lower()]:
            t = tok.lower().strip("_")
            if len(t) >= 2:
                parts.append(t)
    return parts


def _walk_ontology(
    node: dict[str, Any],
    token: str,
    path: list[str],
    hits: list[tuple[list[str], float]],
) -> None:
    kws = node.get("_kw") or ()
    if token in kws:
        hits.append((path[:], 1.0 + 0.15 * len(path)))
    for key, child in node.items():
        if key.startswith("_") or not isinstance(child, dict):
            continue
        _walk_ontology(child, token, path + [key], hits)


def match_ontology(token: str) -> list[tuple[list[str], float]]:
    hits: list[tuple[list[str], float]] = []
    for domain, child in CODE_TYPE_ONTOLOGY.items():
        if isinstance(child, dict):
            _walk_ontology(child, token, [domain], hits)
    hits.sort(key=lambda x: -x[1])
    return hits


def extract_morphemes(
    texts: list[str],
    *,
    top_k: int = 40,
) -> list[Morpheme]:
    counts: Counter[str] = Counter()
    examples: dict[str, list[str]] = {}
    for raw in texts:
        for m in split_morphemes(raw):
            counts[m] += 1
            examples.setdefault(m, [])
            if len(examples[m]) < 4 and raw not in examples[m]:
                examples[m].append(raw[:120])

    out: list[Morpheme] = []
    for stem, n in counts.most_common(top_k * 2):
        ont = match_ontology(stem)
        kind = "ontology" if ont else "ident"
        path = list(ont[0][0]) if ont else []
        weight = float(n) * (1.0 + (ont[0][1] if ont else 0.0))
        out.append(
            Morpheme(
                surface=stem,
                stem=stem,
                kind=kind,
                ontology_path=path,
                weight=weight,
                examples=examples.get(stem, []),
            )
        )
    out.sort(key=lambda m: -m.weight)
    return out[:top_k]


def morphemes_from_repo(
    repo: Path | str,
    paths: list[str] | None = None,
    *,
    max_files: int = 80,
) -> dict[str, Any]:
    root = Path(repo)
    texts: list[str] = []
    if paths:
        for p in paths[:max_files]:
            texts.append(p)
            fp = root / p
            if fp.is_file():
                try:
                    body = fp.read_text(encoding="utf-8", errors="replace")[:4000]
                    # pull defs/classes
                    for ln in body.splitlines():
                        if re.match(r"^\s*(def|class|function|export|pub|fn)\s+", ln):
                            texts.append(ln.strip())
                except OSError:
                    pass
    else:
        for p in root.rglob("*"):
            if not p.is_file():
                continue
            rel = p.relative_to(root).as_posix()
            if any(x in rel.split("/") for x in {".git", ".venv", "node_modules", "__pycache__", ".codeevolve"}):
                continue
            if p.suffix.lower() not in {".py", ".ts", ".js", ".go", ".rs", ".java", ".md"}:
                continue
            texts.append(rel)
            if len(texts) >= max_files:
                break

    morphs = extract_morphemes(texts)
    by_domain: dict[str, list[str]] = {}
    for m in morphs:
        if m.ontology_path:
            by_domain.setdefault(m.ontology_path[0], []).append(m.stem)
    return {
        "morpheme_count": len(morphs),
        "morphemes": [m.to_dict() for m in morphs],
        "by_domain": {k: v[:12] for k, v in by_domain.items()},
        "summary": (
            f"{len(morphs)} morphemes; domains="
            + ", ".join(f"{k}:{len(v)}" for k, v in list(by_domain.items())[:8])
        ),
    }
