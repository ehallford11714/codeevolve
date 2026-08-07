"""CodeEvolve CLI."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from codeevolve import __version__
from codeevolve.api import CodeEvolve
from codeevolve.models.hardware import assess_hardware, recommend_execution
from codeevolve.models.hf_qwen import ensure_hf_qwen
from codeevolve.models.tiers import TIERS, apply_tier_env, tier_spec


def _print(obj: object) -> None:
    print(json.dumps(obj, indent=2, default=str))


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        prog="codeevolve",
        description="Evaluate code evolution from git history (SLM-guided taxonomy, debt, refactor plans)",
    )
    p.add_argument("--version", action="version", version=f"codeevolve {__version__}")
    p.add_argument("--repo", default=".", help="Local path, GitHub URL, or owner/repo")
    p.add_argument("--depth", type=int, default=200, help="Shallow clone depth for GitHub repos")
    p.add_argument("--full-history", action="store_true", help="Full clone (no --depth)")
    p.add_argument(
        "--model-tier",
        default="slm",
        choices=list(TIERS.keys()),
        help="Model tier (default: slm). Swap up: standard|large|frontier for sharper studies",
    )
    p.add_argument("--model", default=None, help="Override HF/cloud model id for this run")
    sub = p.add_subparsers(dest="cmd", required=True)

    an = sub.add_parser("analyze", help="Full analysis + reports")
    an.add_argument("--max-commits", type=int, default=400)
    an.add_argument("--since", default=None)
    an.add_argument(
        "--llm",
        nargs="?",
        const="auto",
        default=None,
        help="Narrative backend override: auto|hf-qwen|openai|anthropic|heuristic (default follows --model-tier)",
    )
    an.add_argument("--out", default=None)
    an.add_argument("--md-out", default=None)
    an.add_argument("--report-out", default=None)
    an.add_argument("--refactor-out", default=None)
    an.add_argument("--no-report", action="store_true")
    an.add_argument("--no-repo-report", action="store_true")
    an.add_argument("--no-refactor", action="store_true")
    an.add_argument("--no-symbols", action="store_true")
    an.add_argument("--no-selection", action="store_true")
    an.add_argument("--no-taxonomy-guide", action="store_true", help="Skip SLM taxonomy guidance")

    for name, help_ in (
        ("metrics", "Metrics only"),
        ("debt", "Technical debt scan"),
        ("phylogeny", "Phylogeny + ecological stage"),
        ("semantics", "Semantic themes + hierarchy"),
        ("taxonomy", "Full taxonomy + SLM-guided clades"),
        ("symbols", "Symbol phylogeny (regex)"),
        ("risk", "Weakness / failure points"),
        ("fatigue", "Sprint / fatigue trends"),
        ("selection", "GitHub Issues/PR selection pressure"),
        ("report", "Drafted repository report"),
        ("refactor", "Evidence-linked refactor plan"),
        ("tiers", "List model tiers"),
    ):
        sp = sub.add_parser(name, help=help_)
        if name != "tiers":
            sp.add_argument("--max-commits", type=int, default=400)
        if name in {"report", "refactor"}:
            sp.add_argument("--llm", nargs="?", const="auto", default=None)
            sp.add_argument("--md-out", default=None)

    hw = sub.add_parser("hardware", help="Hardware profile + Qwen/cloud recommendation")
    hw.add_argument("--ensure-hf", action="store_true", help="Probe HF Qwen availability")

    args = p.parse_args(argv)

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
        _print(payload)
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
            guide_taxonomy=not args.no_taxonomy_guide,
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
                "debt_score": report.debt.score,
                "failure_points": len(report.risk.failure_points),
                "refactor_steps": len(report.refactor_plan.steps) if report.refactor_plan else 0,
            }
        )
        return 0

    report = ce.analyze(
        max_commits=getattr(args, "max_commits", 400),
        write_report=args.cmd in {"report"},
        use_llm=llm if llm is not None else None,
        include_repo_report=args.cmd in {"report", "refactor"},
        include_refactor=args.cmd == "refactor",
        include_hardware=False,
        include_symbols=args.cmd in {"symbols", "taxonomy", "report"},
        include_selection=args.cmd in {"selection", "risk", "report", "refactor"},
    )

    if args.cmd == "metrics":
        _print(
            {
                "metrics": report.metrics.to_dict(),
                "stability": report.stability.to_dict() if report.stability else None,
            }
        )
    elif args.cmd == "debt":
        _print(report.debt.to_dict())
    elif args.cmd == "phylogeny":
        _print(report.phylogeny.to_dict())
    elif args.cmd == "semantics":
        _print(report.semantics.to_dict())
    elif args.cmd == "taxonomy":
        _print(report.taxonomy.to_dict())
    elif args.cmd == "symbols":
        _print(report.symbols.to_dict() if report.symbols else {})
    elif args.cmd == "risk":
        _print(report.risk.to_dict())
    elif args.cmd == "fatigue":
        _print(report.fatigue.to_dict() if report.fatigue else {})
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
