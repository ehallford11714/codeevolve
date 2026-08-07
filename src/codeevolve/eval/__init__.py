"""Rigor & evaluation: hypothesis panels, signal confidence, benchmarks."""

from codeevolve.eval.confidence import SignalConfidenceReport, score_signal_confidence
from codeevolve.eval.hypothesis import HypothesisPanel, build_hypothesis_panel

__all__ = [
    "HypothesisPanel",
    "build_hypothesis_panel",
    "SignalConfidenceReport",
    "score_signal_confidence",
    "BenchmarkCase",
    "run_benchmark_suite",
    "EvaluationReport",
    "run_evaluation",
]


def __getattr__(name: str):
    if name in {"BenchmarkCase", "run_benchmark_suite"}:
        from codeevolve.eval.benchmarks import BenchmarkCase, run_benchmark_suite

        return {"BenchmarkCase": BenchmarkCase, "run_benchmark_suite": run_benchmark_suite}[name]
    if name in {"EvaluationReport", "run_evaluation"}:
        from codeevolve.eval.runner import EvaluationReport, run_evaluation

        return {"EvaluationReport": EvaluationReport, "run_evaluation": run_evaluation}[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
