"""CodeEvolve CLI."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from codeevolve import __version__
from codeevolve.api import CodeEvolve


def _print(obj: object) -> None:
    print(json.dumps(obj, indent=2, default=str))


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        prog="codeevolve",
        description="Evaluate code evolution from git history (stability, debt, phylogeny, trends)",
    )
    p.add_argument("--version", action="version", version=f"codeevolve {__version__}")
    p.add_argument("--repo", default=".", help="Path to git repository")
    sub = p.add_subparsers(dest="cmd", required=True)

    an = sub.add_parser("analyze", help="Full MVP analysis + trend report")
    an.add_argument("--max-commits", type=int, default=400)
    an.add_argument("--since", default=None, help="git --since value, e.g. 90.days")
    an.add_argument("--llm", action="store_true", help="Use cloud/SLM backend for narrative report")
    an.add_argument("--out", default=None, help="Write full JSON report to path")
    an.add_argument("--md-out", default=None, help="Write markdown trend report to path")
    an.add_argument("--no-report", action="store_true")

    m = sub.add_parser("metrics", help="Metrics only")
    m.add_argument("--max-commits", type=int, default=400)

    d = sub.add_parser("debt", help="Technical debt / deprecation scan")
    d.add_argument("--max-commits", type=int, default=200)

    ph = sub.add_parser("phylogeny", help="Phylogeny + ecological stage")
    ph.add_argument("--max-commits", type=int, default=400)

    sm = sub.add_parser("semantics", help="Semantic themes + hierarchy taxonomy")
    sm.add_argument("--max-commits", type=int, default=400)

    args = p.parse_args(argv)
    ce = CodeEvolve(repo=args.repo)

    if args.cmd == "analyze":
        report = ce.analyze(
            max_commits=args.max_commits,
            since=args.since,
            write_report=not args.no_report,
            use_llm=bool(args.llm),
        )
        data = report.to_dict()
        if args.out:
            Path(args.out).write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
        if args.md_out and report.trend:
            Path(args.md_out).write_text(report.trend.markdown, encoding="utf-8")
        if report.trend and not args.out:
            print(report.trend.markdown)
            print("\n---\n")
        _print(
            {
                "repo": report.repo,
                "commit_count": report.commit_count,
                "metrics": report.metrics.to_dict(),
                "stage": report.phylogeny.current_stage,
                "debt_score": report.debt.score,
                "priorities": report.trend.bullets if report.trend else [],
            }
        )
        return 0
    if args.cmd == "metrics":
        commits = ce.commits(max_commits=args.max_commits)
        from codeevolve.metrics import compute_metrics

        _print(compute_metrics(commits).to_dict())
        return 0
    if args.cmd == "debt":
        report = ce.analyze(max_commits=args.max_commits, write_report=False)
        _print(report.debt.to_dict())
        return 0
    if args.cmd == "phylogeny":
        report = ce.analyze(max_commits=args.max_commits, write_report=False)
        _print(report.phylogeny.to_dict())
        return 0
    if args.cmd == "semantics":
        report = ce.analyze(max_commits=args.max_commits, write_report=False)
        _print(report.semantics.to_dict())
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
