"""Dependency / lockfile fragility analysis."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from codeevolve.gitlog import CommitRecord
from codeevolve.metrics import DEP_FILE_RE


@dataclass
class DependencyFragilityReport:
    manifests: list[str] = field(default_factory=list)
    package_count: int = 0
    lockfile_present: bool = False
    churn_commits: int = 0
    churn_rate: float = 0.0
    transitive_depth_proxy: float = 0.0
    abandoned_proxy: int = 0
    fragility: float = 0.0
    top_packages: list[dict[str, Any]] = field(default_factory=list)
    summary: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "manifests": list(self.manifests),
            "package_count": self.package_count,
            "lockfile_present": self.lockfile_present,
            "churn_commits": self.churn_commits,
            "churn_rate": self.churn_rate,
            "transitive_depth_proxy": self.transitive_depth_proxy,
            "abandoned_proxy": self.abandoned_proxy,
            "fragility": self.fragility,
            "top_packages": list(self.top_packages[:30]),
            "summary": self.summary,
        }


def _parse_requirements(text: str) -> list[str]:
    pkgs = []
    for ln in text.splitlines():
        ln = ln.strip()
        if not ln or ln.startswith("#") or ln.startswith("-"):
            continue
        name = re.split(r"[<>=!~\[]", ln, 1)[0].strip()
        if name:
            pkgs.append(name.lower())
    return pkgs


def _parse_package_json(text: str) -> list[str]:
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return []
    out = []
    for key in ("dependencies", "devDependencies", "peerDependencies"):
        block = data.get(key) or {}
        if isinstance(block, dict):
            out.extend(str(k).lower() for k in block)
    return out


def _parse_pyproject(text: str) -> list[str]:
    pkgs = []
    in_deps = False
    for ln in text.splitlines():
        if re.match(r"^\s*\[project\]", ln) or "dependencies" in ln.lower():
            in_deps = "dependencies" in ln.lower() or in_deps
        if in_deps and ("'" in ln or '"' in ln):
            m = re.search(r'["\']([A-Za-z0-9_.-]+)', ln)
            if m and m.group(1).lower() not in {"project", "dependencies"}:
                pkgs.append(m.group(1).lower())
        if in_deps and ln.strip().startswith("["):
            in_deps = "dependencies" in ln.lower()
    return pkgs


def _parse_cargo_lock(text: str) -> list[str]:
    pkgs = []
    for m in re.finditer(r'^name\s*=\s*"([^"]+)"', text, re.M):
        pkgs.append(m.group(1).lower())
    return pkgs


def _parse_go_sum(text: str) -> list[str]:
    pkgs = []
    for ln in text.splitlines():
        parts = ln.split()
        if parts:
            pkgs.append(parts[0].split("@")[0].lower())
    return list(dict.fromkeys(pkgs))


def analyze_dependency_fragility(
    repo: Path | str,
    commits: list[CommitRecord],
) -> DependencyFragilityReport:
    root = Path(repo)
    candidates = [
        "requirements.txt",
        "requirements-dev.txt",
        "pyproject.toml",
        "package.json",
        "package-lock.json",
        "yarn.lock",
        "pnpm-lock.yaml",
        "poetry.lock",
        "Cargo.toml",
        "Cargo.lock",
        "go.mod",
        "go.sum",
        "Pipfile",
        "Pipfile.lock",
        "composer.json",
        "Gemfile",
    ]
    manifests: list[str] = []
    packages: list[str] = []
    lock = False
    for name in candidates:
        fp = root / name
        if not fp.is_file():
            continue
        manifests.append(name)
        if "lock" in name.lower() or name.endswith(".sum"):
            lock = True
        try:
            text = fp.read_text(encoding="utf-8", errors="replace")[:400_000]
        except OSError:
            continue
        if name.startswith("requirements") or name == "Pipfile":
            packages.extend(_parse_requirements(text))
        elif name == "package.json":
            packages.extend(_parse_package_json(text))
        elif name == "pyproject.toml":
            packages.extend(_parse_pyproject(text))
        elif name in {"Cargo.lock", "Cargo.toml"}:
            packages.extend(_parse_cargo_lock(text) if name.endswith(".lock") else [])
            if name == "Cargo.toml":
                packages.extend(re.findall(r'^([A-Za-z0-9_-]+)\s*=', text, re.M))
        elif name == "go.sum":
            packages.extend(_parse_go_sum(text))
        elif name == "go.mod":
            packages.extend(re.findall(r"^\s*([\w./-]+)\s+v", text, re.M))

    packages = list(dict.fromkeys(packages))
    n = max(1, len(commits))
    churn_commits = sum(1 for c in commits if any(DEP_FILE_RE.search(f) for f in c.files))
    churn_rate = churn_commits / n

    # Transitive depth proxy: lockfile lines / direct packages
    lock_lines = 0
    for name in manifests:
        if "lock" in name.lower() or name.endswith(".sum"):
            try:
                lock_lines += len((root / name).read_text(encoding="utf-8", errors="replace").splitlines())
            except OSError:
                pass
    depth = min(20.0, lock_lines / max(1, len(packages))) if packages else 0.0

    # Abandoned proxy: deps that look like unmaintained placeholders (heuristic)
    abandoned = sum(1 for p in packages if any(x in p for x in ("deprecated", "legacy", "old-", "-old")))

    fragility = min(
        1.0,
        0.35 * min(1.0, churn_rate * 4)
        + 0.35 * min(1.0, depth / 10.0)
        + 0.15 * (0.0 if lock else 0.8)
        + 0.15 * min(1.0, abandoned / 3.0)
        + 0.1 * min(1.0, len(packages) / 80.0),
    )

    top = [{"name": p, "rank": i + 1} for i, p in enumerate(packages[:30])]
    return DependencyFragilityReport(
        manifests=manifests,
        package_count=len(packages),
        lockfile_present=lock,
        churn_commits=churn_commits,
        churn_rate=round(churn_rate, 4),
        transitive_depth_proxy=round(depth, 3),
        abandoned_proxy=abandoned,
        fragility=round(fragility, 4),
        top_packages=top,
        summary=(
            f"{len(packages)} packages across {len(manifests)} manifests; "
            f"fragility={fragility:.2f}; lockfile={'yes' if lock else 'no'}"
        ),
    )
