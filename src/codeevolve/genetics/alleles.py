"""Near-duplicate symbol 'allele' divergence (clone genetic drift)."""

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

from codeevolve.embeddings import cosine, embed_text
from codeevolve.taxonomy.symbols import SymbolNode, SymbolReport


@dataclass
class AlleleDriftReport:
    pairs: list[dict[str, Any]] = field(default_factory=list)
    mutant_count: int = 0
    mean_divergence: float = 0.0
    summary: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "pairs": list(self.pairs[:40]),
            "mutant_count": self.mutant_count,
            "mean_divergence": self.mean_divergence,
            "summary": self.summary,
        }


_STEM = re.compile(r"([A-Za-z]+)[\d_]*$")


def _stem(name: str) -> str:
    base = name.split("::")[-1]
    # strip common prefixes/suffixes noise
    base = re.sub(r"^(get|set|is|has|load|save|parse|format)_?", "", base, flags=re.I)
    m = _STEM.match(base)
    return (m.group(1) if m else base).lower()


def analyze_allele_drift(symbols: SymbolReport, *, min_name_len: int = 4) -> AlleleDriftReport:
    groups: dict[str, list[SymbolNode]] = defaultdict(list)
    for s in symbols.symbols:
        short = s.qualname.split("::")[-1]
        if len(short) < min_name_len:
            continue
        groups[_stem(short)].append(s)

    pairs: list[dict[str, Any]] = []
    for stem, nodes in groups.items():
        if len(nodes) < 2 or len(nodes) > 12:
            continue
        # compare embeddings of qualnames + kind
        for i, a in enumerate(nodes):
            ea = embed_text(f"{a.kind} {a.qualname}")
            for b in nodes[i + 1 :]:
                if a.path == b.path:
                    continue
                eb = embed_text(f"{b.kind} {b.qualname}")
                sim = cosine(ea, eb)
                # same stem but different paths → potential mutant if not identical name
                div = 1.0 - sim
                if a.qualname.split("::")[-1] == b.qualname.split("::")[-1]:
                    # exact name clone across files
                    kind = "exact_clone"
                    score = max(div, 0.35)
                else:
                    kind = "mutant_allele"
                    score = div
                if score < 0.15 and kind != "exact_clone":
                    continue
                pairs.append(
                    {
                        "stem": stem,
                        "kind": kind,
                        "a": a.qualname,
                        "b": b.qualname,
                        "divergence": round(score, 4),
                        "similarity": round(sim, 4),
                    }
                )

    pairs.sort(key=lambda x: -x["divergence"])
    mutants = [p for p in pairs if p["kind"] == "mutant_allele"]
    mean_div = sum(p["divergence"] for p in pairs) / len(pairs) if pairs else 0.0
    summary = (
        f"{len(pairs)} allele pairs ({len(mutants)} mutants); "
        f"mean_divergence={mean_div:.2f}"
    )
    return AlleleDriftReport(
        pairs=pairs[:40],
        mutant_count=len(mutants),
        mean_divergence=round(mean_div, 4),
        summary=summary,
    )
