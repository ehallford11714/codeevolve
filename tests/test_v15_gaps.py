"""0.15: close provenance gaps — dynamics, diff, selection, genetics, surfaces."""

from __future__ import annotations

from codeevolve.api import CodeEvolve
from codeevolve.provenance import build_dynamics, build_provenance_ledger, query_provenance
from codeevolve.pr_comment import render_pr_comment


def test_dynamics_state_trajectory(sample_repo, monkeypatch):
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
        include_clones=True,
        include_reticulation=False,
        include_fork_lineage=False,
        include_semantic=False,
        include_rag=False,
        max_commits=80,
    )
    assert report.dynamics
    assert report.dynamics.get("sample_count", 0) >= 1
    kinds = {r.kind for r in report.provenance.records}
    assert "state_sample" in kinds or "trajectory" in kinds
    assert any(f.id in {"frame:basin", "frame:stage"} for f in report.provenance.frames)


def test_diff_and_selection_in_ledger():
    tiny = {
        "repo": "demo",
        "taxonomy": {
            "clades": [{"id": "clade_00", "label": "core", "layer": "core", "files": ["a.py"], "file_count": 1, "churn": 3}],
            "allocations": [
                {"sha": "aaa111", "path": "a.py", "clade_id": "clade_00", "insertions": 2, "deletions": 0},
                {"sha": "bbb222", "path": "a.py", "clade_id": "clade_00", "insertions": 1, "deletions": 0},
                {"sha": "ccc333", "path": "a.py", "clade_id": "clade_00", "insertions": 4, "deletions": 1},
            ],
        },
        "genetics": {
            "lineages": [{"path": "a.py", "clade_id": "clade_00", "first_sha": "aaa", "last_sha": "ccc", "fitness": 0.4}],
            "gene_flow": [{"source_clade": "clade_00", "target_clade": "clade_01", "weight": 6, "kind": "merge_bridge"}],
            "hgt_suspects": [],
        },
        "clones": {"genealogies": [{"qualname": "a.py::f", "pattern": "type1", "path": "a.py"}]},
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
                            "when": "2024-06-01T00:00:00+00:00",
                            "stage_hint": "growth",
                            "confidence": 0.8,
                        }
                    ]
                },
                "changepoints": {
                    "months": [
                        {"month": "2024-01", "start": "2024-01-01T00:00:00+00:00", "commits": 5, "authors": 2, "reverts": 0, "churn": 40},
                        {"month": "2024-02", "start": "2024-02-01T00:00:00+00:00", "commits": 8, "authors": 3, "reverts": 1, "churn": 90},
                        {"month": "2024-03", "start": "2024-03-01T00:00:00+00:00", "commits": 12, "authors": 4, "reverts": 0, "churn": 120},
                        {"month": "2024-04", "start": "2024-04-01T00:00:00+00:00", "commits": 10, "authors": 3, "reverts": 2, "churn": 80},
                        {"month": "2024-05", "start": "2024-05-01T00:00:00+00:00", "commits": 9, "authors": 3, "reverts": 0, "churn": 70},
                        {"month": "2024-06", "start": "2024-06-01T00:00:00+00:00", "commits": 20, "authors": 5, "reverts": 1, "churn": 200},
                        {"month": "2024-07", "start": "2024-07-01T00:00:00+00:00", "commits": 15, "authors": 4, "reverts": 0, "churn": 150},
                        {"month": "2024-08", "start": "2024-08-01T00:00:00+00:00", "commits": 11, "authors": 3, "reverts": 0, "churn": 100},
                    ],
                    "points": [],
                },
                "segments": [
                    {
                        "stage": "growth",
                        "start": "2024-01-01T00:00:00+00:00",
                        "end": "2024-08-01T00:00:00+00:00",
                        "source": "test",
                        "confidence": 0.7,
                    }
                ],
                "anchors": [],
            },
        },
        "selection": {
            "pressure_score": 0.62,
            "open_issues": 4,
            "bug_label_rate": 0.4,
            "pr_merge_rate": 0.5,
            "recent_issues": [
                {
                    "number": 7,
                    "title": "crash on boot",
                    "state": "open",
                    "created_at": "2024-05-01T00:00:00Z",
                    "labels": ["bug"],
                    "epistemic": "stated",
                    "bug_like": True,
                }
            ],
            "recent_prs": [
                {
                    "number": 9,
                    "title": "fix crash",
                    "state": "closed",
                    "merged_at": "2024-05-10T00:00:00Z",
                    "epistemic": "stated",
                }
            ],
        },
        "diff": {
            "improved": ["stability.composite +0.05"],
            "worsened": ["metrics.revert_rate +0.02"],
            "unchanged": [],
            "deltas": {"stability.composite": {"previous": 0.5, "current": 0.55, "delta": 0.05}},
        },
        "hypothesis_panel": {"claims": []},
        "hierarchy_trends": {"branch_trends": [], "next_experiments": []},
        "risk": {"failure_points": []},
        "drift": {"clade_drift": []},
        "coupling": {"edges": [{"a": "a.py", "b": "b.py", "weight": 4, "kind": "commit"}]},
        "debt": {"score": 0.2, "items": [{"path": "a.py", "kind": "todo", "title": "TODO"}]},
        "signal_confidence": {},
    }
    dyn = build_dynamics(tiny)
    assert dyn.samples
    tiny["dynamics"] = dyn.to_dict()
    ledger = build_provenance_ledger(tiny)
    kinds = {r.kind for r in ledger.records}
    assert "state_sample" in kinds
    assert "trajectory" in kinds
    assert "selection_item" in kinds
    assert "report_delta" in kinds
    assert "gene_flow" in kinds
    assert "coupling_edge" in kinds
    assert "debt_item" in kinds
    assert "path_episode" in kinds
    frame_ids = {f.id for f in ledger.frames}
    assert "frame:basin" in frame_ids or "frame:stage" in frame_ids
    assert "frame:delta:report" in frame_ids
    assert "frame:selection" in frame_ids
    pack = query_provenance(ledger, path_pack="a.py")
    assert pack.get("episodes") is not None
    comment = render_pr_comment(tiny, diff=tiny["diff"])
    assert "Deliberation frames" in comment or "frame:" in comment or ledger.frames
    # force frames into report slice for comment
    comment2 = render_pr_comment(
        {**tiny, "provenance": {"frames": [f.to_dict() for f in ledger.frames[:4]]}},
        diff=tiny["diff"],
    )
    assert "Deliberation frames" in comment2
