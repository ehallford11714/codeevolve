"""Codebase RAG chunking + SLM taxonomy guidance."""

from __future__ import annotations

from codeevolve.api import CodeEvolve
from codeevolve.models.guide import guide_taxonomy
from codeevolve.taxonomy.rag import build_rag_index, chunk_text, evidence_bundle, retrieve
from codeevolve.taxonomy.tree import build_taxonomy


def test_chunk_text_splits():
    text = "\n\n".join([f"def f{i}():\n    return {i}\n" + ("x" * 40) for i in range(12)])
    chunks = chunk_text(text, max_chars=120, overlap=20)
    assert len(chunks) >= 2
    assert all(c[2] for c in chunks)


def test_build_rag_index_and_retrieve(sample_repo, monkeypatch):
    monkeypatch.setenv("CODEEVOLVE_SKIP_EMBED", "1")
    monkeypatch.setenv("CODEEVOLVE_VECTOR_BACKEND", "memory")
    idx = build_rag_index(sample_repo, max_files=40, backend="memory")
    assert idx.chunk_count >= 1
    assert idx.backend == "memory"
    hits = retrieve(idx, "application source module utility", top_k=4)
    assert hits
    assert hits[0].text


def test_guide_receives_rag_and_prefers_slm_engine_name(monkeypatch):
    monkeypatch.delenv("CODEEVOLVE_TAXONOMY_HEURISTIC", raising=False)
    monkeypatch.setenv("CODEEVOLVE_SKIP_HF", "1")  # force fallback path in CI
    clades = [
        {
            "id": "clade_00",
            "label": "src",
            "layer": "core",
            "code_type": "architecture/api",
            "type_path": ["architecture", "api"],
            "files": ["src/app.py"],
            "touch_count": 3,
            "churn": 40,
        }
    ]
    rag = {
        "rag": {"backend": "memory", "chunk_count": 2},
        "evidence": {
            "clade_00": [
                {
                    "path": "src/app.py",
                    "score": 0.9,
                    "text": "FILE src/app.py\ndef handler():\n    return api_response()",
                }
            ]
        },
        "instructions": "use chunks",
    }
    guided = guide_taxonomy(clades, tier="slm", rag_evidence=rag, ensure_slm=False)
    # Without HF, heuristic — but must carry RAG meta / note
    assert guided.get("engine") in {"slm_heuristic", "hf-slm-rag", "hf-slm"}
    assert guided.get("clades")
    if guided.get("engine") == "slm_heuristic":
        assert guided.get("rag") or "rag" in (guided.get("note") or "").lower() or guided.get("note")


def test_guide_slm_rag_when_slm_json_works(monkeypatch):
    monkeypatch.delenv("CODEEVOLVE_TAXONOMY_HEURISTIC", raising=False)
    monkeypatch.delenv("CODEEVOLVE_SKIP_HF", raising=False)

    def fake_slm_json(system, payload):
        assert "rag_chunks" in json_dumps_probe(payload)
        return {
            "clades": [
                {
                    "id": "clade_00",
                    "label": "api-core",
                    "role": "HTTP handlers evidenced by chunks",
                    "layer_hint": "core",
                    "type_path": ["architecture", "api", "handler"],
                }
            ]
        }

    import codeevolve.models.guide as guide_mod

    monkeypatch.setattr(guide_mod, "slm_enabled", lambda: True)
    monkeypatch.setattr(guide_mod, "ensure_default_slm", lambda download=None: {"ok": True})
    monkeypatch.setattr(guide_mod, "slm_json", fake_slm_json)

    guided = guide_taxonomy(
        [
            {
                "id": "clade_00",
                "label": "src",
                "layer": "core",
                "files": ["src/app.py"],
                "code_type": "architecture/api",
            }
        ],
        tier="slm",
        rag_evidence={
            "rag": {"chunk_count": 1},
            "evidence": {
                "clade_00": [{"path": "src/app.py", "score": 0.8, "text": "def handler(): pass"}]
            },
        },
        ensure_slm=False,
    )
    assert guided["engine"] == "hf-slm-rag"
    assert guided["clades"][0]["label"] == "api-core"
    assert guided["rag_chunks_used"] == 1


def json_dumps_probe(payload):
    import json

    return json.dumps(payload)


def test_build_taxonomy_indexes_rag(sample_repo, monkeypatch):
    monkeypatch.setenv("CODEEVOLVE_TAXONOMY_HEURISTIC", "1")
    monkeypatch.setenv("CODEEVOLVE_SKIP_HF", "1")
    monkeypatch.setenv("CODEEVOLVE_SKIP_EMBED", "1")
    monkeypatch.setenv("CODEEVOLVE_SKIP_GENSIM", "1")
    monkeypatch.setenv("CODEEVOLVE_VECTOR_BACKEND", "memory")
    commits = CodeEvolve(sample_repo).commits()
    tax = build_taxonomy(
        sample_repo,
        commits,
        guide=True,
        include_semantic=False,
        include_rag=True,
        vector_backend="memory",
    )
    assert tax.rag is not None
    assert tax.rag.get("chunk_count", 0) >= 1
    assert tax.guidance.get("engine") in {"slm_heuristic", "hf-slm-rag", "hf-slm"}
    bundle = evidence_bundle(
        build_rag_index(sample_repo, backend="memory"),
        [c.to_dict() for c in tax.clades],
    )
    assert "evidence" in bundle
