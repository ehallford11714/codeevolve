"""Subagent coordination: path locks, finding merge, optional parallel spawn."""

from __future__ import annotations

import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from codeevolve.agent.kernel import KernelObjective
from codeevolve.agent.subagents import SubAgent, SubAgentResult


@dataclass
class PathLock:
    path: str
    owner: str
    acquired_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {"path": self.path, "owner": self.owner, "acquired_at": self.acquired_at}


class PathLockTable:
    def __init__(self) -> None:
        self._locks: dict[str, PathLock] = {}
        self._mu = threading.Lock()

    def try_acquire(self, owner: str, paths: list[str]) -> tuple[bool, list[str]]:
        normed = [p.replace("\\", "/").lstrip("./") for p in paths if p]
        with self._mu:
            blocked = []
            for p in normed:
                held = self._locks.get(p)
                if held and held.owner != owner:
                    blocked.append(p)
                # also block if parent/child held by other
                for hp, lock in self._locks.items():
                    if lock.owner == owner:
                        continue
                    if p == hp or p.startswith(hp.rstrip("/") + "/") or hp.startswith(p.rstrip("/") + "/"):
                        blocked.append(p)
            if blocked:
                return False, sorted(set(blocked))
            for p in normed:
                self._locks[p] = PathLock(path=p, owner=owner)
            return True, []

    def release(self, owner: str) -> None:
        with self._mu:
            self._locks = {k: v for k, v in self._locks.items() if v.owner != owner}

    def to_dict(self) -> dict[str, Any]:
        with self._mu:
            return {"locks": [v.to_dict() for v in self._locks.values()]}


def merge_findings(results: list[SubAgentResult]) -> dict[str, Any]:
    """Synthesize subagent outputs into a single finding pack."""
    by_kernel: dict[str, list[str]] = {}
    all_findings: list[str] = []
    conflicts: list[str] = []
    path_owners: dict[str, str] = {}
    for r in results:
        name = str((r.kernel or {}).get("name") or r.id)
        by_kernel.setdefault(name, []).extend(r.findings)
        all_findings.extend(f"[{name}] {f}" for f in r.findings)
        # path hints from kernel
        path = (r.kernel or {}).get("path")
        if path:
            p = str(path)
            if p in path_owners and path_owners[p] != name:
                conflicts.append(f"path {p} touched by {path_owners[p]} and {name}")
            path_owners[p] = name
    # dedupe findings
    seen: set[str] = set()
    uniq: list[str] = []
    for f in all_findings:
        if f not in seen:
            seen.add(f)
            uniq.append(f)
    return {
        "findings": uniq[:80],
        "by_kernel": {k: v[:20] for k, v in by_kernel.items()},
        "path_owners": path_owners,
        "conflicts": conflicts,
        "subagent_count": len(results),
        "statuses": {str((r.kernel or {}).get("name")): r.status for r in results},
    }


def run_subagents_coordinated(
    repo: Path | str,
    kernels: list[KernelObjective],
    *,
    make_subagent: Callable[[KernelObjective], SubAgent],
    parallel: bool = False,
    max_workers: int = 3,
    locks: PathLockTable | None = None,
) -> tuple[list[SubAgentResult], dict[str, Any]]:
    """Run subagents sequentially or in parallel with path locks."""
    table = locks or PathLockTable()
    results: list[SubAgentResult] = []

    def _run_one(ker: KernelObjective) -> SubAgentResult:
        owner = f"{ker.name}:{id(ker)}"
        paths = [ker.path] if ker.path else []
        ok, blocked = table.try_acquire(owner, paths) if paths else (True, [])
        if not ok:
            return SubAgentResult(
                id=owner[:10],
                kernel=ker.to_dict(),
                status="blocked",
                findings=[f"path lock blocked: {blocked}"],
                reflection={"stance": "stop", "insights": [f"blocked on {blocked}"]},
            )
        try:
            sub = make_subagent(ker)
            return sub.run()
        finally:
            table.release(owner)

    if parallel and len(kernels) > 1:
        with ThreadPoolExecutor(max_workers=min(max_workers, len(kernels))) as ex:
            futs = {ex.submit(_run_one, k): k for k in kernels}
            for fut in as_completed(futs):
                results.append(fut.result())
    else:
        for ker in kernels:
            results.append(_run_one(ker))

    merged = merge_findings(results)
    merged["locks"] = table.to_dict()
    return results, merged


def write_merge_report(merged: dict[str, Any], dest: Path | str) -> None:
    Path(dest).parent.mkdir(parents=True, exist_ok=True)
    Path(dest).write_text(json.dumps(merged, indent=2, default=str), encoding="utf-8")
