"""python -m codeevolve.agent — objective-driven improve loop."""

from __future__ import annotations

import argparse
import json

from codeevolve.agent.loop import run_agent
from codeevolve.agent.objective import Objective
from codeevolve.models.endpoints import recommend_agent_endpoint


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        prog="python -m codeevolve.agent",
        description="Coding agent that uses CodeEvolve natively to improve toward an objective",
    )
    p.add_argument("--repo", default=".", help="Local path, GitHub URL, or owner/repo")
    p.add_argument(
        "--objective",
        default="follow_refactor",
        help=(
            "reduce_debt | raise_stability | reduce_risk | stabilize_path | "
            "follow_refactor | pass_tests | metric:debt.score:min"
        ),
    )
    p.add_argument("--path", default=None, help="Optional path fence / stabilize_path focus")
    p.add_argument("--wave", default=None, help="Prefer refactor wave: stabilize|contain|pay_down|evolve")
    p.add_argument("--max-rounds", type=int, default=1)
    p.add_argument("--max-commits", type=int, default=200)
    p.add_argument("--apply", action="store_true", help="Write edits (default: dry-run proposals)")
    p.add_argument(
        "--llm",
        nargs="?",
        const="auto",
        default="auto",
        help="auto|slm|hf-qwen|openai|anthropic|grok|kimi|kimik3|openrouter|custom|heuristic",
    )
    p.add_argument("--provider", default=None, help="Provider (wins over --llm)")
    p.add_argument("--model", default=None, help="Model id override")
    p.add_argument("--base-url", default=None, help="OpenAI-compatible base URL")
    p.add_argument("--api-key", default=None, help="API key override")
    p.add_argument("--model-tier", default="slm", help="slm|standard|large|frontier (local ladder)")
    p.add_argument("--list-providers", action="store_true")
    p.add_argument("--no-cognition", action="store_true")
    p.add_argument("--no-spawn", action="store_true")
    p.add_argument("--no-web", action="store_true")
    p.add_argument("--allow-shell", action="store_true")
    p.add_argument("--rag-backend", default="memory")
    p.add_argument("--max-subagents", type=int, default=3)
    p.add_argument("--verify-cmd", default=None, help="Shell command that must pass after apply")
    p.add_argument("--out", default=None, help="Write AgentRun JSON")
    p.add_argument("--no-worktree", action="store_true")
    p.add_argument("--approve", action="store_true")
    p.add_argument("--auto-approve", action="store_true")
    p.add_argument("--max-wall-seconds", type=float, default=None)
    p.add_argument("--max-cost-usd", type=float, default=None)
    p.add_argument("--no-tests-on-apply", action="store_true")
    p.add_argument("--parallel-subagents", action="store_true")
    p.add_argument("--no-resume", action="store_true")
    p.add_argument("--previous-report", default=None)
    p.add_argument("--no-frame-seed", action="store_true")
    p.add_argument("--no-blast-widen", action="store_true")
    p.add_argument("--no-pr-pack", action="store_true")
    args = p.parse_args(argv)

    if args.list_providers:
        print(json.dumps(recommend_agent_endpoint(args.repo), indent=2, default=str))
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
        from pathlib import Path

        Path(args.out).write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    print(json.dumps(payload, indent=2, default=str))
    if run.status in {"ok", "target_reached", "exhausted", "budget_stop"}:
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
