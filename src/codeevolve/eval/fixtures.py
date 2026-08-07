"""Synthetic git fixtures with planted ground truth for evaluation."""

from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


def _git(repo: Path, *args: str, env: dict[str, str] | None = None) -> None:
    subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        capture_output=True,
        text=True,
        env=env,
    )


def _commit(repo: Path, message: str, author: str = "Dev") -> None:
    env = os.environ.copy()
    env["GIT_AUTHOR_NAME"] = author
    env["GIT_AUTHOR_EMAIL"] = f"{author.lower().replace(' ', '')}@example.com"
    env["GIT_COMMITTER_NAME"] = author
    env["GIT_COMMITTER_EMAIL"] = env["GIT_AUTHOR_EMAIL"]
    _git(repo, "add", "-A", env=env)
    _git(repo, "commit", "-m", message, env=env)


def _init(repo: Path) -> None:
    repo.mkdir(parents=True)
    _git(repo, "init")
    _git(repo, "config", "user.email", "dev@example.com")
    _git(repo, "config", "user.name", "Dev")


@dataclass
class FixtureSpec:
    name: str
    description: str
    expect_kinds: list[str] = field(default_factory=list)
    expect_hot_paths: list[str] = field(default_factory=list)
    expect_coupling_pair: tuple[str, str] | None = None
    expect_min_offboarding_drop: float | None = None
    expect_hypothesis: dict[str, str] = field(default_factory=dict)
    expect_stability_range: tuple[float, float] | None = None
    forbid_kinds: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "expect_kinds": list(self.expect_kinds),
            "expect_hot_paths": list(self.expect_hot_paths),
            "expect_coupling_pair": list(self.expect_coupling_pair) if self.expect_coupling_pair else None,
            "expect_min_offboarding_drop": self.expect_min_offboarding_drop,
            "expect_hypothesis": dict(self.expect_hypothesis),
            "expect_stability_range": list(self.expect_stability_range) if self.expect_stability_range else None,
            "forbid_kinds": list(self.forbid_kinds),
            "tags": list(self.tags),
        }


def build_coupled_hotspot(root: Path) -> FixtureSpec:
    repo = root / "coupled_hotspot"
    _init(repo)
    (repo / "src").mkdir()
    complex_body = "def run(x):\n" + "\n".join(
        f"    if x == {i}:\n        return {i}" for i in range(12)
    ) + "\n    return -1\n"
    (repo / "src" / "core.py").write_text(complex_body, encoding="utf-8")
    (repo / "src" / "api.py").write_text(
        "from .core import run\n\ndef handle():\n    return run(1)\n",
        encoding="utf-8",
    )
    _commit(repo, "feat: scaffold #1", "Alice")
    for i in range(8):
        (repo / "src" / "core.py").write_text(complex_body + f"# touch {i}\n", encoding="utf-8")
        (repo / "src" / "api.py").write_text(
            f"from .core import run\n\ndef handle():\n    return run({i})\n",
            encoding="utf-8",
        )
        _commit(repo, f"feat: co-change pair #{i + 2}", "Alice")
    (repo / "src" / "lonely.py").write_text("def x():\n    return 0\n", encoding="utf-8")
    _commit(repo, "chore: add lonely", "Bob")
    return FixtureSpec(
        name="coupled_hotspot",
        description="Planted co-change pair with complex core",
        expect_kinds=["hotspot_blast", "change_coupling"],
        expect_hot_paths=["src/core.py", "src/api.py"],
        expect_coupling_pair=("src/api.py", "src/core.py"),
        tags=["hero", "coupling", "hotspot"],
    )


def build_bus_factor_trap(root: Path) -> FixtureSpec:
    repo = root / "bus_factor_trap"
    _init(repo)
    (repo / "src").mkdir()
    (repo / "src" / "owned.py").write_text("def a():\n    return 1\n", encoding="utf-8")
    _commit(repo, "feat: init", "Solo")
    for i in range(10):
        (repo / "src" / "owned.py").write_text(f"def a():\n    return {i}\n", encoding="utf-8")
        _commit(repo, f"feat: solo edit {i}", "Solo")
    return FixtureSpec(
        name="bus_factor_trap",
        description="Single-author hotspot",
        expect_kinds=["bus_factor", "offboarding_risk", "hotspot_blast"],
        expect_hot_paths=["src/owned.py"],
        expect_min_offboarding_drop=0.5,
        tags=["hero", "offboarding"],
    )


def build_stable_mature(root: Path) -> FixtureSpec:
    repo = root / "stable_mature"
    _init(repo)
    (repo / "src").mkdir()
    (repo / "tests").mkdir()
    (repo / "src" / "lib.py").write_text("def f():\n    return 1\n", encoding="utf-8")
    (repo / "tests" / "test_lib.py").write_text("def test_f():\n    assert True\n", encoding="utf-8")
    _commit(repo, "feat: init", "Ada")
    for i, author in enumerate(["Ada", "Bea", "Cam", "Ada", "Bea", "Cam", "Ada", "Bea"]):
        if i % 2 == 0:
            (repo / "src" / "lib.py").write_text(f"def f():\n    return {i}\n", encoding="utf-8")
        else:
            (repo / "tests" / "test_lib.py").write_text(
                f"def test_f():\n    assert {i} >= 0\n",
                encoding="utf-8",
            )
        _commit(repo, f"chore: maintain {i}", author)
    return FixtureSpec(
        name="stable_mature",
        description="Distributed ownership, modest churn",
        expect_kinds=[],
        forbid_kinds=["dependency_shock", "dependency_fragility"],
        expect_stability_range=(0.25, 1.0),
        tags=["negative_control", "stability"],
    )


def build_debt_disaster(root: Path) -> FixtureSpec:
    repo = root / "debt_disaster"
    _init(repo)
    (repo / "src").mkdir()
    (repo / "src" / "messy.py").write_text(
        "def f():\n    return 1  # FIXME: debt\n# deprecated\n",
        encoding="utf-8",
    )
    _commit(repo, "feat: messy start", "Dev")
    for i in range(6):
        (repo / "src" / "messy.py").write_text(
            f"def f():\n    return {i}  # FIXME: still broken\n# deprecated path\n",
            encoding="utf-8",
        )
        _commit(repo, f"feat: messy {i}", "Dev")
    (repo / "src" / "messy.py").write_text("def f():\n    raise Exception('boom')\n", encoding="utf-8")
    _commit(repo, "feat: bad change", "Dev")
    sha = subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    _git(repo, "revert", "--no-edit", sha)
    for i in range(4):
        (repo / "src" / "messy.py").write_text(
            f"def f():\n    return {i}  # TODO: cleanup\n",
            encoding="utf-8",
        )
        _commit(repo, f"fix: patch {i}", "Dev")
    return FixtureSpec(
        name="debt_disaster",
        description="Debt markers + revert cluster",
        expect_kinds=["hotspot_blast", "revert_surface"],
        expect_hot_paths=["src/messy.py"],
        tags=["debt", "reverts"],
    )


def build_decouple_before(root: Path) -> Path:
    repo = root / "decouple_before"
    _init(repo)
    (repo / "src").mkdir()
    (repo / "src" / "a.py").write_text("def a():\n    return 1\n", encoding="utf-8")
    (repo / "src" / "b.py").write_text("def b():\n    return 2\n", encoding="utf-8")
    _commit(repo, "feat: start", "Dev")
    for i in range(6):
        (repo / "src" / "a.py").write_text(f"def a():\n    return {i}\n", encoding="utf-8")
        (repo / "src" / "b.py").write_text(f"def b():\n    return {i + 1}\n", encoding="utf-8")
        _commit(repo, f"feat: coupled #{i}", "Dev")
    return repo


def build_decouple_after(root: Path) -> Path:
    repo = root / "decouple_after"
    _init(repo)
    (repo / "src").mkdir()
    (repo / "src" / "a.py").write_text("def a():\n    return 1\n", encoding="utf-8")
    (repo / "src" / "b.py").write_text("def b():\n    return 2\n", encoding="utf-8")
    _commit(repo, "feat: start", "Dev")
    for i in range(6):
        (repo / "src" / "a.py").write_text(f"def a():\n    return {i}\n", encoding="utf-8")
        _commit(repo, f"feat: isolated a #{i}", "Dev")
    return repo


def materialize_suite(root: Path) -> list[tuple[Path, FixtureSpec]]:
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    out: list[tuple[Path, FixtureSpec]] = []
    for builder in (build_coupled_hotspot, build_bus_factor_trap, build_stable_mature, build_debt_disaster):
        spec = builder(root)
        out.append((root / spec.name, spec))
    return out
