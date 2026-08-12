"""Objective-driven coding agent loop powered by CodeEvolve natively."""

from __future__ import annotations

import json
import os
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from codeevolve.agent.actor import ActionProposal, propose_action
from codeevolve.agent.blast import preview_blast
from codeevolve.agent.budget import Budget, BudgetTracker, approve_edits
from codeevolve.agent.cognition import CognitiveRuntime
from codeevolve.agent.frameseed import ranks_steps_with_frames
from codeevolve.agent.gitwork import begin_session, commit_accepted, end_session, working_root
from codeevolve.agent.objective import (
    Objective,
    ObjectiveScore,
    ranks_steps_for_objective,
    score_objective,
)
from codeevolve.agent.prpack import write_pr_pack
from codeevolve.agent.session import (
    previous_report_for_run,
    remember_delta,
    update_session_after_run,
)
from codeevolve.agent.testing import detect_test_runner, run_tests, score_tests, score_with_ci_gate
from codeevolve.agent.workspace import Workspace
from codeevolve.api import CodeEvolve
from codeevolve.models.endpoints import recommend_agent_endpoint, resolve_endpoint
from codeevolve.models.tiers import apply_tier_env
from codeevolve.provenance.ledger import build_provenance_ledger
from codeevolve.report.diff import diff_reports


def _agent_env() -> None:
    # Keep analyze light; do NOT force SKIP_HF — actor may use SLM / GPU Qwen.
    os.environ.setdefault("CODEEVOLVE_SKIP_EMBED", "1")
    os.environ.setdefault("CODEEVOLVE_SKIP_GHSA", "1")
    os.environ.setdefault("PYTHONUTF8", "1")


@dataclass
class RoundResult:
    index: int
    step_id: str | None
    proposal: dict[str, Any] | None
    applied: bool
    patch: dict[str, Any] | None
    verify_ok: bool | None
    score_before: dict[str, Any]
    score_after: dict[str, Any] | None
    accepted: bool
    report_path: str
    notes: list[str] = field(default_factory=list)
    cognition: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "index": self.index,
            "step_id": self.step_id,
            "proposal": self.proposal,
            "applied": self.applied,
            "patch": self.patch,
            "verify_ok": self.verify_ok,
            "score_before": self.score_before,
            "score_after": self.score_after,
            "accepted": self.accepted,
            "report_path": self.report_path,
            "notes": list(self.notes),
            "cognition": self.cognition,
        }


@dataclass
class AgentRun:
    objective: dict[str, Any]
    repo: str
    rounds: list[RoundResult] = field(default_factory=list)
    final_score: dict[str, Any] | None = None
    final_report_path: str | None = None
    status: str = "ok"
    summary: str = ""
    endpoint: dict[str, Any] = field(default_factory=dict)
    cognition: dict[str, Any] | None = None
    budget: dict[str, Any] | None = None
    git: dict[str, Any] | None = None
    tests: dict[str, Any] | None = None
    pr_pack: dict[str, Any] | None = None
    session: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "objective": self.objective,
            "repo": self.repo,
            "endpoint": dict(self.endpoint),
            "cognition": self.cognition,
            "budget": self.budget,
            "git": self.git,
            "tests": self.tests,
            "pr_pack": self.pr_pack,
            "session": self.session,
            "rounds": [r.to_dict() for r in self.rounds],
            "final_score": self.final_score,
            "final_report_path": self.final_report_path,
            "status": self.status,
            "summary": self.summary,
        }


class EvolveAgent:
    """Sense (CodeEvolve) → deliberate (frames) → act (bounded edits) → verify (re-score)."""

    def __init__(
        self,
        repo: Path | str = ".",
        *,
        objective: Objective | str | None = None,
        max_commits: int = 200,
        work_dir: Path | str | None = None,
        apply: bool = False,
        llm: str | bool | None = "auto",
        provider: str | None = None,
        model: str | None = None,
        base_url: str | None = None,
        api_key: str | None = None,
        verify_cmd: str | None = None,
        model_tier: str = "slm",
        cognition: bool = True,
        spawn_subagents: bool = True,
        allow_web: bool = True,
        allow_shell: bool = False,
        rag_backend: str = "memory",
        max_subagents: int = 3,
        use_worktree: bool = True,
        approve: bool = False,
        auto_approve: bool = False,
        budget: Budget | None = None,
        max_wall_seconds: float | None = None,
        max_cost_usd: float | None = None,
        run_tests_on_apply: bool = True,
        parallel_subagents: bool = False,
        resume: bool = True,
        previous_report: Path | str | None = None,
        prefer_frames: bool = True,
        auto_widen_blast: bool = True,
        refuse_huge_blast: bool = True,
        write_pr_review: bool = True,
    ) -> None:
        _agent_env()
        apply_tier_env(model_tier, model_override=model if provider in {None, "slm", "hf-qwen", "auto"} else None)
        self.base_repo = Path(repo).resolve() if Path(str(repo)).exists() else Path(str(repo))
        self.ce = CodeEvolve(repo, model_tier=model_tier, model=model if provider in {"slm", "hf-qwen"} else None)
        self.repo_path = Path(self.ce.repo)
        if isinstance(objective, Objective):
            self.objective = objective
        elif isinstance(objective, str):
            self.objective = Objective.parse(objective)
        else:
            self.objective = Objective()
        self.max_commits = max_commits
        self.apply = apply
        # provider wins over llm alias; default auto selects SLM/GPU/cloud
        self.llm = provider or llm or "auto"
        self.model = model
        self.base_url = base_url
        self.api_key = api_key
        self.verify_cmd = verify_cmd
        self.model_tier = model_tier
        self.cognition_enabled = cognition
        self.spawn_subagents = spawn_subagents
        self.allow_web = allow_web
        self.allow_shell = allow_shell
        self.rag_backend = rag_backend
        self.max_subagents = max_subagents
        self.use_worktree = use_worktree
        self.approve = approve
        self.auto_approve = auto_approve
        self.run_tests_on_apply = run_tests_on_apply
        self.parallel_subagents = parallel_subagents
        self.resume = resume
        self.previous_report = previous_report
        self.prefer_frames = prefer_frames
        self.auto_widen_blast = auto_widen_blast
        self.refuse_huge_blast = refuse_huge_blast
        self.write_pr_review = write_pr_review
        bud = budget or Budget()
        if max_wall_seconds is not None:
            bud.max_wall_seconds = max_wall_seconds
        if max_cost_usd is not None:
            bud.max_cost_usd = max_cost_usd
        self.tracker = BudgetTracker(budget=bud)
        self.work_dir = Path(work_dir) if work_dir else self.repo_path / ".codeevolve" / "agent"
        self.work_dir.mkdir(parents=True, exist_ok=True)
        self.endpoint = resolve_endpoint(
            self.llm,
            model=self.model,
            base_url=self.base_url,
            api_key=self.api_key,
            repo=self.repo_path,
        )
        self.runtime: CognitiveRuntime | None = None
        if self.cognition_enabled:
            self.runtime = CognitiveRuntime(
                self.repo_path,
                work_dir=self.work_dir,
                rag_backend=self.rag_backend,
                allow_web=self.allow_web,
                allow_shell=self.allow_shell,
                llm=self.llm,
                model=self.model,
                base_url=self.base_url,
                api_key=self.api_key,
                spawn=self.spawn_subagents,
                max_subagents=self.max_subagents,
                parallel=self.parallel_subagents,
            )
        self.git_session = None
        cov = bool(self.objective.require_coverage or self.objective.kind == "pass_tests")
        self._detected_runner = detect_test_runner(self.repo_path, with_coverage=cov)

    def _analyze(self, *, previous: Path | str | None = None) -> tuple[dict[str, Any], Path]:
        # Fast sensors for scoring; actor uses the resolved chat endpoint separately.
        prev_tax = os.environ.get("CODEEVOLVE_TAXONOMY_HEURISTIC")
        os.environ["CODEEVOLVE_TAXONOMY_HEURISTIC"] = "1"
        try:
            report = self.ce.analyze(
                max_commits=self.max_commits,
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
                include_semantic=False,
                include_rag=False,
                previous_report=previous,
            )
        finally:
            if prev_tax is None:
                os.environ.pop("CODEEVOLVE_TAXONOMY_HEURISTIC", None)
            else:
                os.environ["CODEEVOLVE_TAXONOMY_HEURISTIC"] = prev_tax
        data = report.to_dict()
        stamp = time.strftime("%Y%m%d_%H%M%S")
        out = self.work_dir / f"report_{stamp}.json"
        out.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
        # also refresh canonical
        canon = self.repo_path / ".codeevolve" / "report.json"
        canon.parent.mkdir(parents=True, exist_ok=True)
        canon.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
        return data, out

    def _pack(self, report: dict[str, Any], *, path: str | None = None) -> dict[str, Any]:
        ledger = build_provenance_ledger(report)
        return ledger.deliberation_pack(path=path or self.objective.path)

    def _path_pack(self, report: dict[str, Any], path: str) -> dict[str, Any]:
        ledger = build_provenance_ledger(report)
        from codeevolve.provenance.ledger import query_provenance

        return query_provenance(ledger, path_pack=path)

    def _verify(self) -> bool | None:
        if not self.verify_cmd:
            return None
        try:
            proc = subprocess.run(
                self.verify_cmd,
                shell=True,
                cwd=str(self.repo_path),
                capture_output=True,
                text=True,
                timeout=600,
                check=False,
            )
            (self.work_dir / "last_verify.log").write_text(
                (proc.stdout or "") + "\n" + (proc.stderr or ""),
                encoding="utf-8",
            )
            return proc.returncode == 0
        except (OSError, subprocess.SubprocessError) as exc:
            (self.work_dir / "last_verify.log").write_text(str(exc), encoding="utf-8")
            return False

    def run(self, *, max_rounds: int = 1) -> AgentRun:
        # Invocation max_rounds is authoritative for this run
        self.tracker.budget.max_rounds = max(1, max_rounds)
        # Git-safe session (worktree/branch) when applying or explicitly enabled
        if self.use_worktree and (self.apply or self.approve):
            self.git_session = begin_session(self.repo_path, use_worktree=True)
            wr = working_root(self.git_session)
            if wr != self.repo_path and wr.exists():
                self.repo_path = wr
                self.ce = CodeEvolve(
                    wr,
                    model_tier=self.model_tier,
                    model=self.model if self.llm in {"slm", "hf-qwen"} else None,
                )
                self.work_dir = wr / ".codeevolve" / "agent"
                self.work_dir.mkdir(parents=True, exist_ok=True)
                if self.cognition_enabled:
                    self.runtime = CognitiveRuntime(
                        self.repo_path,
                        work_dir=self.work_dir,
                        rag_backend=self.rag_backend,
                        allow_web=self.allow_web,
                        allow_shell=self.allow_shell,
                        llm=self.llm,
                        model=self.model,
                        base_url=self.base_url,
                        api_key=self.api_key,
                        spawn=self.spawn_subagents,
                        max_subagents=self.max_subagents,
                        parallel=self.parallel_subagents,
                    )

        run = AgentRun(
            objective=self.objective.to_dict(),
            repo=str(self.repo_path),
            endpoint=self.endpoint.to_dict(),
            git=self.git_session.to_dict() if self.git_session else None,
        )
        (self.work_dir / "endpoint.json").write_text(
            json.dumps(recommend_agent_endpoint(self.repo_path), indent=2, default=str),
            encoding="utf-8",
        )
        # Baseline tests for pass_tests objective
        test_baseline = None
        if self.objective.kind == "pass_tests" or self.run_tests_on_apply:
            cmd = self.verify_cmd or (self._detected_runner.command if self._detected_runner else None)
            if cmd:
                test_baseline = run_tests(self.repo_path, command=cmd)
                run.tests = {"baseline": test_baseline.to_dict(), "score": score_tests(test_baseline)}
                baseline_tests_score = score_tests(test_baseline)["value"]
            else:
                baseline_tests_score = 0.0
        else:
            baseline_tests_score = 0.0

        # Cross-run delta: resume from last accepted report when available
        session_prev = previous_report_for_run(
            self.work_dir,
            explicit=self.previous_report,
            resume=self.resume,
        )
        baseline, baseline_path = self._analyze(previous=session_prev)
        if self.objective.kind == "pass_tests":
            baseline = {**baseline, "tests": {"score": baseline_tests_score}}
        prev_score = score_objective(self.objective, baseline)
        run.final_score = prev_score.to_dict()
        run.final_report_path = str(baseline_path)
        if session_prev:
            run.session = {"resumed_from": str(session_prev)}
            if self.runtime is not None:
                remember_delta(
                    self.runtime.memory,
                    report=baseline,
                    previous_path=str(session_prev),
                    diff=baseline.get("diff") if isinstance(baseline.get("diff"), dict) else None,
                    accepted=None,
                    frame_ids=["frame:delta:report"],
                )

        pack = self._pack(baseline)
        steps = ranks_steps_with_frames(
            self.objective,
            baseline.get("refactor_plan") if isinstance(baseline.get("refactor_plan"), dict) else None,
            baseline.get("risk") if isinstance(baseline.get("risk"), dict) else None,
            pack,
            prefer_frames=self.prefer_frames,
        )
        # normalize steps list from waves form
        if not steps and isinstance(baseline.get("refactor_plan"), dict):
            for wave in baseline["refactor_plan"].get("waves") or []:
                steps.extend(wave.get("steps") or [])
            steps = ranks_steps_for_objective(self.objective, {"steps": steps}, baseline.get("risk"))

        attempted: set[str] = set()
        current_report = baseline
        current_path = baseline_path
        last_diff: dict[str, Any] | None = (
            baseline.get("diff") if isinstance(baseline.get("diff"), dict) else None
        )

        for i in range(max(1, max_rounds)):
            ok_budget, stop_reason = self.tracker.check()
            if not ok_budget:
                run.status = "budget_stop"
                run.rounds.append(
                    RoundResult(
                        index=i,
                        step_id=None,
                        proposal=None,
                        applied=False,
                        patch=None,
                        verify_ok=None,
                        score_before=prev_score.to_dict(),
                        score_after=None,
                        accepted=False,
                        report_path=str(current_path),
                        notes=[f"budget stop: {stop_reason}"],
                    )
                )
                break
            self.tracker.tick_round()
            notes: list[str] = []
            step = next((s for s in steps if str(s.get("id")) not in attempted), None)
            if step is None:
                notes.append("no remaining refactor steps")
                run.rounds.append(
                    RoundResult(
                        index=i,
                        step_id=None,
                        proposal=None,
                        applied=False,
                        patch=None,
                        verify_ok=None,
                        score_before=prev_score.to_dict(),
                        score_after=None,
                        accepted=False,
                        report_path=str(current_path),
                        notes=notes,
                    )
                )
                run.status = "exhausted"
                break

            step_id = str(step.get("id"))
            attempted.add(step_id)
            paths = [str(p) for p in (step.get("paths") or []) if p]
            if self.objective.path and self.objective.path not in paths:
                paths = [self.objective.path] + paths
            fence = paths[:6]
            workspace = Workspace(self.repo_path, fence_paths=fence or None)

            path_pack = None
            if fence:
                try:
                    path_pack = self._path_pack(current_report, fence[0])
                except Exception as exc:  # noqa: BLE001 — keep loop alive
                    notes.append(f"path_pack failed: {exc}")

            # Cognitive cycle: memory / RAG / morphemes / reflect / tools / compact / spawn
            cognition_state = None
            if self.runtime is not None:
                try:
                    prior = run.rounds[-1].to_dict() if run.rounds else None
                    cognition_state = self.runtime.run_cycle(
                        self.objective,
                        round_result=prior,
                        paths=fence or None,
                    )
                    notes.append(
                        f"cognition: reflect={cognition_state.reflection.get('stance')} "
                        f"subagents={len(cognition_state.subagents)} "
                        f"tools={len((cognition_state.actions or {}).get('results') or [])}"
                    )
                    run.cognition = cognition_state.to_dict()
                except Exception as exc:  # noqa: BLE001
                    notes.append(f"cognition failed: {exc}")

            # Respect insufficient stance from empty evidence
            frames = (path_pack or pack).get("frames") or []
            if path_pack and not frames and not paths:
                proposal = ActionProposal(
                    step_id=step_id,
                    title=str(step.get("title") or step_id),
                    paths=paths,
                    frame_ids=[],
                    evidence_refs=[],
                    rationale="No frames/paths available; stance insufficient",
                    falsifier="n/a",
                    measure="Re-run analyze_repo",
                    stance="insufficient",
                )
            else:
                tools = self.runtime.tools if self.runtime else None
                proposal = propose_action(
                    workspace,
                    step,
                    objective=self.objective.to_dict(),
                    path_pack=path_pack,
                    pack=pack,
                    llm=self.llm,
                    model=self.model,
                    base_url=self.base_url,
                    api_key=self.api_key,
                    repo=self.repo_path,
                    tools=tools,
                    budget=self.tracker,
                    structured_tools=True,
                )

            round_dir = self.work_dir / f"round_{i:02d}_{step_id}"
            round_dir.mkdir(parents=True, exist_ok=True)
            (round_dir / "proposal.json").write_text(
                json.dumps(proposal.to_dict(), indent=2, default=str),
                encoding="utf-8",
            )
            if path_pack:
                (round_dir / "path_pack.json").write_text(
                    json.dumps(path_pack, indent=2, default=str),
                    encoding="utf-8",
                )
            if cognition_state is not None:
                (round_dir / "cognition.json").write_text(
                    json.dumps(cognition_state.to_dict(), indent=2, default=str),
                    encoding="utf-8",
                )

            applied = False
            patch_info = None
            verify_ok = None
            score_after: ObjectiveScore | None = None
            accepted = False
            after_path = current_path

            if proposal.stance == "insufficient":
                notes.append("stance=insufficient — no edits applied")
            elif proposal.stance == "defer":
                notes.append("stance=defer — already addressed or no-op")
            elif not proposal.edits:
                notes.append("no edits in proposal")
            elif not self.apply:
                notes.append("dry-run (pass --apply to write edits)")
                blast = preview_blast(
                    current_report,
                    [e.path for e in proposal.edits],
                    fence=fence,
                    path_pack=path_pack if isinstance(path_pack, dict) else None,
                    auto_widen=self.auto_widen_blast,
                    refuse_if_huge=self.refuse_huge_blast,
                )
                (round_dir / "blast.json").write_text(
                    json.dumps(blast.to_dict(), indent=2, default=str),
                    encoding="utf-8",
                )
                notes.append(
                    f"blast preview score={blast.blast_score} co_changers={len(blast.co_changers)}"
                )
                for edit in proposal.edits:
                    preview = round_dir / "preview" / edit.path
                    preview.parent.mkdir(parents=True, exist_ok=True)
                    preview.write_text(edit.content, encoding="utf-8")
            else:
                blast = preview_blast(
                    current_report,
                    [e.path for e in proposal.edits],
                    fence=fence,
                    path_pack=path_pack if isinstance(path_pack, dict) else None,
                    auto_widen=self.auto_widen_blast,
                    refuse_if_huge=self.refuse_huge_blast,
                )
                (round_dir / "blast.json").write_text(
                    json.dumps(blast.to_dict(), indent=2, default=str),
                    encoding="utf-8",
                )
                if blast.widened_fence and blast.widened_fence != fence:
                    workspace = Workspace(self.repo_path, fence_paths=blast.widened_fence)
                    notes.append(f"fence widened for blast: {blast.widened_fence[:8]}")
                if blast.refuse:
                    notes.append(f"refused apply: {blast.reason}")
                else:
                    ok_apply, reason = approve_edits(
                        proposal.to_dict(),
                        interactive=self.approve and not self.auto_approve,
                        auto_approve=self.auto_approve or (self.apply and not self.approve),
                        preapproved=True if (self.auto_approve or not self.approve) else None,
                    )
                    if not ok_apply:
                        notes.append(f"HITL denied apply: {reason}")
                    else:
                        snap = round_dir / "snapshot"
                        patch_result = workspace.apply_edits(proposal.edits, snapshot_dir=snap)
                        patch_info = patch_result.to_dict()
                        applied = bool(patch_result.applied)
                        notes.extend(patch_result.errors)
                        if applied:
                            verify_ok = self._verify()
                            test_after = None
                            if verify_ok is not False and self.run_tests_on_apply:
                                cmd = self.verify_cmd or (
                                    self._detected_runner.command if self._detected_runner else None
                                )
                                if cmd:
                                    test_after = run_tests(self.repo_path, command=cmd)
                                    verify_ok = (
                                        test_after.ok if verify_ok is None else (verify_ok and test_after.ok)
                                    )
                                    run.tests = {
                                        **(run.tests or {}),
                                        "latest": test_after.to_dict(),
                                        "score": score_tests(test_after, test_baseline),
                                    }
                            if verify_ok is False:
                                workspace.restore(snap)
                                notes.append("verify/tests failed — rolled back")
                                applied = False
                            else:
                                after_report, after_path = self._analyze(previous=current_path)
                                if test_after is not None:
                                    after_report = {
                                        **after_report,
                                        "tests": {"score": score_tests(test_after)["value"]},
                                    }
                                if test_baseline is not None and "tests" not in current_report:
                                    current_report = {
                                        **current_report,
                                        "tests": {"score": score_tests(test_baseline)["value"]},
                                    }
                                diff = diff_reports(after_report, current_report).to_dict()
                                last_diff = diff
                                (round_dir / "diff.json").write_text(
                                    json.dumps(diff, indent=2, default=str),
                                    encoding="utf-8",
                                )
                                score_after = score_objective(
                                    self.objective,
                                    after_report,
                                    current_report,
                                    diff=diff,
                                )
                                gate = score_with_ci_gate(
                                    after_report,
                                    current_report,
                                    test_result=test_after,
                                    previous_tests=test_baseline,
                                    require_coverage=bool(self.objective.require_coverage),
                                    min_coverage_delta=float(self.objective.min_coverage_delta or 0.0),
                                )
                                (round_dir / "ci_gate.json").write_text(
                                    json.dumps(gate, indent=2, default=str),
                                    encoding="utf-8",
                                )
                                accept = (
                                    score_after.improved
                                    and score_after.constraints_ok
                                    and gate.get("ok", True)
                                )
                                if not accept and score_after.constraints_ok and not score_after.improved:
                                    worsened = diff.get("worsened") or []
                                    if not worsened and proposal.backend.startswith("heuristic"):
                                        accept = True
                                        notes.append("accepted heuristic artifact with no worsened signals")
                                if self.runtime is not None:
                                    remember_delta(
                                        self.runtime.memory,
                                        report=after_report,
                                        previous_path=str(current_path),
                                        diff=diff,
                                        accepted=accept,
                                        frame_ids=list(proposal.frame_ids or []),
                                    )
                                if accept:
                                    accepted = True
                                    current_report = after_report
                                    current_path = after_path
                                    pack = self._pack(current_report)
                                    prev_score = score_after
                                    notes.append("accepted — objective progress kept")
                                    if self.git_session is not None:
                                        sha = commit_accepted(
                                            self.git_session,
                                            message=f"codeevolve({self.objective.kind}): {step_id}",
                                            paths=[e.path for e in proposal.edits],
                                        )
                                        if sha:
                                            notes.append(
                                                f"committed {sha[:8]} on {self.git_session.work_branch}"
                                            )
                                else:
                                    workspace.restore(snap)
                                    notes.append("rejected — rolled back (objective/constraints/ci)")
                                    applied = False

            round_res = RoundResult(
                index=i,
                step_id=step_id,
                proposal=proposal.to_dict(),
                applied=applied,
                patch=patch_info,
                verify_ok=verify_ok,
                score_before=prev_score.to_dict(),
                score_after=score_after.to_dict() if score_after else None,
                accepted=accepted,
                report_path=str(after_path),
                notes=notes,
                cognition=cognition_state.to_dict() if cognition_state else None,
            )
            run.rounds.append(round_res)
            (round_dir / "round.json").write_text(
                json.dumps(round_res.to_dict(), indent=2, default=str),
                encoding="utf-8",
            )

            if score_after and score_after.reached_target:
                run.status = "target_reached"
                break

        if self.git_session is not None:
            end_session(self.git_session, keep_branch=True, restore_base=True)
            run.git = self.git_session.to_dict()
        run.final_score = prev_score.to_dict()
        run.final_report_path = str(current_path)
        run.endpoint = self.endpoint.to_dict()
        run.budget = self.tracker.to_dict()
        self.tracker.save(self.work_dir / "budget.json")
        run_path = self.work_dir / "run.json"
        sess = update_session_after_run(
            self.work_dir,
            repo=str(self.repo_path),
            report_path=str(current_path),
            run_path=str(run_path),
            score=run.final_score,
            objective=self.objective.to_dict(),
            diff=last_diff,
            notes=[f"status={run.status}"],
        )
        run.session = {**(run.session or {}), **sess.to_dict()}
        if self.write_pr_review:
            paths = write_pr_pack(
                run.to_dict(),
                self.work_dir,
                report=current_report,
                diff=last_diff,
            )
            run.pr_pack = {"paths": paths, "kind": "codeevolve_pr_pack"}
        accepted_n = sum(1 for r in run.rounds if r.accepted)
        run.summary = (
            f"EvolveAgent objective={self.objective.kind} "
            f"provider={self.endpoint.provider}:{self.endpoint.model} "
            f"rounds={len(run.rounds)} accepted={accepted_n} status={run.status} "
            f"score={run.final_score.get('value') if run.final_score else None} "
            f"cost_usd={run.budget.get('cost_usd')}"
        )
        run_path.write_text(
            json.dumps(run.to_dict(), indent=2, default=str),
            encoding="utf-8",
        )
        return run


def run_agent(
    repo: Path | str,
    objective: str | Objective = "follow_refactor",
    *,
    max_rounds: int = 1,
    apply: bool = False,
    llm: str | bool | None = "auto",
    provider: str | None = None,
    model: str | None = None,
    base_url: str | None = None,
    api_key: str | None = None,
    verify_cmd: str | None = None,
    max_commits: int = 200,
    path: str | None = None,
    wave: str | None = None,
    model_tier: str = "slm",
    cognition: bool = True,
    spawn_subagents: bool = True,
    allow_web: bool = True,
    allow_shell: bool = False,
    rag_backend: str = "memory",
    max_subagents: int = 3,
    use_worktree: bool = True,
    approve: bool = False,
    auto_approve: bool = False,
    max_wall_seconds: float | None = None,
    max_cost_usd: float | None = None,
    run_tests_on_apply: bool = True,
    parallel_subagents: bool = False,
    resume: bool = True,
    previous_report: Path | str | None = None,
    prefer_frames: bool = True,
    auto_widen_blast: bool = True,
    refuse_huge_blast: bool = True,
    write_pr_review: bool = True,
) -> AgentRun:
    if isinstance(objective, str):
        obj = Objective.parse(objective, path=path, wave=wave)
    else:
        obj = objective
        if path:
            obj.path = path
        if wave:
            obj.wave = wave
    agent = EvolveAgent(
        repo,
        objective=obj,
        max_commits=max_commits,
        apply=apply,
        llm=llm,
        provider=provider,
        model=model,
        base_url=base_url,
        api_key=api_key,
        verify_cmd=verify_cmd,
        model_tier=model_tier,
        cognition=cognition,
        spawn_subagents=spawn_subagents,
        allow_web=allow_web,
        allow_shell=allow_shell,
        rag_backend=rag_backend,
        max_subagents=max_subagents,
        use_worktree=use_worktree,
        approve=approve,
        auto_approve=auto_approve,
        max_wall_seconds=max_wall_seconds,
        max_cost_usd=max_cost_usd,
        run_tests_on_apply=run_tests_on_apply,
        parallel_subagents=parallel_subagents,
        resume=resume,
        previous_report=previous_report,
        prefer_frames=prefer_frames,
        auto_widen_blast=auto_widen_blast,
        refuse_huge_blast=refuse_huge_blast,
        write_pr_review=write_pr_review,
    )
    return agent.run(max_rounds=max_rounds)
