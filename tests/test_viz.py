"""Phylogeny viz: Fitch parsimony, layout, HTML/SVG/Newick."""

from __future__ import annotations

import json
from pathlib import Path

from codeevolve.viz import build_model, builder_payload, fitch_parsimony, render_viz, write_viz
from codeevolve.viz.intent import classify_intent
from codeevolve.viz.layout import layout_layered_dag, layout_phylogeny_3d
from codeevolve.viz.newick import to_newick
from codeevolve.viz.parsimony import spanning_tree


def test_fitch_one_step_two_states() -> None:
    children = {"r": ["a", "b"]}
    result = fitch_parsimony(children, ["r"], {"a": "X", "b": "Y"})
    assert result.steps == 1
    assert result.min_steps == 1
    assert result.consistency_index == 1.0
    assert result.reconstructed["r"] in {"X", "Y"}
    assert len(result.change_edges) == 1


def test_fitch_zero_steps_uniform() -> None:
    children = {"r": ["a", "b"]}
    result = fitch_parsimony(children, ["r"], {"a": "X", "b": "X"})
    assert result.steps == 0
    assert result.reconstructed["r"] == "X"
    assert result.change_edges == []
    assert result.consistency_index == 1.0


def test_fitch_homoplasy_extra_step() -> None:
    children = {"p": ["a1", "b1"], "q": ["a2", "b2"], "r": ["p", "q"]}
    result = fitch_parsimony(
        children,
        ["r"],
        {"a1": "A", "b1": "B", "a2": "A", "b2": "B"},
    )
    assert result.steps == 2
    assert result.min_steps == 1
    assert result.steps > result.min_steps
    assert result.consistency_index < 1.0


def test_observed_internal_states_count_edge_changes() -> None:
    children = {"r": ["a", "b"]}
    result = fitch_parsimony(
        children,
        ["r"],
        {"r": "X", "a": "X", "b": "Y"},
    )
    assert result.steps == 1
    assert result.change_edges == [("r", "b")]


def test_layout_generation_increases_x() -> None:
    lay = layout_layered_dag(
        ["r", "a", "b"],
        parents={"r": [], "a": ["r"], "b": ["r"]},
        children={"r": ["a", "b"], "a": [], "b": []},
        generation={"r": 0, "a": 1, "b": 1},
        roots=["r"],
    )
    assert lay.nodes["a"].x > lay.nodes["r"].x
    assert lay.nodes["b"].x == lay.nodes["a"].x
    assert not lay.nodes["r"].hidden


def test_classify_intent_conventional_and_silent() -> None:
    hit = classify_intent("feat: add phylogeny builder")
    assert hit.kind == "feat" and hit.stance == "support"
    silent = classify_intent("misc tweaks xyz")
    assert silent.kind == "unknown" and silent.stance == "insufficient"
    merge = classify_intent("Merge branch x", n_parents=2)
    assert merge.kind == "merge"


def test_layout_3d_sets_z() -> None:
    lay = layout_phylogeny_3d(
        ["r", "a"],
        parents={"r": [], "a": ["r"]},
        children={"r": ["a"], "a": []},
        generation={"r": 0, "a": 1},
        roots=["r"],
        z_of={"r": 0, "a": 2},
        z_scale=10,
    )
    assert lay.nodes["a"].x > lay.nodes["r"].x
    assert lay.nodes["a"].z == 20.0


def test_newick_forest() -> None:
    nwk = to_newick({"r": ["a", "b"]}, ["r"], {"r": "root", "a": "tipA", "b": "tipB"})
    assert nwk.startswith("(") and nwk.endswith(";")
    assert "tipA" in nwk and "tipB" in nwk


def test_spanning_tree_first_parent() -> None:
    nodes = [
        {"sha": "aaa", "parent_shas": []},
        {"sha": "bbb", "parent_shas": ["aaa"]},
        {"sha": "ccc", "parent_shas": ["bbb", "aaa"]},
    ]
    children, parent, roots = spanning_tree(nodes, ["aaa"])
    assert roots == ["aaa"]
    assert parent["ccc"] == "bbb"
    assert "ccc" in children["bbb"]


def _mini_report() -> dict:
    return {
        "repo": "demo",
        "phylogeny": {
            "roots": ["aaa"],
            "max_generation": 2,
            "branch_factor": 1.0,
            "merge_count": 0,
            "current_stage": "growth",
            "stages": [{"window": 0, "stage": "pioneer"}, {"window": 1, "stage": "growth"}],
            "node_count": 3,
            "nodes": [
                {"sha": "aaa", "subject": "init", "parent_shas": [], "children": ["bbb"], "generation": 0},
                {"sha": "bbb", "subject": "feat", "parent_shas": ["aaa"], "children": ["ccc"], "generation": 1},
                {"sha": "ccc", "subject": "fix", "parent_shas": ["bbb"], "children": [], "generation": 2},
            ],
        },
        "taxonomy": {
            "clades": [{"id": "clade:core", "label": "core", "layer": "core", "files": ["a.py"]}],
            "allocations": [
                {"sha": "aaa", "path": "a.py", "clade_id": "clade:core", "lineage_id": "l", "insertions": 2, "deletions": 0},
                {"sha": "bbb", "path": "a.py", "clade_id": "clade:core", "lineage_id": "l", "insertions": 1, "deletions": 0},
                {"sha": "ccc", "path": "b.py", "clade_id": "clade:tests", "lineage_id": "l", "insertions": 3, "deletions": 0},
            ],
            "keyword_taxonomy": {
                "hierarchy": {
                    "name": "root",
                    "count": 2,
                    "children": [
                        {"name": "architecture", "count": 1, "children": []},
                        {"name": "quality", "count": 1, "children": []},
                    ],
                },
                "path_types": {
                    "a.py": {
                        "path": "a.py",
                        "type_path": ["architecture", "api"],
                        "type_key": "architecture/api",
                        "confidence": 0.9,
                        "matched": ["api"],
                        "layer_hint": "core",
                    },
                    "b.py": {
                        "path": "b.py",
                        "type_path": ["quality", "test"],
                        "type_key": "quality/test",
                        "confidence": 0.9,
                        "matched": ["test"],
                        "layer_hint": "test",
                    },
                },
            },
            "semantic": {
                "path_to_niche": {"a.py": "niche:api", "b.py": "niche:test"},
                "niches": [
                    {"id": "niche:api", "label": "API surface"},
                    {"id": "niche:test", "label": "tests"},
                ],
            },
        },
        "genetics": {
            "gene_flow": [{"source_clade": "clade:core", "target_clade": "clade:tests", "weight": 2, "kind": "cochange"}]
        },
        "ecology": {"global_stage": "growth"},
        "provenance": {
            "frames": [
                {
                    "id": "frame:basin",
                    "claim": "Repo occupies a growth basin",
                    "stance": "support",
                    "confidence": 0.6,
                    "falsifier": "stage leaves growth",
                    "measure": "ecology.global_stage",
                    "context_clades": ["clade:core"],
                }
            ]
        },
        "debt": {"score": 0.2, "summary": "low"},
        "risk": {"count": 0, "failure_points": [], "summary": "none"},
    }


def test_gallery_html_contains_svg_and_parsimony() -> None:
    html = render_viz(_mini_report(), kind="all", fmt="html")
    assert "<svg" in html
    assert "Fitch" in html
    assert "Parsimony" in html
    assert "Newick" in html
    assert "phy3d-canvas" in html
    assert "intent" in html.lower()
    model = build_model(_mini_report())
    assert model.parsimony.steps >= 1
    assert model.commits[0].clade_id == "clade:core"
    assert model.commits[1].intent == "feat"
    assert model.commits[2].intent == "fix"


def test_write_viz_dir_and_cli(tmp_path: Path) -> None:
    report = tmp_path / "report.json"
    report.write_text(json.dumps(_mini_report()), encoding="utf-8")
    out_dir = tmp_path / "viz"
    gallery = write_viz(_mini_report(), out_dir, kind="all")
    assert gallery.is_file()
    assert (out_dir / "builder.html").read_text(encoding="utf-8").find("phy3d-canvas") > 0
    assert (out_dir / "phylogeny.svg").read_text(encoding="utf-8").startswith("<svg")
    assert (out_dir / "parsimony.svg").read_text(encoding="utf-8").startswith("<svg")
    assert (out_dir / "tree.nwk").read_text(encoding="utf-8").endswith(";\n")
    html_path = tmp_path / "g.html"
    write_viz(_mini_report(), html_path)
    assert "CodeEvolve phylogeny" in html_path.read_text(encoding="utf-8")

    from codeevolve.cli import main

    nwk = tmp_path / "t.nwk"
    assert main(["viz", "--report", str(report), "--out", str(nwk), "--format", "newick"]) == 0
    assert nwk.read_text(encoding="utf-8").strip().endswith(";")

    from codeevolve.provenance.schema import dispatch_mcp_tool

    mcp = dispatch_mcp_tool(
        "viz_phylogeny",
        {"from_report": str(report), "out": str(tmp_path / "mcp.html")},
    )
    assert mcp.get("parsimony", {}).get("steps") is not None
    assert Path(mcp["out"]).is_file()


def test_sample_repo_viz(sample_repo: Path, monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("CODEEVOLVE_TAXONOMY_HEURISTIC", "1")
    monkeypatch.setenv("CODEEVOLVE_SKIP_HF", "1")
    from codeevolve import CodeEvolve

    report = CodeEvolve(sample_repo).analyze(
        max_commits=50,
        use_llm=False,
        include_hardware=False,
        include_selection=False,
        ensure_slm=False,
    )
    html = render_viz(report)
    assert "<svg" in html
    model = build_model(report)
    assert model.node_count >= 3
    assert not model.truncated
    out = tmp_path / "phylo.html"
    write_viz(report, out)
    assert out.is_file()


def test_layout_groups_siblings_by_type() -> None:
    lay = layout_layered_dag(
        ["r", "b", "a"],
        parents={"r": [], "a": ["r"], "b": ["r"]},
        children={"r": ["b", "a"], "a": [], "b": []},
        generation={"r": 0, "a": 1, "b": 1},
        roots=["r"],
        order_of={"r": "architecture/api", "a": "architecture/api", "b": "quality/test"},
    )
    assert lay.nodes["a"].y < lay.nodes["b"].y


def test_semantic_type_divisions() -> None:
    model = build_model(_mini_report())
    by = {c.sha: c for c in model.commits}
    assert by["aaa"].type_key == "architecture/api"
    assert by["aaa"].type_path == ["architecture", "api"]
    assert by["aaa"].division_source == "keyword"
    assert by["aaa"].niche_label == "API surface"
    assert by["ccc"].type_key == "quality/test"
    assert by["ccc"].niche_id == "niche:test"
    assert model.parsimony.character == "type_path"
    assert model.parsimony.steps >= 1
    assert 1 in by["aaa"].reconstructed_depths
    assert by["aaa"].reconstructed_depths[1] == "architecture"
    assert by["ccc"].reconstructed_depths[1] == "quality"
    assert "architecture/api" in model.division_counts
    assert "quality/test" in model.division_counts
    payload = builder_payload(model)
    assert payload["meta"]["parsimony"]
    assert any(n.get("type_key") == "architecture/api" for n in payload["nodes"])
    assert any(n.get("zType") is not None for n in payload["nodes"])
    html = render_viz(_mini_report(), kind="parsimony")
    assert "semantic type" in html.lower() or "Fitch parsimony (semantic type)" in html


def test_division_falls_back_to_clade() -> None:
    report = _mini_report()
    report["taxonomy"]["keyword_taxonomy"].pop("path_types", None)
    report["taxonomy"].pop("semantic", None)
    model = build_model(report)
    by = {c.sha: c for c in model.commits}
    assert by["aaa"].division == "clade:core"
    assert by["aaa"].division_source == "clade"
    assert not by["aaa"].type_key
    assert model.parsimony.character == "clade"


def test_builder_payload_intent_and_frames() -> None:
    model = build_model(_mini_report())
    payload = builder_payload(model)
    assert payload["nodes"]
    assert {n["intent"] for n in payload["nodes"]} >= {"feat", "fix"}
    assert any(n.get("zIntent") is not None for n in payload["nodes"])
    assert payload["frames"]
    assert payload["analysis"].get("note")
    html = render_viz(_mini_report(), kind="3d")
    assert "3D phylogeny builder" in html
    assert "phy3d-canvas" in html
    assert "__PAYLOAD__" not in html
