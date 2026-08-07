"""Gap-closure: taxonomy gold, type-aware breakouts, falsifiable experiments."""

from __future__ import annotations

from codeevolve.api import CodeEvolve
from codeevolve.ecology.hierarchy_trends import propose_next_experiments
from codeevolve.eval.taxonomy_gold import run_taxonomy_eval, score_type_gold
from codeevolve.taxonomy.keywords import classify_path
from codeevolve.taxonomy.tree import _split_mixed_type_clades, _type_family


def test_type_gold_majority():
    hits, score = score_type_gold()
    assert score >= 0.75, [(h.path, h.expected, h.actual) for h in hits if not h.ok]
    assert classify_path("src/api/routes/users.py").type_path[:2] == ["architecture", "api"]


def test_type_family_guard():
    assert _type_family("type:architecture/api|dir:src") == "architecture"
    assert _type_family("dir:src") == ""


def test_split_mixed_type_clades():
    mapping = {f"src/a{i}.py": "dir:src" for i in range(10)}
    mapping.update({f"tests/t{i}.py": "dir:src" for i in range(6)})
    seeds = {
        **{f"src/a{i}.py": "type:architecture/api|dir:src" for i in range(10)},
        **{f"tests/t{i}.py": "type:verification/unit|dir:src" for i in range(6)},
    }
    out = _split_mixed_type_clades(mapping, seeds, max_clades=12, min_size=8)
    families = {_type_family(s) for s in out.values()}
    assert "verification" in families or any("verification" in s for s in out.values())


def test_taxonomy_eval_suite(tmp_path, monkeypatch):
    monkeypatch.setenv("CODEEVOLVE_TAXONOMY_HEURISTIC", "1")
    monkeypatch.setenv("CODEEVOLVE_SKIP_HF", "1")
    monkeypatch.setenv("CODEEVOLVE_SKIP_EMBED", "1")
    monkeypatch.setenv("CODEEVOLVE_VECTOR_BACKEND", "memory")
    cases = run_taxonomy_eval(tmp_path)
    assert len(cases) >= 2
    by = {c.name: c for c in cases}
    assert by["taxonomy_type_gold"].score >= 0.75
    assert by["taxonomy_rag_pipeline"].score >= 0.5


def test_next_experiments_on_analyze(sample_repo, monkeypatch):
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
        include_rag=True,
        max_commits=40,
    )
    assert report.hierarchy_trends is not None
    assert report.hierarchy_trends.next_experiments
    assert "falsifier" in report.hierarchy_trends.markdown.lower() or "Next experiments" in report.hierarchy_trends.markdown
    exps = propose_next_experiments(report.ecology, report.hierarchy_trends.branch_trends)
    assert exps
