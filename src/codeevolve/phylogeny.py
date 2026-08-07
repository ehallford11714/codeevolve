"""Phylogeny of commit history + ecological stage classification."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from codeevolve.gitlog import CommitRecord
from codeevolve.metrics import MetricBundle

EcologicalStage = Literal[
    "pioneer",       # early sparse exploration
    "growth",        # rapid feature expansion
    "disturbance",   # high revert / churn shock
    "consolidation", # refactor/test/docs rise, churn cools
    "maturity",      # stable, low revert, steady maintenance
    "decline",       # activity collapse or rising debt signals
]


@dataclass
class PhyloNode:
    sha: str
    subject: str
    parent_shas: list[str] = field(default_factory=list)
    children: list[str] = field(default_factory=list)
    generation: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "sha": self.sha,
            "subject": self.subject,
            "parent_shas": list(self.parent_shas),
            "children": list(self.children),
            "generation": self.generation,
        }


@dataclass
class PhylogenyReport:
    nodes: list[PhyloNode]
    roots: list[str]
    max_generation: int
    branch_factor: float
    merge_count: int
    stages: list[dict[str, Any]]
    current_stage: EcologicalStage
    stage_rationale: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "roots": list(self.roots),
            "max_generation": self.max_generation,
            "branch_factor": self.branch_factor,
            "merge_count": self.merge_count,
            "current_stage": self.current_stage,
            "stage_rationale": self.stage_rationale,
            "stages": list(self.stages),
            "nodes": [n.to_dict() for n in self.nodes[:200]],  # cap for report size
            "node_count": len(self.nodes),
        }


def build_phylogeny(commits: list[CommitRecord]) -> tuple[list[PhyloNode], list[str], int, float, int]:
    by_sha = {c.sha: c for c in commits}
    short = {c.sha[:7]: c.sha for c in commits}
    nodes: dict[str, PhyloNode] = {}
    for c in commits:
        nodes[c.sha] = PhyloNode(sha=c.sha, subject=c.subject, parent_shas=list(c.parents))

    for c in commits:
        for p in c.parents:
            full = p if p in nodes else short.get(p[:7])
            if full and full in nodes:
                nodes[full].children.append(c.sha)

    # generations via BFS from roots (no known parent in set)
    roots = [sha for sha, n in nodes.items() if not any(
        (p in nodes) or (p[:7] in short) for p in n.parent_shas
    )]
    if not roots and nodes:
        # fallback oldest
        oldest = min(commits, key=lambda c: c.timestamp)
        roots = [oldest.sha]

    from collections import deque

    q = deque([(r, 0) for r in roots])
    seen: set[str] = set()
    max_gen = 0
    while q:
        sha, gen = q.popleft()
        if sha in seen or sha not in nodes:
            continue
        seen.add(sha)
        nodes[sha].generation = gen
        max_gen = max(max_gen, gen)
        for ch in nodes[sha].children:
            q.append((ch, gen + 1))

    merge_count = sum(1 for c in commits if len(c.parents) > 1)
    branch_factor = (sum(len(n.children) for n in nodes.values()) / max(1, len(nodes)))
    return list(nodes.values()), roots, max_gen, round(branch_factor, 4), merge_count


def classify_ecological_stages(
    commits: list[CommitRecord],
    metrics: MetricBundle,
    *,
    windows: int = 5,
) -> tuple[list[dict[str, Any]], EcologicalStage, str]:
    if not commits:
        return [], "pioneer", "no history"

    chronological = sorted(commits, key=lambda c: c.timestamp)
    n = len(chronological)
    size = max(1, n // windows)
    stages: list[dict[str, Any]] = []
    for i in range(windows):
        chunk = chronological[i * size : (i + 1) * size] if i < windows - 1 else chronological[i * size :]
        if not chunk:
            continue
        churn = sum(c.insertions + c.deletions for c in chunk) / max(1, len(chunk))
        reverts = sum(1 for c in chunk if c.is_revert) / max(1, len(chunk))
        subjects = " ".join(c.subject.lower() for c in chunk)
        refactorish = sum(w in subjects for w in ("refactor", "cleanup", "test", "docs")) / max(1, len(chunk))
        if reverts > 0.15 or churn > 400:
            stage: EcologicalStage = "disturbance"
        elif i == 0 and n < 40:
            stage = "pioneer"
        elif churn > 120 and reverts < 0.08:
            stage = "growth"
        elif refactorish > 0.25 and churn < 100:
            stage = "consolidation"
        elif churn < 40 and reverts < 0.05:
            stage = "maturity"
        elif churn < 15 and i == windows - 1:
            stage = "decline"
        else:
            stage = "growth"
        stages.append(
            {
                "window": i,
                "stage": stage,
                "commits": len(chunk),
                "avg_churn": round(churn, 2),
                "revert_rate": round(reverts, 4),
                "start": chunk[0].timestamp.isoformat(),
                "end": chunk[-1].timestamp.isoformat(),
            }
        )

    # current stage: last window, adjusted by global metrics
    current: EcologicalStage = stages[-1]["stage"] if stages else "pioneer"
    rationale = f"latest window classified as {current}"
    if metrics.revert_rate > 0.12:
        current = "disturbance"
        rationale = f"global revert_rate={metrics.revert_rate} indicates disturbance"
    elif metrics.code_stability > 0.75 and metrics.momentum < 0.2:
        current = "maturity"
        rationale = f"high stability ({metrics.code_stability}) and low momentum"
    elif metrics.momentum > 0.8 and metrics.improvement_trend < 0:
        current = "growth"
        rationale = "high momentum with weak improvement trend — expansion phase"
    elif metrics.improvement_trend > 0.15:
        current = "consolidation"
        rationale = f"positive improvement_trend={metrics.improvement_trend}"

    return stages, current, rationale


def analyze_phylogeny(commits: list[CommitRecord], metrics: MetricBundle) -> PhylogenyReport:
    nodes, roots, max_gen, branch_factor, merges = build_phylogeny(commits)
    stages, current, rationale = classify_ecological_stages(commits, metrics)
    return PhylogenyReport(
        nodes=nodes,
        roots=roots,
        max_generation=max_gen,
        branch_factor=branch_factor,
        merge_count=merges,
        stages=stages,
        current_stage=current,
        stage_rationale=rationale,
    )
