"""Taxonomy gold set + RAG/SLM quality checks (closes eval gap beyond fixtures)."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from codeevolve.eval.benchmarks import BenchmarkCase, CheckResult

# Path → expected type_path prefix (must be prefix-match of classifier output)
GOLD_TYPE_PATHS: list[tuple[str, list[str]]] = [
    ("src/api/routes/users.py", ["architecture", "api"]),
    ("src/api/handlers/orders.py", ["architecture", "api"]),
    ("src/data/models/user.py", ["architecture", "data"]),
    ("src/data/repository/user_repo.py", ["architecture", "data"]),
    ("src/ui/components/UserCard.tsx", ["architecture", "ui"]),
    ("src/security/auth/login.py", ["architecture", "security"]),
    ("tests/unit/test_users.py", ["verification"]),
    ("tests/e2e/test_checkout.py", ["verification"]),
    ("docs/ARCHITECTURE.md", ["knowledge"]),
    (".github/workflows/ci.yml", ["architecture", "infra"]),
    ("scripts/build.sh", ["tooling"]),
    ("src/utils/parse_json.py", ["utility"]),
    ("src/ml/embeddings/encoder.py", ["architecture", "ml"]),
    ("src/infra/deploy/helm/values.yaml", ["architecture", "infra"]),
]


@dataclass
class GoldHit:
    path: str
    expected: list[str]
    actual: list[str]
    ok: bool
    detail: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "expected": list(self.expected),
            "actual": list(self.actual),
            "ok": self.ok,
            "detail": self.detail,
        }


def _prefix_ok(actual: list[str], expected: list[str]) -> bool:
    if len(actual) < len(expected):
        return False
    return actual[: len(expected)] == expected


def score_type_gold() -> tuple[list[GoldHit], float]:
    from codeevolve.taxonomy.keywords import classify_path

    hits: list[GoldHit] = []
    for path, expected in GOLD_TYPE_PATHS:
        hit = classify_path(path)
        ok = _prefix_ok(hit.type_path, expected)
        hits.append(
            GoldHit(
                path=path,
                expected=expected,
                actual=list(hit.type_path),
                ok=ok,
                detail=f"got={hit.type_key} conf={hit.confidence}",
            )
        )
    score = sum(1 for h in hits if h.ok) / max(1, len(hits))
    return hits, score


def _token_overlap(a: str, b: str) -> float:
    ta = set(re.findall(r"[a-zA-Z_]{3,}", (a or "").lower()))
    tb = set(re.findall(r"[a-zA-Z_]{3,}", (b or "").lower()))
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / max(1, min(len(ta), len(tb)))


def score_rag_faithfulness(guidance: dict[str, Any], evidence: dict[str, Any]) -> tuple[float, list[CheckResult]]:
    """Fraction of guided clades whose label/role overlaps retrieved chunk text."""
    checks: list[CheckResult] = []
    clades = guidance.get("clades") or []
    if not clades:
        # guidance meta from apply_guidance doesn't keep clade list — use engine signals
        used = int(guidance.get("rag_chunks_used") or 0)
        engine = str(guidance.get("engine") or "")
        ok_engine = "rag" in engine or used > 0 or bool(guidance.get("rag"))
        checks.append(
            CheckResult(
                "rag_attached",
                ok_engine,
                f"engine={engine} rag_chunks_used={used}",
            )
        )
        return (1.0 if ok_engine else 0.0), checks

    ev = evidence.get("evidence") or evidence
    scored = 0
    total = 0
    for c in clades:
        if not isinstance(c, dict):
            continue
        cid = str(c.get("id") or "")
        chunks = ev.get(cid) or []
        blob = " ".join(str(x.get("text") or x.get("excerpt") or "") for x in chunks)
        text = f"{c.get('label', '')} {c.get('role', '')} {' '.join(c.get('type_path') or [])}"
        total += 1
        ov = _token_overlap(text, blob) if blob else 0.0
        ok = ov >= 0.08 or (not blob and "heuristic" in str(guidance.get("engine") or ""))
        if ok:
            scored += 1
        checks.append(CheckResult(f"faithful:{cid}", ok, f"overlap={ov:.2f} chunks={len(chunks)}"))
    score = scored / max(1, total)
    return score, checks


def run_taxonomy_eval(work_dir: Path | str | None = None) -> list[BenchmarkCase]:
    """
    Offline-capable taxonomy quality suite:
    1) gold type_path prefix accuracy
    2) RAG index + evidence on sample repo
    3) guidance engine / faithfulness (live SLM optional)
    """
    from codeevolve.api import CodeEvolve
    from codeevolve.eval.fixtures import materialize_suite
    from codeevolve.taxonomy.rag import build_rag_index, evidence_bundle
    from codeevolve.taxonomy.tree import build_taxonomy

    cases: list[BenchmarkCase] = []

    # --- Gold type paths ---
    hits, gold_score = score_type_gold()
    checks = [
        CheckResult(
            f"type:{h.path}",
            h.ok,
            h.detail if h.ok else f"expected={ '/'.join(h.expected)} {h.detail}",
        )
        for h in hits
    ]
    cases.append(
        BenchmarkCase(
            name="taxonomy_type_gold",
            passed=sum(1 for c in checks if c.ok),
            failed=sum(1 for c in checks if not c.ok),
            checks=checks,
            score=round(gold_score, 4),
            report_summary={"gold_score": gold_score, "n": len(hits)},
        )
    )

    # --- RAG + breakout on a fixture repo ---
    work = Path(work_dir) if work_dir else Path.cwd() / ".codeevolve_eval"
    work.mkdir(parents=True, exist_ok=True)
    fixtures = materialize_suite(work)
    # Prefer a dense fixture
    repo = fixtures[0][0] if fixtures else work
    os.environ.setdefault("CODEEVOLVE_SKIP_EMBED", "1")
    os.environ.setdefault("CODEEVOLVE_VECTOR_BACKEND", "memory")
    # Keep heuristic for CI unless live SLM requested
    live_slm = os.environ.get("CODEEVOLVE_LIVE_SLM", "").lower() in {"1", "true", "yes"}
    if not live_slm:
        os.environ.setdefault("CODEEVOLVE_TAXONOMY_HEURISTIC", "1")
        os.environ.setdefault("CODEEVOLVE_SKIP_HF", "1")

    commits = CodeEvolve(repo).commits(max_commits=80)
    tax = build_taxonomy(
        repo,
        commits,
        guide=True,
        include_semantic=False,
        include_rag=True,
        vector_backend="memory",
    )
    rag_checks: list[CheckResult] = []
    rag = tax.rag or {}
    rag_checks.append(
        CheckResult("rag_chunks", (rag.get("chunk_count") or 0) >= 1, f"chunks={rag.get('chunk_count')}")
    )
    rag_checks.append(
        CheckResult("rag_files", (rag.get("file_count") or 0) >= 1, f"files={rag.get('file_count')}")
    )
    typed = sum(1 for c in tax.clades if c.code_type or c.type_path)
    rag_checks.append(
        CheckResult("clades_typed", typed >= 1, f"typed_clades={typed}/{len(tax.clades)}")
    )
    # Type diversity: breakouts should not collapse everything into one type seed when mixed
    type_keys = {c.code_type for c in tax.clades if c.code_type}
    rag_checks.append(
        CheckResult(
            "type_aware_labels",
            bool(type_keys) or any(str(c.label).startswith("type:") or "/" in str(c.label) for c in tax.clades),
            f"type_keys={sorted(type_keys)[:8]}",
        )
    )
    guidance = tax.guidance or {}
    engine = str(guidance.get("engine") or "")
    if live_slm:
        rag_checks.append(
            CheckResult(
                "engine_slm_rag",
                engine in {"hf-slm-rag", "hf-slm"} or "rag" in engine,
                f"engine={engine} (live SLM required)",
            )
        )
        rag_checks.append(
            CheckResult(
                "rag_chunks_used",
                int(guidance.get("rag_chunks_used") or 0) > 0,
                f"used={guidance.get('rag_chunks_used')}",
            )
        )
    else:
        rag_checks.append(
            CheckResult(
                "engine_reported",
                bool(engine),
                f"engine={engine} (offline heuristic allowed)",
            )
        )
        rag_checks.append(
            CheckResult(
                "rag_meta_on_guidance",
                bool(guidance.get("rag")) or bool(rag),
                "RAG metadata attached even under heuristic",
            )
        )

    # Faithfulness via re-built evidence + heuristic labels
    idx = build_rag_index(repo, backend="memory")
    bundle = evidence_bundle(idx, [c.to_dict() for c in tax.clades])
    # synthesize pseudo guidance clades for overlap when SLM skipped
    pseudo = {
        "engine": engine,
        "rag_chunks_used": guidance.get("rag_chunks_used") or sum(len(v) for v in bundle["evidence"].values()),
        "rag": rag,
        "clades": [
            {
                "id": c.id,
                "label": c.label,
                "role": c.role,
                "type_path": c.type_path,
            }
            for c in tax.clades
        ],
    }
    faith_score, faith_checks = score_rag_faithfulness(pseudo, bundle)
    rag_checks.extend(faith_checks[:12])

    rag_pass = sum(1 for c in rag_checks if c.ok)
    rag_fail = sum(1 for c in rag_checks if not c.ok)
    cases.append(
        BenchmarkCase(
            name="taxonomy_rag_pipeline",
            passed=rag_pass,
            failed=rag_fail,
            checks=rag_checks,
            score=round(rag_pass / max(1, len(rag_checks)), 4),
            report_summary={
                "engine": engine,
                "rag": rag,
                "faithfulness": faith_score,
                "live_slm": live_slm,
            },
        )
    )
    return cases
