"""CodeEvolve CLI."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from codeevolve import __version__
from codeevolve.api import CodeEvolve
from codeevolve.ci import evaluate_ci_gate
from codeevolve.dashboard import write_dashboard
from codeevolve.models.hardware import assess_hardware, recommend_execution
from codeevolve.models.hf_qwen import ensure_hf_qwen
from codeevolve.models.slm import ensure_default_slm
from codeevolve.models.tiers import TIERS, apply_tier_env, tier_spec
from codeevolve.pr_comment import render_pr_comment
from codeevolve.report.diff import diff_reports, load_previous


def _print(obj: object) -> None:
    print(json.dumps(obj, indent=2, default=str))


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        prog="codeevolve",
        description="Evaluate code evolution (SLM-guided taxonomy, drift, fatigue, CI/PR)",
    )
    p.add_argument("--version", action="version", version=f"codeevolve {__version__}")
    p.add_argument("--repo", default=".", help="Local path, GitHub URL, or owner/repo")
    p.add_argument("--depth", type=int, default=200)
    p.add_argument("--full-history", action="store_true")
    p.add_argument("--model-tier", default="slm", choices=list(TIERS.keys()))
    p.add_argument("--model", default=None)
    sub = p.add_subparsers(dest="cmd", required=True)

    an = sub.add_parser("analyze", help="Full analysis + reports")
    an.add_argument("--max-commits", type=int, default=400)
    an.add_argument("--since", default=None)
    an.add_argument("--llm", nargs="?", const="auto", default=None)
    an.add_argument("--out", default=None)
    an.add_argument("--md-out", default=None)
    an.add_argument("--report-out", default=None)
    an.add_argument("--refactor-out", default=None)
    an.add_argument("--dashboard-out", default=None, help="Write HTML clade×drift×fatigue dashboard")
    an.add_argument("--previous", default=None, help="Prior report.json for diff")
    an.add_argument("--diff-out", default=None)
    an.add_argument("--no-report", action="store_true")
    an.add_argument("--no-repo-report", action="store_true")
    an.add_argument("--no-refactor", action="store_true")
    an.add_argument("--no-symbols", action="store_true")
    an.add_argument("--no-selection", action="store_true")
    an.add_argument("--no-taxonomy-guide", action="store_true")
    an.add_argument("--no-ensure-slm", action="store_true")
    an.add_argument("--no-cst", action="store_true")
    an.add_argument("--no-clones", action="store_true")
    an.add_argument("--no-reticulation", action="store_true")
    an.add_argument("--no-fork-lineage", action="store_true")
    an.add_argument("--peer-repo", action="append", default=[], help="Peer repo path for blob lineage")
    an.add_argument("--no-semantic", action="store_true", help="Skip Word2Vec + vector semantic taxonomy")
    an.add_argument(
        "--vector-backend",
        default=None,
        choices=["auto", "memory", "chromadb", "pinecone"],
        help="Semantic taxonomy store (default auto: pinecone→chroma→memory)",
    )

    for name, help_ in (
        ("metrics", "Metrics + stability v2"),
        ("debt", "Technical debt scan"),
        ("phylogeny", "Phylogeny + ecological stage"),
        ("semantics", "Semantic themes"),
        ("taxonomy", "SLM-guided taxonomy"),
        ("word2vec", "Word2Vec over code-evolution corpus"),
        ("semantic-taxonomy", "Chroma/Pinecone semantic niches"),
        ("symbols", "Symbol phylogeny"),
        ("risk", "Failure points"),
        ("fatigue", "Sprint / fatigue trends"),
        ("sprints", "Sprint windows (milestones or weeks)"),
        ("selection", "GitHub Issues/PR selection pressure"),
        ("coupling", "Temporal / ticket change coupling"),
        ("clones", "Clone genealogy patterns"),
        ("dependencies", "Lockfile / dependency fragility"),
        ("offboarding", "Knowledge offboarding simulation"),
        ("report", "Drafted repository report"),
        ("refactor", "Refactor plan"),
        ("tiers", "List model tiers"),
    ):
        sp = sub.add_parser(name, help=help_)
        if name != "tiers":
            sp.add_argument("--max-commits", type=int, default=400)
        if name in {"report", "refactor"}:
            sp.add_argument("--llm", nargs="?", const="auto", default=None)
            sp.add_argument("--md-out", default=None)

    hw = sub.add_parser("hardware", help="Hardware + SLM / taxonomy-embedder probe")
    hw.add_argument("--ensure-hf", action="store_true")
    hw.add_argument("--ensure-slm", action="store_true")
    hw.add_argument("--ensure-embed", action="store_true", help="Ensure MiniLM taxonomy embedder")

    ci = sub.add_parser("ci", help="CI gate against report JSON")
    ci.add_argument("--report", required=True, help="Current report.json")
    ci.add_argument("--previous", default=None)
    ci.add_argument("--min-stability", type=float, default=0.35)
    ci.add_argument("--max-fatigue", type=float, default=0.75)

    cm = sub.add_parser("comment", help="Render GitHub PR comment markdown from report JSON")
    cm.add_argument("--report", required=True)
    cm.add_argument("--previous", default=None)
    cm.add_argument("--out", default=None)

    dash = sub.add_parser("dashboard", help="Build HTML dashboard from report JSON")
    dash.add_argument("--report", required=True)
    dash.add_argument("--out", default="codeevolve_dashboard.html")

    ev = sub.add_parser("evaluate", help="Run synthetic-fixture evaluation suite")
    ev.add_argument("--work-dir", default=None, help="Scratch dir for fixtures (default .codeevolve_eval)")
    ev.add_argument("--out", default=None, help="Write evaluation JSON")
    ev.add_argument("--md-out", default=None, help="Write evaluation markdown")

    args = p.parse_args(argv)

    if args.cmd == "evaluate":
        report = CodeEvolve.evaluate(args.work_dir)
        if args.out:
            Path(args.out).write_text(
                json.dumps(report.to_dict(), indent=2, default=str),
                encoding="utf-8",
            )
        if args.md_out:
            Path(args.md_out).write_text(report.markdown, encoding="utf-8")
        _print(
            {
                "summary": report.summary,
                "overall_score": report.overall_score,
                "passed_cases": report.passed_cases,
                "total_cases": report.total_cases,
                "cases": [
                    {"name": c.name, "score": c.score, "failed": c.failed} for c in report.cases
                ],
            }
        )
        return 0 if report.overall_score >= 0.7 else 1

    if args.cmd == "tiers":
        _print({k: v.to_dict() for k, v in TIERS.items()})
        return 0

    if args.cmd == "hardware":
        apply_tier_env(args.model_tier, model_override=args.model)
        profile = assess_hardware()
        payload: dict = {
            "profile": profile.to_dict(),
            "recommendation": recommend_execution(profile),
            "tier": tier_spec(args.model_tier).to_dict(),
        }
        if args.ensure_hf:
            payload["hf_qwen"] = ensure_hf_qwen(profile.recommended_model)
        if args.ensure_slm:
            payload["slm"] = ensure_default_slm()
        if args.ensure_embed:
            from codeevolve.models.taxonomy_embed import ensure_taxonomy_embedder

            payload["taxonomy_embedder"] = ensure_taxonomy_embedder(download=True).to_dict()
        else:
            from codeevolve.models.taxonomy_embed import ensure_taxonomy_embedder

            payload["taxonomy_embedder"] = ensure_taxonomy_embedder(download=False).to_dict()
        _print(payload)
        return 0

    if args.cmd == "ci":
        cur = json.loads(Path(args.report).read_text(encoding="utf-8"))
        prev = load_previous(args.previous) if args.previous else None
        gate = evaluate_ci_gate(
            cur,
            previous=prev,
            min_stability=args.min_stability,
            max_fatigue=args.max_fatigue,
        )
        _print(gate.to_dict())
        return 0 if gate.ok else 2

    if args.cmd == "comment":
        cur = json.loads(Path(args.report).read_text(encoding="utf-8"))
        prev = load_previous(args.previous) if args.previous else None
        d = diff_reports(cur, prev).to_dict() if prev else None
        md = render_pr_comment(cur, diff=d)
        if args.out:
            Path(args.out).write_text(md, encoding="utf-8")
        else:
            sys.stdout.write(md)
        return 0

    if args.cmd == "dashboard":
        cur = json.loads(Path(args.report).read_text(encoding="utf-8"))
        write_dashboard(cur, args.out)
        print(args.out)
        return 0

    ce = CodeEvolve(
        repo=args.repo,
        clone_depth=args.depth,
        full_history=bool(args.full_history),
        model_tier=args.model_tier,
        model=args.model,
    )
    llm = getattr(args, "llm", None)

    if args.cmd == "analyze":
        use_llm: bool | str | None = None if args.llm is None else args.llm
        report = ce.analyze(
            max_commits=args.max_commits,
            since=args.since,
            write_report=not args.no_report,
            use_llm=use_llm,
            include_repo_report=not args.no_repo_report,
            include_refactor=not args.no_refactor,
            include_symbols=not args.no_symbols,
            include_selection=not args.no_selection,
            include_cst=not args.no_cst,
            include_clones=not args.no_clones,
            include_reticulation=not args.no_reticulation,
            include_fork_lineage=not args.no_fork_lineage,
            peer_repos=args.peer_repo or None,
            guide_taxonomy=not args.no_taxonomy_guide,
            include_semantic=not args.no_semantic,
            vector_backend=args.vector_backend,
            previous_report=args.previous,
            ensure_slm=not args.no_ensure_slm,
        )
        data = report.to_dict()
        if args.out:
            Path(args.out).write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
        if args.md_out and report.trend:
            Path(args.md_out).write_text(report.trend.markdown, encoding="utf-8")
        if args.report_out and report.repo_report:
            Path(args.report_out).write_text(report.repo_report.markdown, encoding="utf-8")
        if args.refactor_out and report.refactor_plan:
            Path(args.refactor_out).write_text(report.refactor_plan.markdown, encoding="utf-8")
        if args.diff_out and report.diff:
            Path(args.diff_out).write_text(report.diff.markdown, encoding="utf-8")
        if args.dashboard_out:
            write_dashboard(data, args.dashboard_out)
        if report.repo_report and not args.out and not args.report_out:
            print(report.repo_report.markdown)
            print("\n---\n")
        _print(
            {
                "repo": report.repo,
                "model_tier": report.model_tier,
                "taxonomy_guidance": report.taxonomy.guidance,
                "commit_count": report.commit_count,
                "stage": report.ecology.global_stage,
                "stability": report.stability.to_dict() if report.stability else None,
                "fatigue": report.fatigue.fatigue_score if report.fatigue else None,
                "drift": report.drift.global_drift if report.drift else None,
                "alleles": (report.drift.alleles or {}).get("mutant_count") if report.drift else None,
                "coupling_edges": report.coupling.edges.__len__() if report.coupling else 0,
                "clone_patterns": (report.clones.pattern_counts if report.clones else None),
                "dep_fragility": report.dependencies.fragility if report.dependencies else None,
                "offboarding_drop": report.offboarding.mastery_drop_top1 if report.offboarding else None,
                "selection": report.selection.pressure_score if report.selection else None,
                "sprints": report.sprints.source if report.sprints else None,
                "debt_score": report.debt.score,
                "failure_points": len(report.risk.failure_points),
                "remediation_days": sum(
                    (s.estimated_person_days for s in (report.refactor_plan.steps if report.refactor_plan else [])),
                    0.0,
                ),
                "hero_signals": report.signal_confidence.hero_ranking if report.signal_confidence else None,
                "hypotheses": (report.hypothesis_panel.to_dict().get("counts") if report.hypothesis_panel else None),
                "semantic_backend": (report.taxonomy.semantic or {}).get("backend") if report.taxonomy.semantic else None,
                "word2vec_engine": (report.taxonomy.word2vec or {}).get("engine") if report.taxonomy.word2vec else None,
                "diff": bool(report.diff),
            }
        )
        return 0

    report = ce.analyze(
        max_commits=getattr(args, "max_commits", 400),
        write_report=args.cmd in {"report"},
        use_llm=llm if llm is not None else False,
        include_repo_report=args.cmd in {"report", "refactor"},
        include_refactor=args.cmd == "refactor",
        include_hardware=False,
        include_symbols=args.cmd in {"symbols", "taxonomy", "report", "clones"},
        include_selection=args.cmd in {"selection", "risk", "report", "refactor", "sprints"},
        include_cst=args.cmd in {"report"},
        include_clones=args.cmd in {"clones", "report", "risk"},
        include_reticulation=args.cmd in {"report"},
        include_fork_lineage=args.cmd in {"report"},
        include_semantic=args.cmd in {"taxonomy", "word2vec", "semantic-taxonomy", "report"},
        ensure_slm=False,
    )

    if args.cmd == "metrics":
        _print({"metrics": report.metrics.to_dict(), "stability": report.stability.to_dict() if report.stability else None})
    elif args.cmd == "debt":
        _print(report.debt.to_dict())
    elif args.cmd == "phylogeny":
        _print(report.phylogeny.to_dict())
    elif args.cmd == "semantics":
        _print(report.semantics.to_dict())
    elif args.cmd == "taxonomy":
        _print(report.taxonomy.to_dict())
    elif args.cmd == "word2vec":
        _print(report.taxonomy.word2vec or {})
    elif args.cmd == "semantic-taxonomy":
        _print(report.taxonomy.semantic or {})
    elif args.cmd == "symbols":
        _print(report.symbols.to_dict() if report.symbols else {})
    elif args.cmd == "risk":
        _print(report.risk.to_dict())
    elif args.cmd == "fatigue":
        _print(report.fatigue.to_dict() if report.fatigue else {})
    elif args.cmd == "sprints":
        _print(report.sprints.to_dict() if report.sprints else {})
    elif args.cmd == "coupling":
        _print(report.coupling.to_dict() if report.coupling else {})
    elif args.cmd == "clones":
        _print(report.clones.to_dict() if report.clones else {})
    elif args.cmd == "dependencies":
        _print(report.dependencies.to_dict() if report.dependencies else {})
    elif args.cmd == "offboarding":
        _print(report.offboarding.to_dict() if report.offboarding else {})
    elif args.cmd == "selection":
        _print(report.selection.to_dict() if report.selection else {"notes": ["not a GitHub repo spec"]})
    elif args.cmd == "report":
        assert report.repo_report
        md_out = getattr(args, "md_out", None)
        if md_out:
            Path(md_out).write_text(report.repo_report.markdown, encoding="utf-8")
        else:
            print(report.repo_report.markdown)
    elif args.cmd == "refactor":
        if not report.refactor_plan:
            from codeevolve.refactor import build_refactor_plan

            report.refactor_plan = build_refactor_plan(report.risk, report.debt)
        md_out = getattr(args, "md_out", None)
        if md_out:
            Path(md_out).write_text(report.refactor_plan.markdown, encoding="utf-8")
        else:
            print(report.refactor_plan.markdown)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
