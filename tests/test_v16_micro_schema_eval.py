"""0.16: blast/symbol/CST provenance, schema/MCP, dynamics eval suite."""

from __future__ import annotations

from codeevolve.eval.dynamics_gold import run_dynamics_eval
from codeevolve.eval.runner import run_evaluation
from codeevolve.mcp.server import handle
from codeevolve.provenance import (
    build_provenance_ledger,
    dispatch_mcp_tool,
    validate_deliberation_pack,
    write_schemas,
)


def test_blast_symbol_cst_in_ledger():
    report = {
        "repo": "x",
        "taxonomy": {"clades": [], "allocations": []},
        "genetics": {"lineages": [], "gene_flow": []},
        "ecology": {"global_stage": "growth", "calibration": {}},
        "blast_radius": [{"path": "a.py", "co_changers": 8, "blast_score": 0.2}],
        "symbols": {
            "symbols": [{"qualname": "a.py::f", "kind": "function", "path": "a.py", "line": 3}]
        },
        "cst_evolution": {
            "deltas": [{"path": "a.py", "node": "function", "delta": 1, "window": "late"}]
        },
        "risk": {
            "failure_points": [
                {
                    "id": "fp_a",
                    "title": "hot a",
                    "path": "a.py",
                    "severity": "high",
                    "kind": "hotspot",
                }
            ]
        },
        "hypothesis_panel": {"claims": []},
        "hierarchy_trends": {"next_experiments": []},
        "drift": {},
        "signal_confidence": {},
    }
    ledger = build_provenance_ledger(report)
    kinds = {r.kind for r in ledger.records}
    assert "blast_radius" in kinds
    assert "symbol" in kinds
    assert "cst_delta" in kinds
    risk = next(f for f in ledger.frames if f.id == "frame:risk:fp_a")
    assert any(e.kind == "blast_radius" for e in risk.evidence)
    pack = ledger.path_pack("a.py")
    assert pack["blast_radius"] is not None
    assert pack["symbols"]


def test_schema_and_mcp(tmp_path):
    written = write_schemas(tmp_path)
    assert (tmp_path / "deliberation_pack.schema.json").is_file()
    assert (tmp_path / "mcp_tools.json").is_file()
    assert "deliberation_pack" in written

    tiny = {
        "repo": "x",
        "taxonomy": {"clades": [], "allocations": []},
        "genetics": {"lineages": []},
        "ecology": {"global_stage": "growth", "calibration": {}},
        "hypothesis_panel": {"claims": []},
        "hierarchy_trends": {"next_experiments": []},
        "risk": {"failure_points": []},
        "drift": {},
        "signal_confidence": {},
    }
    ledger = build_provenance_ledger(tiny)
    pack = ledger.deliberation_pack()
    assert validate_deliberation_pack(pack) == []

    report_path = tmp_path / "report.json"
    report_path.write_text(__import__("json").dumps(tiny), encoding="utf-8")
    out = dispatch_mcp_tool("provenance_pack", {"from_report": str(report_path)})
    assert "frames" in out
    listed = handle({"method": "tools/list"})
    assert len(listed["tools"]) >= 4


def test_dynamics_eval_suite():
    cases = run_dynamics_eval()
    assert len(cases) >= 3
    assert all(c.score >= 0.6 for c in cases)
    report = run_evaluation(suite="dynamics")
    assert report.dynamics_score is not None
    assert report.dynamics_score >= 0.7
    assert report.overall_score >= 0.7
