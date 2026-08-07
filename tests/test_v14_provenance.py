"""Unified provenance ledger for deliberation."""

from __future__ import annotations

from codeevolve.api import CodeEvolve
from codeevolve.provenance import build_provenance_ledger, query_provenance


def test_ledger_from_analyze(sample_repo, monkeypatch):
    monkeypatch.setenv("CODEEVOLVE_SKIP_GHSA", "1")
    monkeypatch.setenv("CODEEVOLVE_TAXONOMY_HEURISTIC", "1")
    monkeypatch.setenv("CODEEVOLVE_SKIP_HF", "1")
    monkeypatch.setenv("CODEEVOLVE_SKIP_EMBED", "1")
    monkeypatch.setenv("CODEEVOLVE_SKIP_GENSIM", "1")
    monkeypatch.setenv("CODEEVOLVE_VECTOR_BACKEND", "memory")
    report = CodeEvolve(sample_repo).analyze(
        use_llm=False,
        ensure_slm=False,
        include_selection=False,
        write_report=False,
        include_repo_report=False,
        include_hardware=False,
        include_cst=False,
        include_clones=False,
        include_reticulation=False,
        include_fork_lineage=False,
        include_semantic=False,
        include_rag=False,
        max_commits=60,
    )
    assert report.provenance is not None
    assert report.provenance.records
    assert report.provenance.frames
    d = report.to_dict()
    assert d.get("provenance", {}).get("record_count", 0) >= 1


def test_query_pack_resolve_timeline(sample_repo, monkeypatch):
    monkeypatch.setenv("CODEEVOLVE_SKIP_GHSA", "1")
    monkeypatch.setenv("CODEEVOLVE_TAXONOMY_HEURISTIC", "1")
    monkeypatch.setenv("CODEEVOLVE_SKIP_HF", "1")
    monkeypatch.setenv("CODEEVOLVE_SKIP_EMBED", "1")
    report = CodeEvolve(sample_repo).analyze(
        use_llm=False,
        ensure_slm=False,
        include_selection=False,
        write_report=False,
        include_repo_report=False,
        include_hardware=False,
        include_cst=False,
        include_clones=False,
        include_reticulation=False,
        include_fork_lineage=False,
        include_semantic=False,
        include_rag=False,
        max_commits=40,
    )
    ledger = report.provenance or build_provenance_ledger(report.to_dict())
    kinds = {r.kind for r in ledger.records}
    assert kinds & {"clade", "commit_delta", "lineage", "code_type"}

    pack = ledger.deliberation_pack()
    assert pack["frames"]
    assert "howto" in pack
    assert "timeline" in pack

    stage = ledger.expand_frame("frame:stage")
    assert stage is not None
    assert stage["frame"]["id"] == "frame:stage"
    assert "evidence_records" in stage

    chain = ledger.resolve("frame:stage", depth=2)
    assert chain["node_count"] >= 1

    q = query_provenance(ledger, kind="hypothesis", pack=False)
    assert "records" in q


def test_from_report_dict_static():
    tiny = {
        "repo": "demo",
        "taxonomy": {
            "clades": [
                {
                    "id": "clade_00",
                    "label": "core",
                    "layer": "core",
                    "files": ["a.py"],
                    "file_count": 1,
                    "churn": 3,
                }
            ],
            "allocations": [
                {
                    "sha": "abc1234",
                    "path": "a.py",
                    "clade_id": "clade_00",
                    "insertions": 2,
                    "deletions": 0,
                    "lineage_id": "lin:a.py",
                }
            ],
        },
        "genetics": {
            "lineages": [
                {
                    "path": "a.py",
                    "clade_id": "clade_00",
                    "first_sha": "abc",
                    "last_sha": "abc",
                    "fitness": 0.5,
                }
            ]
        },
        "ecology": {
            "global_stage": "growth",
            "calibration": {
                "method": "event_anchor",
                "confidence": 0.7,
                "events": {
                    "events": [
                        {
                            "kind": "major_release",
                            "label": "v2.0.0",
                            "when": "2024-01-01T00:00:00+00:00",
                            "stage_hint": "growth",
                            "confidence": 0.8,
                        }
                    ]
                },
                "changepoints": {"points": []},
                "segments": [],
                "anchors": [],
            },
        },
        "hypothesis_panel": {
            "claims": [
                {
                    "id": "lehman_change",
                    "claim": "continuing change",
                    "verdict": "support",
                    "confidence": 0.6,
                    "method": "test",
                    "caveats": ["proxy"],
                }
            ]
        },
        "hierarchy_trends": {
            "branch_trends": [
                {
                    "type_key": "architecture/api",
                    "churn": 10,
                    "trend": "heating",
                    "narrative": "api heating",
                }
            ],
            "next_experiments": [
                {
                    "id": "heat_1",
                    "claim": "branch heating",
                    "falsifier": "no heat",
                    "measure": "x",
                    "branch": "architecture/api",
                }
            ],
        },
        "risk": {
            "failure_points": [
                {
                    "id": "fp1",
                    "title": "hot",
                    "path": "a.py",
                    "clade_id": "clade_00",
                    "severity": "high",
                    "kind": "hotspot",
                }
            ]
        },
        "drift": {"clade_drift": []},
        "signal_confidence": {"signals": [{"signal": "coupling", "confidence": 0.7, "reliability": "high"}]},
    }
    ledger = build_provenance_ledger(tiny)
    assert any(r.kind == "lifecycle_event" for r in ledger.records)
    assert any(f.id == "frame:stage" for f in ledger.frames)
    assert any(f.id.startswith("frame:branch:") for f in ledger.frames)

    pack = CodeEvolve.provenance_from_report(tiny, pack=True)
    assert pack["frames"]
    path = ledger.path_pack("a.py")
    assert path["lineage"] is not None
    assert path["related_frames"]
    tl = ledger.timeline()
    assert tl and tl[0]["kind"] == "lifecycle_event"
    expanded = ledger.expand_frame("frame:risk:fp1")
    assert expanded and expanded["evidence_records"]
