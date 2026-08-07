"""CI gate: fail when stability drops or new P0 risks appear."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class CiGateResult:
    ok: bool
    failures: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    summary: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "failures": list(self.failures),
            "warnings": list(self.warnings),
            "summary": self.summary,
        }


def evaluate_ci_gate(
    report: dict[str, Any],
    *,
    previous: dict[str, Any] | None = None,
    min_stability: float = 0.35,
    max_fatigue: float = 0.75,
    max_new_p0: int = 0,
) -> CiGateResult:
    failures: list[str] = []
    warnings: list[str] = []

    stab = float(((report.get("stability") or {}).get("composite")) or (report.get("metrics") or {}).get("code_stability") or 0)
    if stab < min_stability:
        failures.append(f"composite stability {stab:.3f} < {min_stability}")

    fat = float((report.get("fatigue") or {}).get("fatigue_score") or 0)
    if fat > max_fatigue:
        warnings.append(f"fatigue_score {fat:.3f} > {max_fatigue}")

    fps = (report.get("risk") or {}).get("failure_points") or []
    p0 = [f for f in fps if float(f.get("severity") or 0) >= 0.85]
    if previous is not None:
        prev_paths = {
            (f.get("kind"), f.get("path"))
            for f in (previous.get("risk") or {}).get("failure_points") or []
            if float(f.get("severity") or 0) >= 0.85
        }
        new_p0 = [f for f in p0 if (f.get("kind"), f.get("path")) not in prev_paths]
        if len(new_p0) > max_new_p0:
            failures.append(f"{len(new_p0)} new P0 failure points (max {max_new_p0})")
    elif len(p0) > 12:
        warnings.append(f"{len(p0)} high-severity failure points (baseline run)")

    ok = not failures
    summary = "CI gate passed" if ok else f"CI gate failed: {'; '.join(failures)}"
    return CiGateResult(ok=ok, failures=failures, warnings=warnings, summary=summary)
