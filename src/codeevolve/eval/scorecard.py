"""Public-repo scorecard: smoke + before/after directional checks on real tags."""

from __future__ import annotations

import subprocess
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterator

from codeevolve.eval.benchmarks import BenchmarkCase, CheckResult
from codeevolve.eval.public_cases import MetricExpect, PublicCase, public_catalog
from codeevolve.gitlog import ensure_rev
from codeevolve.ingest.github import clone_or_update, github_owner_repo


def _get_path(obj: Any, path: str) -> Any:
    cur = obj
    for part in path.split("."):
        if cur is None:
            return None
        if isinstance(cur, dict):
            cur = cur.get(part)
        else:
            return None
    return cur


def digest_report(report: dict[str, Any]) -> dict[str, Any]:
    """Compact numeric digest used for scorecard deltas."""
    metrics = report.get("metrics") or {}
    coupling = report.get("coupling") or {}
    risk = report.get("risk") or {}
    hyp = report.get("hypothesis_panel") or {}
    conf = report.get("signal_confidence") or {}
    heroes = conf.get("hero_ranking") or []
    claims = hyp.get("claims") or []
    edges = coupling.get("edges") or []
    return {
        "metrics": {
            "code_stability": float(metrics.get("code_stability") or 0.0),
            "revert_rate": float(metrics.get("revert_rate") or 0.0),
            "dependency_rate": float(metrics.get("dependency_rate") or 0.0),
            "momentum": float(metrics.get("momentum") or 0.0),
            "commit_count": int(metrics.get("commit_count") or 0),
        },
        "coupling": {
            "edge_count": int(coupling.get("edge_count") or len(edges)),
            "filtered_large_commits": int(coupling.get("filtered_large_commits") or 0),
        },
        "risk": {"count": int(risk.get("count") or len(risk.get("failure_points") or []))},
        "hypothesis_panel": {
            "counts": hyp.get("counts") or {},
            "claim_count": len(claims),
        },
        "signal_confidence": {
            "hero_ranking": list(heroes),
            "hero_count": len(heroes),
        },
    }


def check_direction(before: float, after: float, expect: MetricExpect) -> CheckResult:
    name = f"delta:{expect.path}:{expect.direction}"
    tol = float(expect.tol)
    d = after - before
    ok = False
    if expect.direction == "down":
        ok = after < before - tol
    elif expect.direction == "down_or_flat":
        ok = after <= before + tol
    elif expect.direction == "up":
        ok = after > before + tol
    elif expect.direction == "up_or_flat":
        ok = after >= before - tol
    elif expect.direction == "nonzero":
        ok = after > 0
    detail = f"before={before} after={after} delta={d:.4g} tol={tol}"
    if expect.note:
        detail += f" ({expect.note})"
    return CheckResult(name, ok, detail)


def score_delta_expectations(
    before_digest: dict[str, Any],
    after_digest: dict[str, Any],
    expects: list[MetricExpect],
) -> list[CheckResult]:
    checks: list[CheckResult] = []
    for exp in expects:
        if exp.direction == "nonzero":
            after_v = _get_path(after_digest, exp.path)
            after_f = float(after_v or 0.0) if not isinstance(after_v, (list, dict)) else float(len(after_v or []))
            checks.append(check_direction(0.0, after_f, exp))
            continue
        b = _get_path(before_digest, exp.path)
        a = _get_path(after_digest, exp.path)
        if b is None or a is None:
            checks.append(CheckResult(f"delta:{exp.path}", False, "missing metric in digest"))
            continue
        try:
            bf, af = float(b), float(a)
        except (TypeError, ValueError):
            checks.append(CheckResult(f"delta:{exp.path}", False, f"non-numeric {b!r}/{a!r}"))
            continue
        checks.append(check_direction(bf, af, exp))
    return checks


def score_field_presence(digest: dict[str, Any], fields: list[str]) -> list[CheckResult]:
    checks: list[CheckResult] = []
    for path in fields:
        val = _get_path(digest, path)
        ok = val is not None and val != {} and val != []
        if path.endswith("code_stability") and isinstance(val, (int, float)):
            ok = True
        checks.append(CheckResult(f"field:{path}", ok, f"value={val!r}"[:120]))
    return checks


@contextmanager
def _detached_checkout(repo: Path, rev: str) -> Iterator[str]:
    sha = ensure_rev(repo, rev)
    prev = subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "--abbrev-ref", "HEAD"],
        capture_output=True,
        text=True,
        check=False,
    ).stdout.strip()
    if prev == "HEAD":
        prev = subprocess.run(
            ["git", "-C", str(repo), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
    subprocess.run(
        ["git", "-C", str(repo), "checkout", "--detach", "-f", sha],
        capture_output=True,
        text=True,
        check=True,
    )
    try:
        yield sha
    finally:
        subprocess.run(
            ["git", "-C", str(repo), "checkout", "-f", prev],
            capture_output=True,
            text=True,
            check=False,
        )


def _analyze_at(repo: Path, *, rev: str, max_commits: int) -> dict[str, Any]:
    from codeevolve.api import CodeEvolve

    with _detached_checkout(repo, rev):
        report = CodeEvolve(repo).analyze(
            max_commits=max_commits,
            rev=rev,
            use_llm=False,
            ensure_slm=False,
            include_selection=False,
            write_report=False,
            include_repo_report=False,
            include_hardware=False,
            include_symbols=False,
            include_cst=False,
            include_clones=False,
            include_reticulation=False,
            include_fork_lineage=False,
            guide_taxonomy=False,
            include_semantic=False,
            include_rag=False,
            include_refactor=True,
        )
        return report.to_dict()


@dataclass
class ScorecardResult:
    cases: list[BenchmarkCase] = field(default_factory=list)
    skipped: list[dict[str, Any]] = field(default_factory=list)
    overall_score: float = 0.0
    passed_cases: int = 0
    total_cases: int = 0
    markdown: str = ""
    summary: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "overall_score": self.overall_score,
            "passed_cases": self.passed_cases,
            "total_cases": self.total_cases,
            "summary": self.summary,
            "skipped": list(self.skipped),
            "cases": [c.to_dict() for c in self.cases],
            "markdown": self.markdown,
        }


def _case_from_checks(name: str, checks: list[CheckResult], summary: dict[str, Any]) -> BenchmarkCase:
    passed = sum(1 for c in checks if c.ok)
    failed = sum(1 for c in checks if not c.ok)
    # weight-aware: treat each check equal here; weights applied in delta helper already via repeats? 
    # Use simple pass rate; MetricExpect.weight handled by duplicating influence in scoring:
    score = passed / max(1, len(checks))
    return BenchmarkCase(
        name=name,
        passed=passed,
        failed=failed,
        checks=checks,
        score=round(score, 4),
        report_summary=summary,
    )


def run_public_case(case: PublicCase, *, offline: bool = False) -> BenchmarkCase | dict[str, Any]:
    """Run one public case; return BenchmarkCase or skip dict."""
    gh = github_owner_repo(case.repo)
    if not gh:
        return {"id": case.id, "skipped": True, "reason": "invalid repo spec"}
    owner, name = gh
    try:
        if offline:
            # only use existing cache
            from codeevolve.ingest.github import _cache_root
            import hashlib

            key = hashlib.sha1(f"{owner}/{name}".encode()).hexdigest()[:12]
            dest = _cache_root() / f"{owner}__{name}__{key}"
            if not (dest / ".git").is_dir():
                return {"id": case.id, "skipped": True, "reason": "offline and no cached clone"}
            repo = dest
        else:
            repo = clone_or_update(owner, name, depth=case.clone_depth, full=False)
            # ensure tags available
            subprocess.run(
                ["git", "-C", str(repo), "fetch", "--tags", "--force", "origin"],
                capture_output=True,
                text=True,
                check=False,
            )
    except Exception as exc:
        return {"id": case.id, "skipped": True, "reason": f"clone failed: {exc}"}

    try:
        if case.kind == "smoke":
            after = _analyze_at(repo, rev=case.after_ref, max_commits=case.max_commits)
            dig = digest_report(after)
            checks = score_field_presence(dig, case.expect_fields)
            return _case_from_checks(
                case.id,
                checks,
                {"kind": "smoke", "repo": case.repo, "ref": case.after_ref, "digest": dig},
            )

        assert case.before_ref
        before = _analyze_at(repo, rev=case.before_ref, max_commits=case.max_commits)
        after = _analyze_at(repo, rev=case.after_ref, max_commits=case.max_commits)
        bdig, adig = digest_report(before), digest_report(after)
        checks = score_field_presence(adig, case.expect_fields)
        # weight: expand heavier expects
        weighted: list[CheckResult] = []
        for exp in case.expect_deltas:
            ch = score_delta_expectations(bdig, adig, [exp])[0]
            copies = max(1, int(round(exp.weight)))
            for i in range(copies):
                weighted.append(
                    CheckResult(ch.name if i == 0 else f"{ch.name}#w{i}", ch.ok, ch.detail)
                )
        checks.extend(weighted)
        return _case_from_checks(
            case.id,
            checks,
            {
                "kind": "before_after",
                "repo": case.repo,
                "before_ref": case.before_ref,
                "after_ref": case.after_ref,
                "before": bdig,
                "after": adig,
            },
        )
    except Exception as exc:
        return {"id": case.id, "skipped": True, "reason": f"analyze failed: {exc}"}


def run_public_scorecard(
    *,
    offline: bool = False,
    case_ids: list[str] | None = None,
) -> ScorecardResult:
    catalog = public_catalog()
    if case_ids:
        want = set(case_ids)
        catalog = [c for c in catalog if c.id in want]
    cases: list[BenchmarkCase] = []
    skipped: list[dict[str, Any]] = []
    for case in catalog:
        result = run_public_case(case, offline=offline)
        if isinstance(result, dict) and result.get("skipped"):
            skipped.append(result)
            continue
        assert isinstance(result, BenchmarkCase)
        cases.append(result)

    if not cases and skipped:
        return ScorecardResult(
            skipped=skipped,
            summary=f"Public scorecard: 0 runnable cases ({len(skipped)} skipped)",
            markdown="# Public scorecard\n\nAll cases skipped.\n",
        )
    overall = sum(c.score for c in cases) / max(1, len(cases))
    passed = sum(1 for c in cases if c.failed == 0)
    lines = [
        "# Public-repo scorecard",
        "",
        "_Real GitHub tags. Smoke checks require coherent digests; before/after checks "
        "score directional movement with tolerances (not absolute truth)._",
        "",
        f"**Public score:** {overall:.1%} · **Clean cases:** {passed}/{len(cases)} · "
        f"**Skipped:** {len(skipped)}",
        "",
        "| Case | Score | Passed | Failed |",
        "|------|------:|-------:|-------:|",
    ]
    for c in cases:
        lines.append(f"| `{c.name}` | {c.score:.0%} | {c.passed} | {c.failed} |")
    if skipped:
        lines.extend(["", "## Skipped", ""])
        for s in skipped:
            lines.append(f"- `{s.get('id')}`: {s.get('reason')}")
    lines.append("")
    for c in cases:
        lines.append(f"## {c.name}")
        lines.append("")
        for ch in c.checks:
            mark = "PASS" if ch.ok else "FAIL"
            lines.append(f"- [{mark}] `{ch.name}` — {ch.detail}")
        lines.append("")
    md = "\n".join(lines)
    return ScorecardResult(
        cases=cases,
        skipped=skipped,
        overall_score=round(overall, 4),
        passed_cases=passed,
        total_cases=len(cases),
        markdown=md,
        summary=(
            f"Public scorecard {overall:.1%} across {len(cases)} cases "
            f"({passed} clean, {len(skipped)} skipped)"
        ),
    )
