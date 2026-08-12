"""Objective coding agent — dry-run loop + scoring."""

from __future__ import annotations

import json
from pathlib import Path

from codeevolve.agent import EvolveAgent, Objective, run_agent, score_objective
from codeevolve.agent.objective import ranks_steps_for_objective
from codeevolve.agent.workspace import Workspace, parse_unified_diff
from codeevolve.provenance.schema import MCP_TOOLS, dispatch_mcp_tool


def test_objective_parse_and_score() -> None:
    obj = Objective.parse("reduce_debt")
    assert obj.kind == "reduce_debt"
    custom = Objective.parse("metric:stability.composite:max:0.9")
    assert custom.kind == "custom" and custom.higher_better and custom.target == 0.9
    before = {"debt": {"score": 0.5}, "stability": {"composite": 0.4}, "risk": {"failure_points": [1, 2]}}
    after = {"debt": {"score": 0.3}, "stability": {"composite": 0.4}, "risk": {"failure_points": [1]}}
    scored = score_objective(obj, after, before, diff={"worsened": []})
    assert scored.improved and scored.constraints_ok


def test_ranks_steps_from_waves() -> None:
    plan = {
        "waves": [
            {"name": "evolve", "steps": [{"id": "R2", "wave": "evolve", "paths": ["b.py"]}]},
            {"name": "stabilize", "steps": [{"id": "R1", "wave": "stabilize", "paths": ["a.py"]}]},
        ]
    }
    ordered = ranks_steps_for_objective(Objective(kind="follow_refactor"), plan)
    assert ordered[0]["id"] == "R1"


def test_workspace_fence_and_diff_parse(tmp_path: Path) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "a.py").write_text("x = 1\n", encoding="utf-8")
    ws = Workspace(tmp_path, fence_paths=["src/a.py"])
    assert ws.allowed("src/a.py")
    assert not ws.allowed("secret.env")
    text = "FILE: src/a.py\nx = 2\nEND FILE\n"
    parsed = parse_unified_diff(text)
    assert parsed and parsed[0][0] == "src/a.py" and "x = 2" in parsed[0][1]


def test_agent_dry_run(sample_repo: Path, monkeypatch) -> None:
    monkeypatch.setenv("CODEEVOLVE_TAXONOMY_HEURISTIC", "1")
    monkeypatch.setenv("CODEEVOLVE_SKIP_HF", "1")
    monkeypatch.setenv("CODEEVOLVE_SKIP_EMBED", "1")
    monkeypatch.setenv("CODEEVOLVE_SKIP_GHSA", "1")
    monkeypatch.setenv("CODEEVOLVE_DISABLE_WEB", "1")
    run = run_agent(
        sample_repo,
        "follow_refactor",
        max_rounds=1,
        apply=False,
        max_commits=50,
        llm="heuristic",  # unit test: no network / HF download
        allow_web=False,
        max_subagents=1,
    )
    assert run.rounds
    assert (sample_repo / ".codeevolve" / "agent" / "run.json").is_file()
    proposal = run.rounds[0].proposal
    assert proposal is not None
    assert "stance" in proposal
    # dry-run must not apply
    assert run.rounds[0].applied is False


def test_agent_apply_heuristic_artifact(sample_repo: Path, monkeypatch) -> None:
    monkeypatch.setenv("CODEEVOLVE_TAXONOMY_HEURISTIC", "1")
    monkeypatch.setenv("CODEEVOLVE_SKIP_HF", "1")
    monkeypatch.setenv("CODEEVOLVE_SKIP_EMBED", "1")
    monkeypatch.setenv("CODEEVOLVE_SKIP_GHSA", "1")
    monkeypatch.setenv("CODEEVOLVE_DISABLE_WEB", "1")
    agent = EvolveAgent(
        sample_repo,
        objective=Objective.parse("reduce_debt"),
        apply=True,
        max_commits=50,
        llm="heuristic",
        allow_web=False,
        max_subagents=1,
        use_worktree=False,
        run_tests_on_apply=False,
        auto_approve=True,
    )
    run = agent.run(max_rounds=1)
    assert run.final_report_path
    assert run.budget is not None
    # Either accepted an artifact or deferred/insufficient — must not crash
    assert run.status in {"ok", "exhausted", "target_reached", "budget_stop"}


def test_mcp_tool_catalog_includes_evolve() -> None:
    names = {t["name"] for t in MCP_TOOLS}
    assert "evolve_toward_objective" in names


def test_mcp_evolve_dry_run(sample_repo: Path, tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("CODEEVOLVE_TAXONOMY_HEURISTIC", "1")
    monkeypatch.setenv("CODEEVOLVE_SKIP_HF", "1")
    monkeypatch.setenv("CODEEVOLVE_SKIP_EMBED", "1")
    monkeypatch.setenv("CODEEVOLVE_SKIP_GHSA", "1")
    out = tmp_path / "agent_run.json"
    result = dispatch_mcp_tool(
        "evolve_toward_objective",
        {
            "repo": str(sample_repo),
            "objective": "follow_refactor",
            "max_rounds": 1,
            "max_commits": 50,
            "apply": False,
            "llm": "heuristic",
            "allow_web": False,
            "max_subagents": 1,
            "out": str(out),
        },
    )
    assert "rounds" in result
    assert out.is_file()
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["objective"]["kind"] == "follow_refactor"


def test_cli_agent(sample_repo: Path, tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("CODEEVOLVE_TAXONOMY_HEURISTIC", "1")
    monkeypatch.setenv("CODEEVOLVE_SKIP_HF", "1")
    monkeypatch.setenv("CODEEVOLVE_SKIP_EMBED", "1")
    monkeypatch.setenv("CODEEVOLVE_SKIP_GHSA", "1")
    from codeevolve.cli import main

    out = tmp_path / "run.json"
    code = main(
        [
            "--repo",
            str(sample_repo),
            "agent",
            "--objective",
            "reduce_debt",
            "--llm",
            "heuristic",
            "--no-web",
            "--max-subagents",
            "1",
            "--max-rounds",
            "1",
            "--max-commits",
            "50",
            "--out",
            str(out),
        ]
    )
    assert code == 0
    assert out.exists()
