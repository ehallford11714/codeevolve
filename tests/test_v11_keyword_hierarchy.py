"""Deep keyword hierarchy + ecological trend reports."""

from __future__ import annotations

from codeevolve.api import CodeEvolve
from codeevolve.ecology.hierarchy_trends import analyze_hierarchy_trends
from codeevolve.taxonomy.keywords import (
    classify_path,
    ontology_outline,
    render_tree,
    analyze_keyword_taxonomy,
)
from codeevolve.taxonomy.tree import build_taxonomy


def test_classify_api_handler():
    hit = classify_path("src/api/handlers/auth_login.py")
    assert hit.type_path[0] == "architecture"
    assert "api" in hit.type_path
    assert hit.confidence >= 0.35
    assert hit.layer_hint in {"core", "other", "utility"}


def test_classify_tests_and_docs():
    t = classify_path("tests/unit/test_auth.py")
    assert t.type_path[0] == "verification"
    d = classify_path("docs/ARCHITECTURE.md")
    assert d.type_path[0] == "knowledge"


def test_ontology_has_depth():
    outline = ontology_outline(max_depth=4)
    assert "architecture" in outline
    assert "api" in outline["architecture"]["children"]
    assert outline["architecture"]["children"]["api"]["children"]


def test_hierarchy_tree_builds():
    paths = [
        "src/api/routes/users.py",
        "src/api/handlers/users.py",
        "src/data/models/user.py",
        "src/data/repository/user_repo.py",
        "tests/unit/test_users.py",
        "docs/api.md",
        "src/ui/components/UserCard.tsx",
        ".github/workflows/ci.yml",
    ]
    kw = analyze_keyword_taxonomy(paths)
    assert kw.hierarchy.count == len(paths)
    tree = render_tree(kw.hierarchy, max_depth=4)
    assert "architecture" in tree
    assert "verification" in tree
    assert kw.breakout_seeds


def test_build_taxonomy_attaches_keyword_types(sample_repo, monkeypatch):
    monkeypatch.setenv("CODEEVOLVE_TAXONOMY_HEURISTIC", "1")
    monkeypatch.setenv("CODEEVOLVE_SKIP_HF", "1")
    monkeypatch.setenv("CODEEVOLVE_SKIP_EMBED", "1")
    monkeypatch.setenv("CODEEVOLVE_SKIP_GENSIM", "1")
    commits = CodeEvolve(sample_repo).commits()
    tax = build_taxonomy(
        sample_repo,
        commits,
        guide=True,
        include_semantic=False,
    )
    assert tax.keyword_taxonomy is not None
    assert tax.keyword_taxonomy.hierarchy.count >= 1
    assert any(c.code_type or c.type_path for c in tax.clades) or tax.keyword_taxonomy.path_types


def test_hierarchy_trends_markdown(sample_repo, monkeypatch):
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
        max_commits=50,
    )
    assert report.hierarchy_trends is not None
    ht = report.hierarchy_trends
    assert "What Was Built" in ht.markdown
    assert ht.ascii_tree
    assert ht.built_narrative
    assert ht.ecology_narrative
    assert ht.lehman_narrative
    # recompute path stays consistent
    again = analyze_hierarchy_trends(
        CodeEvolve(sample_repo).commits(max_commits=50),
        report.taxonomy,
        report.ecology,
    )
    assert again.branch_trends is not None
