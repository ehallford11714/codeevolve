from codeevolve.risk.blast_radius import blast_radius_table, cochange_degrees

__all__ = ["RiskReport", "analyze_risk", "blast_radius_table", "cochange_degrees"]


def __getattr__(name: str):
    if name in {"RiskReport", "analyze_risk"}:
        from codeevolve.risk.weaknesses import RiskReport, analyze_risk

        return {"RiskReport": RiskReport, "analyze_risk": analyze_risk}[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
