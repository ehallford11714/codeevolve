"""Test/CI detection and scoring for agent objectives."""

from __future__ import annotations

import json
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from codeevolve.ci import evaluate_ci_gate


@dataclass
class TestRunner:
    name: str
    command: str
    kind: str  # pytest|npm|cargo|go|generic

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "command": self.command, "kind": self.kind}


@dataclass
class TestRunResult:
    runner: dict[str, Any] | None
    ok: bool
    returncode: int
    output: str
    passed: int | None = None
    failed: int | None = None
    coverage: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "runner": self.runner,
            "ok": self.ok,
            "returncode": self.returncode,
            "passed": self.passed,
            "failed": self.failed,
            "coverage": self.coverage,
            "output_tail": self.output[-2000:],
        }


def pytest_has_cov(repo: Path | str) -> bool:
    """True if pytest-cov appears available / configured."""
    root = Path(repo)
    try:
        import importlib.util

        if importlib.util.find_spec("pytest_cov") is not None:
            return True
    except Exception:
        pass
    for name in ("pytest.ini", "pyproject.toml", "setup.cfg", ".coveragerc"):
        p = root / name
        if not p.is_file():
            continue
        try:
            text = p.read_text(encoding="utf-8", errors="replace").lower()
        except OSError:
            continue
        if "pytest-cov" in text or "--cov" in text or "[coverage" in text:
            return True
    return False


def detect_test_runner(repo: Path | str, *, with_coverage: bool = False) -> TestRunner | None:
    root = Path(repo)
    cov = with_coverage and pytest_has_cov(root)
    pytest_cmd = "python -m pytest -q --cov=. --cov-report=term-missing" if cov else "python -m pytest -q"
    if (root / "pytest.ini").exists() or (root / "pyproject.toml").exists() or (root / "tests").is_dir():
        # prefer pytest if tests/ or pytest config
        if (root / "tests").is_dir() or (root / "pytest.ini").exists():
            return TestRunner("pytest", pytest_cmd, "pytest")
        # pyproject may still be a python pkg
        try:
            text = (root / "pyproject.toml").read_text(encoding="utf-8", errors="replace")
            if "pytest" in text or 'requires-python' in text:
                return TestRunner("pytest", pytest_cmd, "pytest")
        except OSError:
            pass
    if (root / "package.json").exists():
        try:
            pkg = json.loads((root / "package.json").read_text(encoding="utf-8"))
            scripts = pkg.get("scripts") or {}
            if "test" in scripts:
                return TestRunner("npm-test", "npm test --silent", "npm")
        except (OSError, json.JSONDecodeError):
            return TestRunner("npm-test", "npm test --silent", "npm")
    if (root / "Cargo.toml").exists():
        return TestRunner("cargo-test", "cargo test --quiet", "cargo")
    if (root / "go.mod").exists():
        return TestRunner("go-test", "go test ./...", "go")
    return None


def _parse_pytest(output: str) -> tuple[int | None, int | None]:
    # "3 passed" / "1 failed, 2 passed"
    passed = failed = None
    m = re.search(r"(\d+)\s+passed", output)
    if m:
        passed = int(m.group(1))
    m = re.search(r"(\d+)\s+failed", output)
    if m:
        failed = int(m.group(1))
    return passed, failed


def _parse_coverage(output: str) -> float | None:
    m = re.search(r"TOTAL\s+\d+\s+\d+\s+(\d+)%", output)
    if m:
        return float(m.group(1)) / 100.0
    m = re.search(r"coverage[:\s]+(\d+(?:\.\d+)?)%", output, re.I)
    if m:
        return float(m.group(1)) / 100.0
    return None


def run_tests(
    repo: Path | str,
    *,
    command: str | None = None,
    timeout: int = 300,
) -> TestRunResult:
    root = Path(repo)
    runner = detect_test_runner(root)
    cmd = command or (runner.command if runner else None)
    if not cmd:
        return TestRunResult(runner=None, ok=True, returncode=0, output="no test runner detected")
    try:
        proc = subprocess.run(
            cmd,
            shell=True,
            cwd=str(root),
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return TestRunResult(
            runner=runner.to_dict() if runner else None,
            ok=False,
            returncode=-1,
            output=str(exc),
        )
    out = (proc.stdout or "") + "\n" + (proc.stderr or "")
    passed = failed = None
    if runner and runner.kind == "pytest":
        passed, failed = _parse_pytest(out)
    cov = _parse_coverage(out)
    return TestRunResult(
        runner=runner.to_dict() if runner else {"name": "custom", "command": cmd, "kind": "generic"},
        ok=proc.returncode == 0,
        returncode=proc.returncode,
        output=out,
        passed=passed,
        failed=failed,
        coverage=cov,
    )


def score_tests(
    current: TestRunResult,
    previous: TestRunResult | None = None,
) -> dict[str, Any]:
    """Return objective-style score: higher is better (passed - failed + coverage)."""
    cur = 0.0
    if current.ok:
        cur += 1.0
    if current.passed is not None:
        cur += min(current.passed, 50) * 0.02
    if current.failed:
        cur -= current.failed * 0.1
    if current.coverage is not None:
        cur += current.coverage
    prev = None
    improved = False
    if previous is not None:
        prev_s = score_tests(previous)["value"]
        prev = prev_s
        improved = cur > prev_s + 1e-9
    return {
        "value": round(cur, 4),
        "previous": prev,
        "improved": improved,
        "ok": current.ok,
        "coverage": current.coverage,
        "passed": current.passed,
        "failed": current.failed,
    }


def coverage_gate(
    current: TestRunResult,
    previous: TestRunResult | None = None,
    *,
    require_coverage: bool = False,
    min_coverage_delta: float = 0.0,
) -> dict[str, Any]:
    """Gate on coverage: optionally require coverage present and non-decreasing."""
    cur = current.coverage
    prev = previous.coverage if previous else None
    ok = True
    notes: list[str] = []
    if require_coverage and cur is None:
        ok = False
        notes.append("coverage required but not reported (install pytest-cov or set verify_cmd with --cov)")
    if cur is not None and prev is not None and min_coverage_delta is not None:
        delta = cur - prev
        if delta + 1e-12 < min_coverage_delta:
            ok = False
            notes.append(f"coverage delta {delta:.4f} < min {min_coverage_delta}")
        else:
            notes.append(f"coverage {prev:.3f} → {cur:.3f}")
    elif cur is not None:
        notes.append(f"coverage={cur:.3f}")
    return {
        "ok": ok,
        "coverage": cur,
        "previous_coverage": prev,
        "min_coverage_delta": min_coverage_delta,
        "notes": notes,
    }


def score_with_ci_gate(
    report: dict[str, Any],
    previous: dict[str, Any] | None = None,
    *,
    test_result: TestRunResult | None = None,
    previous_tests: TestRunResult | None = None,
    require_coverage: bool = False,
    min_coverage_delta: float = 0.0,
) -> dict[str, Any]:
    gate = evaluate_ci_gate(report, previous=previous)
    payload = gate.to_dict()
    if test_result is not None:
        payload["tests"] = test_result.to_dict()
        payload["test_score"] = score_tests(test_result, previous_tests)
        if not test_result.ok:
            payload["ok"] = False
            payload["failures"] = list(payload.get("failures") or []) + ["tests failed"]
        cov = coverage_gate(
            test_result,
            previous_tests,
            require_coverage=require_coverage,
            min_coverage_delta=min_coverage_delta,
        )
        payload["coverage_gate"] = cov
        if not cov.get("ok", True):
            payload["ok"] = False
            payload["failures"] = list(payload.get("failures") or []) + list(cov.get("notes") or [])
    return payload
