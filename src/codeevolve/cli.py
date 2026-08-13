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
    an.add_argument(
        "--viz-out",
        default=None,
        help="Write phylogeny/clade/parsimony gallery (HTML file or directory)",
    )
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
    an.add_argument("--no-rag", action="store_true", help="Skip codebase chunking / RAG evidence for SLM taxonomy")
    an.add_argument(
        "--vector-backend",
        default=None,
        choices=["auto", "memory", "chromadb", "pinecone"],
        help="Vector store for RAG + semantic taxonomy (default auto: pinecone→chroma→memory)",
    )

    for name, help_ in (
        ("metrics", "Metrics + stability v2"),
        ("debt", "Technical debt scan"),
        ("phylogeny", "Phylogeny + ecological stage"),
        ("semantics", "Semantic themes"),
        ("taxonomy", "SLM-guided taxonomy"),
        ("hierarchy", "Deep nested build hierarchy + ecological trend report"),
        ("provenance", "Unified provenance ledger for deliberation"),
        ("keyword-taxonomy", "Keyword code-type ontology + path classifications"),
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
        if name in {"report", "refactor", "hierarchy"}:
            if name != "hierarchy":
                sp.add_argument("--llm", nargs="?", const="auto", default=None)
            sp.add_argument("--md-out", default=None)
        if name == "provenance":
            sp.add_argument("--path", default=None, help="Filter records by path prefix/substring")
            sp.add_argument("--clade", default=None, help="Filter by clade id")
            sp.add_argument("--kind", default=None, help="Record kind (lineage|event|hypothesis|...)")
            sp.add_argument("--tag", default=None)
            sp.add_argument("--since", default=None, help="ISO lower bound on record.when")
            sp.add_argument("--until", default=None)
            sp.add_argument("--pack", action="store_true", help="Emit deliberation pack (frames+evidence)")
            sp.add_argument("--path-pack", dest="path_pack", default=None, help="Path-centric provenance pack")
            sp.add_argument("--timeline", action="store_true", help="Chronological provenance slice")
            sp.add_argument("--resolve", default=None, help="Walk evidence chain from record/frame id")
            sp.add_argument("--frame", default=None, help="Expand a deliberation frame with evidence")
            sp.add_argument("--depth", type=int, default=2, help="Resolve chain depth")
            sp.add_argument("--out", default=None, help="Write JSON")
            sp.add_argument("--from-report", default=None, help="Build ledger from existing report.json")
            sp.add_argument("--schema", action="store_true", help="Emit JSON Schema + MCP tool descriptors")
            sp.add_argument("--schema-out", default=None, help="Write schema files to directory")

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

    vz = sub.add_parser("viz", help="Phylogeny / clade / Fitch parsimony / gene-flow HTML+SVG")
    vz.add_argument("--report", "--from-report", dest="report", default=None, help="report.json (default .codeevolve/report.json)")
    vz.add_argument("--out", default="codeevolve_viz.html", help="HTML/SVG/JSON/Newick file, or a directory")
    vz.add_argument(
        "--kind",
        default="all",
        choices=["all", "3d", "phylogeny", "clades", "parsimony", "gene-flow"],
        help="Scene to render (all = HTML gallery with 3D builder first)",
    )
    vz.add_argument("--format", dest="fmt", default="html", choices=["html", "svg", "json", "newick"])
    vz.add_argument("--collapse-unary", action="store_true", help="Hide unary same-clade chains")

    gr = sub.add_parser("graph", help="Parse/search context graph and agentic flow")
    gr.add_argument("--from-report", dest="from_report", default=None, help="report.json (default .codeevolve/report.json if present)")
    gr.add_argument("--from-agent", dest="from_agent", default=None, help="Agent dir (.codeevolve/agent) or run.json")
    gr.add_argument("--search", default=None, help="Search nodes (tools, kernels, frames, types, …)")
    gr.add_argument("--flow", nargs="?", const=True, default=False, help="Extract agentic flow (optional extra query)")
    gr.add_argument("--kernel", default=None, help="Focus flow on a kernel name (investigate, pay_down, …)")
    gr.add_argument("--kind", action="append", default=[], help="Restrict search to node kind (repeatable)")
    gr.add_argument("--family", default=None, help="Family slice or search filter: taxon|context|knowledge|decision|pivot|flow")
    gr.add_argument("--pivot", default=None, help="Pivot id or type (choose_path, propose, sense, …)")
    gr.add_argument("--precedent", nargs="?", const=True, default=False, help="Similar past decisions/pivots")
    gr.add_argument("--previous", default=None, help="Previous report.json for delta detection")
    gr.add_argument("--delta", action="store_true", help="Emit threshold-crossing delta nodes vs --previous")
    gr.add_argument("--surface", action="store_true", help="Rank deltas for proactive surfacing")
    gr.add_argument("--traverse", default="wave", help="Search traversal: wave|bfs|flow|pivot|rw|off")
    gr.add_argument("--depth", type=int, default=2, help="Traversal depth")
    gr.add_argument("--limit", type=int, default=20)
    gr.add_argument("--out", default=None, help="Write JSON")

    ev = sub.add_parser("evaluate", help="Run evaluation (synthetic + taxonomy gold + public scorecard)")
    ev.add_argument("--work-dir", default=None, help="Scratch dir for fixtures (default .codeevolve_eval)")
    ev.add_argument("--out", default=None, help="Write evaluation JSON")
    ev.add_argument("--md-out", default=None, help="Write evaluation markdown")
    ev.add_argument(
        "--suite",
        default="all",
        choices=["synthetic", "public", "taxonomy", "ecology", "dynamics", "agent", "all"],
        help="synthetic | taxonomy | ecology | dynamics | public | agent | all (default)",
    )
    ev.add_argument(
        "--offline",
        action="store_true",
        help="Do not clone; only use cached public repos (skip if missing)",
    )
    ev.add_argument(
        "--public-case",
        action="append",
        default=[],
        help="Limit public suite to case id (repeatable)",
    )

    ag = sub.add_parser(
        "agent",
        help="Objective-driven coding agent (sense→deliberate→act→verify via CodeEvolve)",
    )
    ag.add_argument(
        "--objective",
        default="follow_refactor",
        help="reduce_debt | raise_stability | reduce_risk | stabilize_path | follow_refactor | metric:PATH:min|max",
    )
    ag.add_argument("--path", default=None, help="Path fence / stabilize_path focus")
    ag.add_argument("--wave", default=None, help="Prefer refactor wave")
    ag.add_argument("--max-rounds", type=int, default=1)
    ag.add_argument("--max-commits", type=int, default=200)
    ag.add_argument("--apply", action="store_true", help="Write edits (default dry-run)")
    ag.add_argument(
        "--llm",
        nargs="?",
        const="auto",
        default="auto",
        help="Provider alias: auto|slm|hf-qwen|openai|anthropic|grok|kimi|kimik3|openrouter|custom|heuristic",
    )
    ag.add_argument(
        "--provider",
        default=None,
        help="Same as --llm (wins if both set): openai|anthropic|grok|kimi|kimik3|slm|hf-qwen|…",
    )
    ag.add_argument("--model", default=None, help="Chat/local model id override")
    ag.add_argument("--base-url", default=None, help="OpenAI-compatible API base URL")
    ag.add_argument("--api-key", default=None, help="API key (else provider env vars)")
    ag.add_argument("--list-providers", action="store_true", help="List model providers and exit")
    ag.add_argument("--no-cognition", action="store_true", help="Disable memory/RAG/reflect/tools/subagents stack")
    ag.add_argument("--no-spawn", action="store_true", help="Do not spawn kernel subagents")
    ag.add_argument("--no-web", action="store_true", help="Disable web_search tool")
    ag.add_argument("--allow-shell", action="store_true", help="Enable bounded shell tool")
    ag.add_argument("--rag-backend", default="memory", help="memory|chromadb|pinecone|auto")
    ag.add_argument("--max-subagents", type=int, default=3)
    ag.add_argument("--verify-cmd", default=None)
    ag.add_argument("--out", default=None, help="Write AgentRun JSON")
    ag.add_argument("--no-worktree", action="store_true", help="Skip git worktree/branch session on apply")
    ag.add_argument("--approve", action="store_true", help="HITL prompt before applying edits")
    ag.add_argument("--auto-approve", action="store_true", help="Skip HITL even with --approve")
    ag.add_argument("--max-wall-seconds", type=float, default=None)
    ag.add_argument("--max-cost-usd", type=float, default=None)
    ag.add_argument("--no-tests-on-apply", action="store_true", help="Skip auto-detected test run after apply")
    ag.add_argument("--parallel-subagents", action="store_true", help="Spawn kernel subagents in parallel")
    ag.add_argument("--no-resume", action="store_true", help="Do not resume from last session report")
    ag.add_argument("--previous-report", default=None, help="Explicit previous report.json for delta analyze")
    ag.add_argument("--no-frame-seed", action="store_true", help="Do not prefer frame:basin/delta steps")
    ag.add_argument("--no-blast-widen", action="store_true", help="Do not auto-widen path fence from blast")
    ag.add_argument("--no-pr-pack", action="store_true", help="Skip writing pr_pack.md/json")

    args = p.parse_args(argv)

    if args.cmd == "provenance" and (
        getattr(args, "schema", False) or getattr(args, "schema_out", None)
    ):
        from codeevolve.provenance.schema import schemas, write_schemas

        written = write_schemas(args.schema_out) if getattr(args, "schema_out", None) else {}
        payload = {"schemas": schemas(), "written": written}
        if getattr(args, "out", None):
            Path(args.out).write_text(json.dumps(payload, indent=2), encoding="utf-8")
        _print(payload)
        return 0

    if args.cmd == "provenance" and getattr(args, "from_report", None):
        from codeevolve.provenance import build_provenance_ledger, query_provenance

        data = json.loads(Path(args.from_report).read_text(encoding="utf-8"))
        ledger = build_provenance_ledger(data)
        payload = query_provenance(
            ledger,
            path=getattr(args, "path", None),
            clade=getattr(args, "clade", None),
            kind=getattr(args, "kind", None),
            tag=getattr(args, "tag", None),
            since=getattr(args, "since", None),
            until=getattr(args, "until", None),
            pack=bool(getattr(args, "pack", False)),
            path_pack=getattr(args, "path_pack", None),
            timeline=bool(getattr(args, "timeline", False)),
            resolve=getattr(args, "resolve", None),
            frame=getattr(args, "frame", None),
            depth=getattr(args, "depth", 2),
        )
        if getattr(args, "out", None):
            Path(args.out).write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
        _print(payload)
        return 0

    if args.cmd == "agent":
        from codeevolve.agent import run_agent
        from codeevolve.agent.objective import Objective
        from codeevolve.models.endpoints import recommend_agent_endpoint

        if args.list_providers:
            _print(recommend_agent_endpoint(args.repo))
            return 0

        obj = Objective.parse(args.objective, path=args.path, wave=args.wave)
        run = run_agent(
            args.repo,
            obj,
            max_rounds=args.max_rounds,
            apply=bool(args.apply),
            llm=args.llm,
            provider=args.provider,
            model=args.model,
            base_url=args.base_url,
            api_key=args.api_key,
            verify_cmd=args.verify_cmd,
            max_commits=args.max_commits,
            path=args.path,
            wave=args.wave,
            model_tier=args.model_tier,
            cognition=not bool(args.no_cognition),
            spawn_subagents=not bool(args.no_spawn),
            allow_web=not bool(args.no_web),
            allow_shell=bool(args.allow_shell),
            rag_backend=args.rag_backend,
            max_subagents=args.max_subagents,
            use_worktree=not bool(args.no_worktree),
            approve=bool(args.approve),
            auto_approve=bool(args.auto_approve),
            max_wall_seconds=args.max_wall_seconds,
            max_cost_usd=args.max_cost_usd,
            run_tests_on_apply=not bool(args.no_tests_on_apply),
            parallel_subagents=bool(args.parallel_subagents),
            resume=not bool(args.no_resume),
            previous_report=args.previous_report,
            prefer_frames=not bool(args.no_frame_seed),
            auto_widen_blast=not bool(args.no_blast_widen),
            write_pr_review=not bool(args.no_pr_pack),
        )
        payload = run.to_dict()
        if args.out:
            Path(args.out).write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
        _print(payload)
        return 0 if run.status in {"ok", "target_reached", "exhausted", "budget_stop"} else 1

    if args.cmd == "evaluate":
        report = CodeEvolve.evaluate(
            args.work_dir,
            suite=args.suite,
            offline=bool(args.offline),
            public_case_ids=args.public_case or None,
        )
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
                "suite": report.suite,
                "overall_score": report.overall_score,
                "synthetic_score": report.synthetic_score,
                "taxonomy_score": report.taxonomy_score,
                "ecology_score": report.ecology_score,
                "dynamics_score": report.dynamics_score,
                "public_score": report.public_score,
                "agent_score": report.agent_score,
                "public_skipped": report.public_skipped,
                "dynamics_skipped": report.dynamics_skipped,
                "passed_cases": report.passed_cases,
                "total_cases": report.total_cases,
                "cases": [
                    {"name": c.name, "score": c.score, "failed": c.failed} for c in report.cases
                ],
            }
        )
        # Pass if present suites meet floors; public may be skipped offline
        synth_ok = report.synthetic_score is None or report.synthetic_score >= 0.7
        tax_ok = report.taxonomy_score is None or report.taxonomy_score >= 0.7
        eco_ok = report.ecology_score is None or report.ecology_score >= 0.7
        dyn_ok = report.dynamics_score is None or report.dynamics_score >= 0.7
        public_ok = report.public_score is None or report.public_score >= 0.55
        agent_ok = report.agent_score is None or report.agent_score >= 0.55
        return 0 if (synth_ok and tax_ok and eco_ok and dyn_ok and public_ok and agent_ok and report.overall_score >= 0.55) else 1

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

    if args.cmd == "viz":
        from codeevolve.viz import write_viz

        report_path = args.report or str(Path(".codeevolve") / "report.json")
        cur = json.loads(Path(report_path).read_text(encoding="utf-8"))
        out = write_viz(
            cur,
            args.out,
            kind=args.kind,
            fmt=args.fmt,
            collapse_unary=bool(args.collapse_unary),
        )
        print(out)
        return 0

    if args.cmd == "graph":
        from codeevolve.graph import query_context

        report = None
        report_path = args.from_report
        if not report_path:
            guess = Path(".codeevolve") / "report.json"
            if guess.is_file() and not args.from_agent:
                report_path = str(guess)
            elif guess.is_file() and args.from_agent:
                report_path = str(guess)
        if report_path:
            report = json.loads(Path(report_path).read_text(encoding="utf-8"))
        agent_dir = args.from_agent
        if not agent_dir and not report_path:
            guess_agent = Path(".codeevolve") / "agent"
            if guess_agent.is_dir():
                agent_dir = str(guess_agent)
        prev_report = None
        if getattr(args, "previous", None):
            prev_report = json.loads(Path(args.previous).read_text(encoding="utf-8"))
        payload = query_context(
            report=report,
            agent_dir=agent_dir,
            previous=prev_report,
            search=args.search,
            flow=args.flow,
            kernel=args.kernel,
            kinds=list(args.kind) or None,
            family=getattr(args, "family", None),
            pivot=getattr(args, "pivot", None),
            precedent=getattr(args, "precedent", False),
            delta=bool(getattr(args, "delta", False)),
            surface=bool(getattr(args, "surface", False)),
            traverse=getattr(args, "traverse", "wave"),
            depth=int(getattr(args, "depth", 2) or 2),
            limit=args.limit,
        )
        if args.out:
            Path(args.out).write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
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
            include_cst=not args.no_cst,
            include_clones=not args.no_clones,
            include_reticulation=not args.no_reticulation,
            include_fork_lineage=not args.no_fork_lineage,
            peer_repos=args.peer_repo or None,
            guide_taxonomy=not args.no_taxonomy_guide,
            include_semantic=not args.no_semantic,
            include_rag=not args.no_rag,
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
        if args.viz_out:
            from codeevolve.viz import write_viz

            write_viz(report, args.viz_out)
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
                "rag": report.taxonomy.rag,
                "taxonomy_engine": (report.taxonomy.guidance or {}).get("engine"),
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
        include_semantic=args.cmd in {
            "taxonomy",
            "word2vec",
            "semantic-taxonomy",
            "report",
            "hierarchy",
            "provenance",
        },
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
    elif args.cmd == "hierarchy":
        ht = report.hierarchy_trends
        md_out = getattr(args, "md_out", None)
        if ht and md_out:
            Path(md_out).write_text(ht.markdown, encoding="utf-8")
            print(ht.markdown)
        elif ht:
            print(ht.markdown)
        else:
            _print({})
    elif args.cmd == "provenance":
        from codeevolve.provenance import build_provenance_ledger, query_provenance

        ledger = report.provenance or build_provenance_ledger(report.to_dict())
        payload = query_provenance(
            ledger,
            path=getattr(args, "path", None),
            clade=getattr(args, "clade", None),
            kind=getattr(args, "kind", None),
            tag=getattr(args, "tag", None),
            since=getattr(args, "since", None),
            until=getattr(args, "until", None),
            pack=bool(getattr(args, "pack", False)),
            path_pack=getattr(args, "path_pack", None),
            timeline=bool(getattr(args, "timeline", False)),
            resolve=getattr(args, "resolve", None),
            frame=getattr(args, "frame", None),
            depth=getattr(args, "depth", 2),
        )
        out = getattr(args, "out", None)
        if out:
            Path(out).write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
        _print(payload)
    elif args.cmd == "keyword-taxonomy":
        kw = report.taxonomy.keyword_taxonomy
        if kw:
            print(kw.to_dict().get("ascii_tree") or "")
            print()
            _print({k: v for k, v in kw.to_dict().items() if k != "ascii_tree"})
        else:
            _print({})
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
