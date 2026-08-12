"""v0.21 — PR pack, frame seed, session delta, AST fence, blast, coverage gate, apply eval."""

from __future__ import annotations

from pathlib import Path

from codeevolve.agent.blast import preview_blast
from codeevolve.agent.frameseed import ranks_steps_with_frames, steps_from_frames
from codeevolve.agent.objective import Objective
from codeevolve.agent.patch import symbol_fence_for
from codeevolve.agent.prpack import build_pr_pack, render_pr_pack_markdown, write_pr_pack
from codeevolve.agent.session import load_session, previous_report_for_run, update_session_after_run
from codeevolve.agent import testing as testing_mod
from codeevolve.taxonomy.symbols import scan_symbols

_TestRun = testing_mod.TestRunResult
coverage_gate = testing_mod.coverage_gate


def test_pr_pack_render(tmp_path: Path) -> None:
    run = {
        "objective": {"kind": "reduce_debt", "description": "pay debt"},
        "status": "ok",
        "summary": "done",
        "final_score": {"value": 0.2},
        "rounds": [
            {
                "index": 0,
                "step_id": "R1",
                "accepted": True,
                "proposal": {
                    "stance": "proceed",
                    "frame_ids": ["frame:basin"],
                    "falsifier": "stability drops",
                    "measure": "re-analyze",
                    "paths": ["src/a.py"],
                    "rationale": "contain hotspot",
                },
                "score_before": {"value": 0.5},
                "score_after": {"value": 0.2},
                "notes": ["accepted"],
            }
        ],
        "git": {"work_branch": "codeevolve/agent-x", "base_branch": "main"},
    }
    pack = build_pr_pack(run, report={"stability": {"composite": 0.7}, "debt": {"score": 0.2}})
    md = render_pr_pack_markdown(pack)
    assert "frame:basin" in md and "Falsifier" in md
    paths = write_pr_pack(run, tmp_path)
    assert Path(paths["md"]).is_file()


def test_frame_seed_ranks_basin_first() -> None:
    pack = {
        "frames": [
            {
                "id": "frame:basin",
                "claim": "Repo in attractor basin",
                "stance": "assert",
                "falsifier": "trajectory leaves basin",
                "measure": "dynamics",
                "context_paths": ["src/core.py"],
                "evidence": [{"record_id": "rec:1", "kind": "dynamics", "role": "support"}],
            }
        ]
    }
    steps = steps_from_frames(Objective.parse("follow_refactor"), pack)
    assert steps and "basin" in steps[0]["id"]
    ranked = ranks_steps_with_frames(
        Objective.parse("reduce_risk"),
        {"steps": [{"id": "R9", "wave": "evolve", "paths": ["other.py"]}]},
        {"failure_points": []},
        pack,
    )
    assert ranked[0]["id"].startswith("FR-")


def test_session_resume(tmp_path: Path) -> None:
    report = tmp_path / "report.json"
    report.write_text("{}", encoding="utf-8")
    update_session_after_run(
        tmp_path,
        repo=str(tmp_path),
        report_path=str(report),
        run_path=str(tmp_path / "run.json"),
        score={"value": 1},
        objective={"kind": "reduce_debt"},
    )
    sess = load_session(tmp_path)
    assert sess and sess.last_report_path
    prev = previous_report_for_run(tmp_path, resume=True)
    assert prev == report
    assert previous_report_for_run(tmp_path, resume=False) is None


def test_ast_symbol_fence_python() -> None:
    src = "def outer():\n    x = 1\n    return x\n\ndef inner():\n    return 2\n"
    nodes, eng = scan_symbols("m.py", src)
    assert eng == "ast"
    outer = next(n for n in nodes if n.qualname.endswith("::outer"))
    assert outer.end_line is not None and outer.end_line >= outer.line
    fence = symbol_fence_for("m.py", src, qualname="outer")
    assert fence is not None
    assert fence.start_line == 1
    assert fence.end_line >= 3


def test_blast_preview_widens() -> None:
    report = {
        "risk": {
            "failure_points": [
                {
                    "id": "FP1",
                    "kind": "hotspot_blast",
                    "path": "src/a.py",
                    "severity": 0.9,
                    "evidence": [{"path": "src/b.py"}],
                }
            ],
            "coupling": {"edges": [{"a": "src/a.py", "b": "src/c.py", "weight": 0.8}]},
        }
    }
    prev = preview_blast(report, ["src/a.py"], fence=["src/a.py"], auto_widen=True)
    assert "src/c.py" in prev.co_changers or "src/b.py" in prev.co_changers or prev.widened_fence
    assert prev.blast_score >= 0


def test_coverage_gate() -> None:
    before = _TestRun(runner=None, ok=True, returncode=0, output="", coverage=0.5)
    after = _TestRun(runner=None, ok=True, returncode=0, output="", coverage=0.4)
    bad = coverage_gate(after, before, require_coverage=True, min_coverage_delta=0.0)
    assert not bad["ok"]
    good = coverage_gate(
        _TestRun(runner=None, ok=True, returncode=0, output="", coverage=0.6),
        before,
        require_coverage=True,
        min_coverage_delta=0.0,
    )
    assert good["ok"]


def test_agent_eval_includes_apply(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("CODEEVOLVE_TAXONOMY_HEURISTIC", "1")
    monkeypatch.setenv("CODEEVOLVE_SKIP_HF", "1")
    monkeypatch.setenv("CODEEVOLVE_SKIP_EMBED", "1")
    monkeypatch.setenv("CODEEVOLVE_SKIP_GHSA", "1")
    monkeypatch.setenv("CODEEVOLVE_DISABLE_WEB", "1")
    from codeevolve.eval.agent_eval import AgentEvalCase, run_agent_eval

    report = run_agent_eval(
        tmp_path / "eval",
        cases=[
            AgentEvalCase("dry_run_refactor", "follow_refactor", expect_pr_pack=True, tags=["dry"]),
            AgentEvalCase(
                "apply_debt_artifact",
                "reduce_debt",
                apply=True,
                expect_pr_pack=True,
                expect_blast=True,
                expect_rollback_or_accept=True,
                tags=["apply"],
            ),
        ],
        include_apply=True,
    )
    assert report["total_cases"] == 2
    assert report["passed_cases"] >= 1
    outcomes = {c["name"]: (c.get("details") or {}).get("outcome") for c in report["cases"]}
    assert outcomes.get("dry_run_refactor") in {"delta_ready", "none"}
    assert "outcome_counts" in report
