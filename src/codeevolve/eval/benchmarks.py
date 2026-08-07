"""Score analyzer outputs against fixture ground truth."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from codeevolve.eval.fixtures import FixtureSpec, build_decouple_after, build_decouple_before, materialize_suite


@dataclass
class CheckResult:
    name: str
    ok: bool
    detail: str

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "ok": self.ok, "detail": self.detail}


@dataclass
class BenchmarkCase:
    name: str
    passed: int
    failed: int
    checks: list[CheckResult] = field(default_factory=list)
    score: float = 0.0
    report_summary: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "passed": self.passed,
            "failed": self.failed,
            "score": self.score,
            "checks": [c.to_dict() for c in self.checks],
            "report_summary": self.report_summary,
        }


def _pair_match(edges: list[dict[str, Any]], a: str, b: str) -> bool:
    for e in edges:
        ea, eb = e.get("a"), e.get("b")
        if {ea, eb} == {a, b}:
            return True
    return False


def score_case(repo: Path, spec: FixtureSpec) -> BenchmarkCase:
    from codeevolve.api import CodeEvolve

    report = CodeEvolve(repo).analyze(
        use_llm=False,
        ensure_slm=False,
        include_selection=False,
        write_report=False,
        include_repo_report=False,
        include_hardware=False,
        include_cst=False,
        include_reticulation=False,
        include_fork_lineage=False,
        guide_taxonomy=False,
    )
    d = report.to_dict()
    kinds = {fp["kind"] for fp in (d.get("risk") or {}).get("failure_points") or []}
    hot_paths = [h.get("path") for h in (d.get("metrics") or {}).get("hot_files") or []]
    edges = (d.get("coupling") or {}).get("edges") or []
    checks: list[CheckResult] = []

    for kind in spec.expect_kinds:
        ok = kind in kinds
        checks.append(CheckResult(f"kind:{kind}", ok, "found" if ok else f"missing; have={sorted(kinds)}"))

    for kind in spec.forbid_kinds:
        ok = kind not in kinds
        checks.append(CheckResult(f"forbid:{kind}", ok, "absent" if ok else "incorrectly present"))

    if spec.expect_hot_paths:
        ok = any(p in hot_paths[:8] for p in spec.expect_hot_paths)
        checks.append(
            CheckResult(
                "hot_paths",
                ok,
                f"expected one of {spec.expect_hot_paths} in {hot_paths[:8]}",
            )
        )

    if spec.expect_coupling_pair:
        a, b = spec.expect_coupling_pair
        ok = _pair_match(edges, a, b)
        checks.append(CheckResult("coupling_pair", ok, f"{a}↔{b} in edges={ok}"))

    if spec.expect_min_offboarding_drop is not None:
        drop = float(((d.get("offboarding") or {}).get("mastery_drop_top1")) or 0.0)
        ok = drop >= spec.expect_min_offboarding_drop
        checks.append(
            CheckResult(
                "offboarding_drop",
                ok,
                f"drop={drop} threshold={spec.expect_min_offboarding_drop}",
            )
        )

    if spec.expect_stability_range:
        lo, hi = spec.expect_stability_range
        stab = float(((d.get("metrics") or {}).get("code_stability")) or 0.0)
        ok = lo <= stab <= hi
        checks.append(CheckResult("stability_range", ok, f"stability={stab} in [{lo},{hi}]"))

    # Hypothesis panel present + disclaimer
    panel = d.get("hypothesis_panel") or {}
    disc = (panel.get("disclaimer") or "").lower()
    panel_ok = bool(panel.get("claims")) and (
        "not laws" in disc or "hypothes" in disc or "not a grade" in disc
    )
    checks.append(
        CheckResult(
            "hypothesis_panel",
            panel_ok,
            panel.get("summary") or "missing panel",
        )
    )
    # Hero confidence present
    conf = d.get("signal_confidence") or {}
    checks.append(
        CheckResult(
            "signal_confidence",
            bool(conf.get("hero_ranking")),
            conf.get("summary") or "missing confidence",
        )
    )

    passed = sum(1 for c in checks if c.ok)
    failed = sum(1 for c in checks if not c.ok)
    score = passed / max(1, len(checks))
    return BenchmarkCase(
        name=spec.name,
        passed=passed,
        failed=failed,
        checks=checks,
        score=round(score, 4),
        report_summary={
            "kinds": sorted(kinds),
            "hot_paths": hot_paths[:5],
            "offboarding": (d.get("offboarding") or {}).get("mastery_drop_top1"),
            "stability": (d.get("metrics") or {}).get("code_stability"),
            "hero_ranking": conf.get("hero_ranking"),
        },
    )


def score_before_after(root: Path) -> BenchmarkCase:
    """Coupling should drop after isolating changes."""
    from codeevolve.api import CodeEvolve

    before = build_decouple_before(root)
    after = build_decouple_after(root)
    rb = CodeEvolve(before).analyze(
        use_llm=False,
        ensure_slm=False,
        include_selection=False,
        write_report=False,
        include_repo_report=False,
        include_hardware=False,
        include_cst=False,
        include_clones=False,
        include_reticulation=False,
        include_fork_lineage=False,
        guide_taxonomy=False,
    )
    ra = CodeEvolve(after).analyze(
        use_llm=False,
        ensure_slm=False,
        include_selection=False,
        write_report=False,
        include_repo_report=False,
        include_hardware=False,
        include_cst=False,
        include_clones=False,
        include_reticulation=False,
        include_fork_lineage=False,
        guide_taxonomy=False,
    )
    eb = len((rb.coupling.edges if rb.coupling else []) or [])
    ea = len((ra.coupling.edges if ra.coupling else []) or [])
    # weight on a↔b specifically
    def pair_w(rep: Any) -> int:
        if not rep.coupling:
            return 0
        for e in rep.coupling.edges:
            if {e.a, e.b} == {"src/a.py", "src/b.py"}:
                return e.weight
        return 0

    wb, wa = pair_w(rb), pair_w(ra)
    ok = wa < wb or (wb > 0 and wa == 0)
    checks = [
        CheckResult("coupling_edges_drop", ea <= eb, f"before_edges={eb} after_edges={ea}"),
        CheckResult("pair_weight_drop", ok, f"before_w={wb} after_w={wa}"),
    ]
    passed = sum(1 for c in checks if c.ok)
    return BenchmarkCase(
        name="decouple_before_after",
        passed=passed,
        failed=len(checks) - passed,
        checks=checks,
        score=round(passed / len(checks), 4),
        report_summary={"before_edges": eb, "after_edges": ea, "before_w": wb, "after_w": wa},
    )


def run_benchmark_suite(work_dir: Path | str) -> list[BenchmarkCase]:
    work = Path(work_dir)
    suite = materialize_suite(work / "fixtures")
    cases = [score_case(path, spec) for path, spec in suite]
    cases.append(score_before_after(work / "fixtures"))
    return cases
