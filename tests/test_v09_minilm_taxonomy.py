"""Lightweight taxonomy embedder + deepened semantic niches."""

from __future__ import annotations

from codeevolve.api import CodeEvolve
from codeevolve.embeddings import embed_text, embed_texts
from codeevolve.models.taxonomy_embed import (
    DEFAULT_TAXONOMY_EMBED_MODEL,
    ensure_taxonomy_embedder,
    embed_taxonomy_texts,
    resolve_taxonomy_embed_model,
)
from codeevolve.taxonomy.semantic import build_semantic_taxonomy


def test_resolve_default_minilm(monkeypatch):
    monkeypatch.delenv("CODEEVOLVE_EMBED_MODEL", raising=False)
    monkeypatch.delenv("CODEEVOLVE_EMBED_LIGHT", raising=False)
    assert resolve_taxonomy_embed_model() == DEFAULT_TAXONOMY_EMBED_MODEL
    monkeypatch.setenv("CODEEVOLVE_EMBED_LIGHT", "1")
    assert "L3" in resolve_taxonomy_embed_model() or "MiniLM" in resolve_taxonomy_embed_model()


def test_embed_taxonomy_falls_back_when_skipped(monkeypatch):
    monkeypatch.setenv("CODEEVOLVE_SKIP_EMBED", "1")
    vecs, info = embed_taxonomy_texts(["auth login handler", "billing invoice total"])
    assert len(vecs) == 2
    assert info.engine == "hash_fallback"
    assert len(vecs[0]) == 64


def test_embed_texts_for_taxonomy_flag(monkeypatch):
    monkeypatch.setenv("CODEEVOLVE_SKIP_EMBED", "1")
    a = embed_text("src auth service", for_taxonomy=True)
    b = embed_texts(["src auth service"], for_taxonomy=True)[0]
    assert len(a) == len(b)


def test_ensure_embedder_reports_skip(monkeypatch):
    monkeypatch.setenv("CODEEVOLVE_SKIP_EMBED", "1")
    info = ensure_taxonomy_embedder(download=False)
    assert info.ok is False
    assert info.engine == "hash_fallback"


def test_semantic_includes_embedder_and_confidence(sample_repo, monkeypatch):
    monkeypatch.setenv("CODEEVOLVE_SKIP_EMBED", "1")
    monkeypatch.setenv("CODEEVOLVE_SKIP_GENSIM", "1")
    monkeypatch.setenv("CODEEVOLVE_VECTOR_BACKEND", "memory")
    commits = CodeEvolve(sample_repo).commits()
    sem = build_semantic_taxonomy(
        sample_repo,
        commits,
        display="sample",
        path_to_clade={"src/app.py": "clade_00", "src/utils.py": "clade_00"},
        clades=[{"id": "clade_00", "files": ["src/app.py", "src/utils.py"]}],
        backend="memory",
    )
    assert sem.embedder.get("engine") in {"hash_fallback", "sentence_transformers"}
    assert sem.niches
    assert "mean_confidence" in sem.niches[0].to_dict()
    assert sem.path_confidence
    assert "MiniLM-path" in sem.summary or "embed" in sem.summary.lower() or sem.embedder


def test_analyze_semantic_embedder_block(sample_repo, monkeypatch):
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
        include_semantic=True,
        vector_backend="memory",
    )
    assert report.taxonomy.semantic
    assert "embedder" in report.taxonomy.semantic
