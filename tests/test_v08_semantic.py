"""Word2Vec + semantic taxonomy tests (memory backend / gensim optional)."""

from __future__ import annotations

from codeevolve.api import CodeEvolve
from codeevolve.taxonomy.semantic import build_semantic_taxonomy
from codeevolve.taxonomy.vector_store import MemoryVectorStore, VectorRecord, open_vector_store
from codeevolve.taxonomy.word2vec import analyze_word2vec, build_evolution_corpus


def test_evolution_corpus_and_word2vec(sample_repo, monkeypatch):
    monkeypatch.setenv("CODEEVOLVE_SKIP_GENSIM", "1")
    monkeypatch.setenv("CODEEVOLVE_SKIP_EMBED", "1")
    commits = CodeEvolve(sample_repo).commits()
    corpus = build_evolution_corpus(commits)
    assert corpus
    w2v = analyze_word2vec(
        commits,
        clade_files={"clade_00": ["src/app.py", "src/utils.py"]},
    )
    assert w2v.engine in {"gensim", "cooccurrence_fallback"}
    assert w2v.vocab_size >= 1
    assert w2v.corpus_sentences >= 1
    d = w2v.to_dict()
    assert "top_terms" in d


def test_memory_vector_store_query():
    store = MemoryVectorStore("ce-test")
    store.upsert(
        [
            VectorRecord("a", "auth login", [1.0, 0.0, 0.0], {"path": "a.py"}),
            VectorRecord("b", "billing invoice", [0.0, 1.0, 0.0], {"path": "b.py"}),
        ]
    )
    hits = store.query([0.9, 0.1, 0.0], top_k=1)
    assert hits and hits[0]["id"] == "a"


def test_open_vector_store_defaults_memory(monkeypatch):
    monkeypatch.delenv("PINECONE_API_KEY", raising=False)
    monkeypatch.delenv("CODEEVOLVE_PINECONE_API_KEY", raising=False)
    monkeypatch.delenv("CODEEVOLVE_USE_CHROMA", raising=False)
    monkeypatch.setenv("CODEEVOLVE_VECTOR_BACKEND", "memory")
    store = open_vector_store("ce-unit", dimension=8, backend="memory")
    assert store.name == "memory"


def test_semantic_taxonomy_builds(sample_repo, monkeypatch):
    monkeypatch.setenv("CODEEVOLVE_SKIP_GENSIM", "1")
    monkeypatch.setenv("CODEEVOLVE_SKIP_EMBED", "1")
    monkeypatch.setenv("CODEEVOLVE_VECTOR_BACKEND", "memory")
    ce = CodeEvolve(sample_repo)
    commits = ce.commits()
    sem = build_semantic_taxonomy(
        sample_repo,
        commits,
        display="sample",
        path_to_clade={"src/app.py": "clade_00", "src/utils.py": "clade_00"},
        clades=[{"id": "clade_00", "files": ["src/app.py", "src/utils.py"]}],
        backend="memory",
    )
    assert sem.backend == "memory"
    assert sem.niches
    assert sem.stored_vectors >= 1
    assert sem.word2vec is not None


def test_analyze_includes_semantic_blocks(sample_repo, monkeypatch):
    monkeypatch.setenv("CODEEVOLVE_TAXONOMY_HEURISTIC", "1")
    monkeypatch.setenv("CODEEVOLVE_SKIP_HF", "1")
    monkeypatch.setenv("CODEEVOLVE_SKIP_GENSIM", "1")
    monkeypatch.setenv("CODEEVOLVE_SKIP_EMBED", "1")
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
    assert report.taxonomy.word2vec
    assert report.taxonomy.semantic.get("backend") == "memory"
