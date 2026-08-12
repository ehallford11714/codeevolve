"""Objective specs and scoring against CodeEvolve reports / diffs."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal


ObjectiveKind = Literal[
    "reduce_debt",
    "raise_stability",
    "reduce_risk",
    "stabilize_path",
    "follow_refactor",
    "pass_tests",
    "custom",
]


@dataclass
class Objective:
    """What the coding agent optimizes for across sense→act→verify rounds."""

    kind: ObjectiveKind = "follow_refactor"
    # Optional focus (path fence / clade)
    path: str | None = None
    clade: str | None = None
    # Prefer a refactor wave when kind is follow_refactor
    wave: str | None = None
    # custom metric: dotted path into report dict, higher_better, optional target
    metric: str | None = None
    higher_better: bool = True
    target: float | None = None
    # Soft constraints from CI-style gates
    min_stability: float = 0.0
    max_new_worsened: int = 3
    # pass_tests: require coverage report / non-decreasing coverage
    require_coverage: bool = False
    min_coverage_delta: float = 0.0
    description: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "path": self.path,
            "clade": self.clade,
            "wave": self.wave,
            "metric": self.metric,
            "higher_better": self.higher_better,
            "target": self.target,
            "min_stability": self.min_stability,
            "max_new_worsened": self.max_new_worsened,
            "require_coverage": self.require_coverage,
            "min_coverage_delta": self.min_coverage_delta,
            "description": self.description or self.default_description(),
        }

    def default_description(self) -> str:
        if self.kind == "reduce_debt":
            return "Lower technical debt.score without worsening stability"
        if self.kind == "raise_stability":
            return "Raise stability.composite / metrics.code_stability"
        if self.kind == "reduce_risk":
            return "Reduce failure-point count / top severity"
        if self.kind == "stabilize_path":
            return f"Stabilize hotspot path {self.path or '(unspecified)'}"
        if self.kind == "follow_refactor":
            w = self.wave or "stabilize→contain→pay_down→evolve"
            return f"Execute next evidence-linked refactor step ({w})"
        if self.kind == "pass_tests":
            return "Make detected test suite pass; improve coverage when available"
        if self.kind == "custom" and self.metric:
            direction = "maximize" if self.higher_better else "minimize"
            tgt = f" toward {self.target}" if self.target is not None else ""
            return f"{direction} report.{self.metric}{tgt}"
        return "Improve evolutionary health per CodeEvolve signals"

    @classmethod
    def parse(cls, spec: str, *, path: str | None = None, wave: str | None = None) -> "Objective":
        """Parse CLI-friendly specs: reduce_debt | raise_stability | metric:debt.score:min | ..."""
        raw = (spec or "follow_refactor").strip()
        lower = raw.lower()
        if lower in {"reduce_debt", "debt"}:
            return cls(kind="reduce_debt", path=path, wave=wave)
        if lower in {"raise_stability", "stability"}:
            return cls(kind="raise_stability", path=path, wave=wave)
        if lower in {"reduce_risk", "risk"}:
            return cls(kind="reduce_risk", path=path, wave=wave)
        if lower in {"stabilize_path", "path"}:
            return cls(kind="stabilize_path", path=path, wave=wave)
        if lower in {"follow_refactor", "refactor"}:
            return cls(kind="follow_refactor", path=path, wave=wave)
        if lower in {"pass_tests", "tests", "test"}:
            return cls(kind="pass_tests", path=path, wave=wave)
        if lower in {"pass_tests+cov", "tests+cov", "coverage"}:
            return cls(
                kind="pass_tests",
                path=path,
                wave=wave,
                require_coverage=True,
                min_coverage_delta=0.0,
            )
        if lower.startswith("metric:"):
            # metric:debt.score:min[:target] or metric:stability.composite:max
            parts = raw.split(":")
            metric = parts[1] if len(parts) > 1 else "debt.score"
            direction = (parts[2] if len(parts) > 2 else "min").lower()
            higher = direction in {"max", "maximize", "higher", "up"}
            target = float(parts[3]) if len(parts) > 3 else None
            return cls(
                kind="custom",
                metric=metric,
                higher_better=higher,
                target=target,
                path=path,
                wave=wave,
            )
        return cls(kind="follow_refactor", path=path, wave=wave, description=raw)


@dataclass
class ObjectiveScore:
    value: float
    previous: float | None
    delta: float | None
    improved: bool
    reached_target: bool
    constraints_ok: bool
    notes: list[str] = field(default_factory=list)
    signals: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "value": self.value,
            "previous": self.previous,
            "delta": self.delta,
            "improved": self.improved,
            "reached_target": self.reached_target,
            "constraints_ok": self.constraints_ok,
            "notes": list(self.notes),
            "signals": dict(self.signals),
        }


def _get_path(data: dict[str, Any], dotted: str, default: float = 0.0) -> float:
    cur: Any = data
    for part in dotted.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return default
        cur = cur[part]
    try:
        return float(cur)
    except (TypeError, ValueError):
        return default


def primary_metric(objective: Objective) -> tuple[str, bool]:
    """Return (dotted metric path, higher_better)."""
    if objective.kind == "reduce_debt":
        return "debt.score", False
    if objective.kind == "raise_stability":
        return "stability.composite", True
    if objective.kind == "reduce_risk":
        return "risk.count", False
    if objective.kind == "stabilize_path":
        return "risk.count", False
    if objective.kind == "pass_tests":
        return "tests.score", True
    if objective.kind == "custom" and objective.metric:
        return objective.metric, objective.higher_better
    # follow_refactor: prefer debt down, then risk, then stability up as composite
    return "debt.score", False


def extract_signal(report: dict[str, Any], metric: str) -> float:
    if metric == "risk.count":
        return float(len((report.get("risk") or {}).get("failure_points") or []))
    if metric == "stability.composite":
        stab = _get_path(report, "stability.composite", default=-1.0)
        if stab < 0:
            return _get_path(report, "metrics.code_stability")
        return stab
    if metric == "tests.score":
        tests = report.get("tests") if isinstance(report.get("tests"), dict) else {}
        if tests and tests.get("score") is not None:
            try:
                return float(tests["score"])
            except (TypeError, ValueError):
                pass
        return _get_path(report, "tests.score")
    return _get_path(report, metric)


def score_objective(
    objective: Objective,
    current: dict[str, Any],
    previous: dict[str, Any] | None = None,
    *,
    diff: dict[str, Any] | None = None,
) -> ObjectiveScore:
    metric, higher_better = primary_metric(objective)
    value = extract_signal(current, metric)
    prev = extract_signal(previous, metric) if previous else None
    delta = None if prev is None else value - prev
    if prev is None:
        improved = False
    elif abs(delta or 0.0) < 1e-9:
        improved = False
    elif higher_better:
        improved = bool(delta and delta > 0)
    else:
        improved = bool(delta and delta < 0)

    reached = False
    if objective.target is not None:
        reached = value >= objective.target if higher_better else value <= objective.target

    notes: list[str] = []
    constraints_ok = True
    stab = extract_signal(current, "stability.composite")
    if stab < objective.min_stability:
        constraints_ok = False
        notes.append(f"stability {stab:.3f} < min {objective.min_stability}")

    worsened = list((diff or {}).get("worsened") or [])
    if len(worsened) > objective.max_new_worsened:
        constraints_ok = False
        notes.append(f"{len(worsened)} worsened signals > max {objective.max_new_worsened}")

    if objective.path:
        fps = (current.get("risk") or {}).get("failure_points") or []
        path_hits = [f for f in fps if objective.path in str(f.get("path") or "")]
        notes.append(f"path-focus failure points: {len(path_hits)}")

    if prev is None:
        notes.append("baseline score (no previous report)")
    elif improved and constraints_ok:
        notes.append("objective improved under constraints")
    elif improved:
        notes.append("raw objective improved but constraints failed")
    else:
        notes.append("objective did not improve")

    return ObjectiveScore(
        value=value,
        previous=prev,
        delta=None if delta is None else round(delta, 6),
        improved=improved,
        reached_target=reached,
        constraints_ok=constraints_ok,
        notes=notes,
        signals={
            "metric": metric,
            "higher_better": higher_better,
            "stability.composite": stab,
            "debt.score": extract_signal(current, "debt.score"),
            "risk.count": extract_signal(current, "risk.count"),
        },
    )


def ranks_steps_for_objective(
    objective: Objective,
    refactor_plan: dict[str, Any] | None,
    risk: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Order refactor steps / failure points for the next action."""
    plan = refactor_plan or {}
    steps = list(plan.get("steps") or [])
    if not steps:
        for wave in plan.get("waves") or []:
            steps.extend(list(wave.get("steps") or []))
    if not steps:
        # synthesize from failure points
        for i, fp in enumerate((risk or {}).get("failure_points") or []):
            steps.append(
                {
                    "id": fp.get("id") or f"FP{i+1}",
                    "title": fp.get("title") or fp.get("kind") or "failure point",
                    "wave": "stabilize",
                    "paths": [fp.get("path")] if fp.get("path") else [],
                    "problem_kind": fp.get("kind"),
                    "evidence_refs": [fp.get("id")] if fp.get("id") else [],
                    "actions": [fp.get("suggested_intervention") or "Inspect hotspot"],
                    "acceptance_criteria": [
                        "Severity reduced on next CodeEvolve run",
                    ],
                    "priority": "P0" if float(fp.get("severity") or 0) >= 0.85 else "P1",
                }
            )

    wave_order = ["stabilize", "contain", "pay_down", "evolve"]
    if objective.wave:
        preferred = objective.wave
        steps = sorted(
            steps,
            key=lambda s: (0 if s.get("wave") == preferred else 1, wave_order.index(s.get("wave") or "evolve") if (s.get("wave") or "evolve") in wave_order else 99),
        )
    else:
        steps = sorted(
            steps,
            key=lambda s: wave_order.index(s.get("wave") or "evolve") if (s.get("wave") or "evolve") in wave_order else 99,
        )

    if objective.path:
        focused = [s for s in steps if any(objective.path in str(p) for p in (s.get("paths") or []))]
        if focused:
            return focused + [s for s in steps if s not in focused]

    if objective.kind == "reduce_debt":
        debtish = [s for s in steps if "debt" in str(s.get("problem_kind") or "") or s.get("wave") == "pay_down"]
        if debtish:
            return debtish + [s for s in steps if s not in debtish]

    if objective.kind in {"reduce_risk", "stabilize_path", "raise_stability"}:
        stab = [s for s in steps if s.get("wave") in {"stabilize", "contain"}]
        if stab:
            return stab + [s for s in steps if s not in stab]

    return steps
