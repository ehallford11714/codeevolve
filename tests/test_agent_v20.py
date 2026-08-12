"""v0.20 — patch engine, gitwork, tests, toolcall, coord, budget, memory retrieve, agent eval."""

from __future__ import annotations

from pathlib import Path

from codeevolve.agent.budget import Budget, BudgetTracker, approve_edits, estimate_cost
from codeevolve.agent.coord import PathLockTable, merge_findings, run_subagents_coordinated
from codeevolve.agent.gitwork import begin_session, end_session, is_git_repo, working_root
from codeevolve.agent.kernel import make_kernel
from codeevolve.agent.memory import AgentMemory
from codeevolve.agent.objective import Objective, score_objective
from codeevolve.agent.patch import apply_hunks_to_text, apply_patches, parse_unified_patches, symbol_fence_for
from codeevolve.agent.subagents import SubAgent, SubAgentResult
from codeevolve.agent.testing import detect_test_runner, score_tests
from codeevolve.agent.toolcall import TOOL_SCHEMAS
from codeevolve.agent.workspace import Workspace
from codeevolve.eval.agent_eval import run_agent_eval


def test_patch_hunk_apply_fail_closed(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text("def f():\n    return 1\n", encoding="utf-8")
    ws = Workspace(tmp_path)
    diff = (
        "diff --git a/a.py b/a.py\n"
        "--- a/a.py\n"
        "+++ b/a.py\n"
        "@@ -1,2 +1,2 @@\n"
        " def f():\n"
        "-    return 1\n"
        "+    return 2\n"
    )
    patches = parse_unified_patches(diff)
    assert patches and patches[0].hunks
    result = apply_patches(ws, patches, snapshot_dir=tmp_path / "snap")
    assert "return 2" in (tmp_path / "a.py").read_text(encoding="utf-8")
    assert result.applied

    bad = (
        "diff --git a/a.py b/a.py\n"
        "--- a/a.py\n"
        "+++ b/a.py\n"
        "@@ -1,2 +1,2 @@\n"
        " def f():\n"
        "-    return 999\n"
        "+    return 3\n"
    )
    bad_patches = parse_unified_patches(bad)
    result2 = apply_patches(ws, bad_patches, snapshot_dir=tmp_path / "snap2", fail_closed=True)
    assert not result2.applied
    assert "return 2" in (tmp_path / "a.py").read_text(encoding="utf-8")


def test_symbol_fence(tmp_path: Path) -> None:
    src = "def outer():\n    return 1\n\ndef inner():\n    return 2\n"
    (tmp_path / "m.py").write_text(src, encoding="utf-8")
    fence = symbol_fence_for("m.py", src, qualname="outer")
    assert fence is not None
    assert fence.start_line == 1


def test_apply_hunks_to_text() -> None:
    from codeevolve.agent.patch import Hunk

    original = "a\nb\nc\n"
    hunk = Hunk(2, 1, 2, 1, ["-b", "+B"])
    new, err = apply_hunks_to_text(original, [hunk])
    assert err is None and new is not None
    assert "B" in new


def test_git_session(tmp_path: Path) -> None:
    import subprocess

    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(["git", "-C", str(tmp_path), "config", "user.email", "t@e.com"], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(tmp_path), "config", "user.name", "t"], check=True, capture_output=True)
    (tmp_path / "f.txt").write_text("x\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(tmp_path), "add", "-A"], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(tmp_path), "commit", "-m", "i"], check=True, capture_output=True)
    assert is_git_repo(tmp_path)
    sess = begin_session(tmp_path, use_worktree=True)
    assert sess.work_branch.startswith("codeevolve/")
    root = working_root(sess)
    assert root.exists()
    end_session(sess, keep_branch=False, restore_base=True)


def test_detect_pytest_runner(tmp_path: Path) -> None:
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_x.py").write_text("def test_ok():\n    assert True\n", encoding="utf-8")
    runner = detect_test_runner(tmp_path)
    assert runner and runner.kind == "pytest"


def test_pass_tests_objective() -> None:
    obj = Objective.parse("pass_tests")
    assert obj.kind == "pass_tests"
    before = {"tests": {"score": 0.2}}
    after = {"tests": {"score": 0.8}}
    scored = score_objective(obj, after, before, diff={"worsened": []})
    assert scored.improved


def test_score_tests_helper() -> None:
    from codeevolve.agent.testing import TestRunResult

    r = TestRunResult(runner={"name": "pytest"}, ok=True, returncode=0, output="2 passed", passed=2, failed=0)
    s = score_tests(r)
    assert s["value"] > 0.5


def test_tool_schemas() -> None:
    assert TOOL_SCHEMAS and any(s.get("name") == "apply_patch" for s in TOOL_SCHEMAS)
    assert any(s.get("name") == "grep" for s in TOOL_SCHEMAS)


def test_path_locks_and_merge() -> None:
    table = PathLockTable()
    ok, _ = table.try_acquire("a", ["src/a.py"])
    assert ok
    ok2, blocked = table.try_acquire("b", ["src/a.py"])
    assert not ok2 and blocked
    table.release("a")

    results = [
        SubAgentResult(
            id="1",
            kernel={"name": "stabilize", "path": "src/a.py"},
            status="ok",
            findings=["debt in a"],
            reflection={"stance": "continue"},
        ),
        SubAgentResult(
            id="2",
            kernel={"name": "pay_down", "path": "src/b.py"},
            status="ok",
            findings=["todo marker"],
            reflection={"stance": "continue"},
        ),
    ]
    merged = merge_findings(results)
    assert merged["subagent_count"] == 2
    assert len(merged["findings"]) >= 2


def test_coord_parallel_spawn(tmp_path: Path) -> None:
    parent = Objective.parse("reduce_debt")
    kernels = [
        make_kernel("investigate", parent),
        make_kernel("pay_down", parent),
    ]

    def make(ker):
        return SubAgent(tmp_path, ker, allow_web=False, llm="heuristic")

    results, merged = run_subagents_coordinated(
        tmp_path,
        kernels,
        make_subagent=make,
        parallel=True,
        max_workers=2,
    )
    assert len(results) == 2
    assert merged["subagent_count"] == 2


def test_budget_and_hitl() -> None:
    tr = BudgetTracker(budget=Budget(max_rounds=1, max_cost_usd=0.01, max_wall_seconds=3600))
    ok, _ = tr.check()
    assert ok
    tr.tick_round()
    ok2, reason = tr.check()
    assert not ok2 and reason
    assert estimate_cost("openai", "gpt-4o", 1000, 1000) > 0
    allowed, why = approve_edits({"step_id": "R1", "edits": []}, interactive=False, auto_approve=True)
    assert allowed and "auto" in why
    denied, _ = approve_edits({"step_id": "R1"}, interactive=False, auto_approve=False, preapproved=None)
    assert not denied


def test_embedded_memory_retrieve(tmp_path: Path) -> None:
    mem = AgentMemory(persist_dir=tmp_path)
    mem.add("debt hotspot in src/core.py TODO refactor", kind="episodic", tags=["debt", "src/core.py"])
    mem.add("stability improved after fence", kind="semantic", tags=["stability"])
    hits = mem.retrieve("debt refactor core", limit=4)
    assert hits
    block = mem.retrieve_block("debt", path="src/core.py")
    assert "debt" in block.lower() or "core" in block.lower() or "no embedded" in block


def test_agent_eval_suite(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("CODEEVOLVE_TAXONOMY_HEURISTIC", "1")
    monkeypatch.setenv("CODEEVOLVE_SKIP_HF", "1")
    monkeypatch.setenv("CODEEVOLVE_SKIP_EMBED", "1")
    monkeypatch.setenv("CODEEVOLVE_SKIP_GHSA", "1")
    monkeypatch.setenv("CODEEVOLVE_DISABLE_WEB", "1")
    report = run_agent_eval(tmp_path / "eval")
    assert report["suite"] == "agent"
    assert report["total_cases"] >= 1
    assert report["overall_score"] >= 0.0
