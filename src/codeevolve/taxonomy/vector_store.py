"""Vector store backends: memory (default), ChromaDB, Pinecone."""

from __future__ import annotations

import hashlib
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from codeevolve.embeddings import cosine


def repo_namespace(repo: Path | str, display: str | None = None) -> str:
    raw = (display or str(repo)).replace("\\", "/")
    slug = re.sub(r"[^a-zA-Z0-9_-]+", "-", raw).strip("-").lower()[:48] or "repo"
    digest = hashlib.sha1(raw.encode("utf-8")).hexdigest()[:8]
    return f"ce-{slug}-{digest}"


@dataclass
class VectorRecord:
    id: str
    text: str
    vector: list[float]
    metadata: dict[str, Any] = field(default_factory=dict)


class VectorStore(Protocol):
    name: str

    def upsert(self, records: list[VectorRecord]) -> int: ...
    def query(self, vector: list[float], *, top_k: int = 8) -> list[dict[str, Any]]: ...
    def count(self) -> int: ...


class MemoryVectorStore:
    name = "memory"

    def __init__(self, namespace: str) -> None:
        self.namespace = namespace
        self._rows: dict[str, VectorRecord] = {}

    def upsert(self, records: list[VectorRecord]) -> int:
        for r in records:
            self._rows[r.id] = r
        return len(records)

    def query(self, vector: list[float], *, top_k: int = 8) -> list[dict[str, Any]]:
        scored = []
        for r in self._rows.values():
            scored.append(
                {
                    "id": r.id,
                    "score": cosine(vector, r.vector),
                    "text": r.text,
                    "metadata": r.metadata,
                }
            )
        scored.sort(key=lambda x: -x["score"])
        return scored[:top_k]

    def count(self) -> int:
        return len(self._rows)


class ChromaVectorStore:
    name = "chromadb"

    def __init__(self, namespace: str, *, persist_dir: Path | None = None) -> None:
        import chromadb
        from chromadb.config import Settings

        root = persist_dir or Path(os.environ.get("CODEEVOLVE_CHROMA_DIR", Path.home() / ".codeevolve" / "chroma"))
        root.mkdir(parents=True, exist_ok=True)
        self._client = chromadb.PersistentClient(
            path=str(root),
            settings=Settings(anonymized_telemetry=False),
        )
        self._col = self._client.get_or_create_collection(
            name=namespace[:63],
            metadata={"hnsw:space": "cosine"},
        )

    def upsert(self, records: list[VectorRecord]) -> int:
        if not records:
            return 0
        self._col.upsert(
            ids=[r.id for r in records],
            embeddings=[r.vector for r in records],
            documents=[r.text for r in records],
            metadatas=[{k: (v if isinstance(v, (str, int, float, bool)) else str(v)) for k, v in r.metadata.items()} for r in records],
        )
        return len(records)

    def query(self, vector: list[float], *, top_k: int = 8) -> list[dict[str, Any]]:
        res = self._col.query(query_embeddings=[vector], n_results=top_k)
        out: list[dict[str, Any]] = []
        ids = (res.get("ids") or [[]])[0]
        docs = (res.get("documents") or [[]])[0]
        metas = (res.get("metadatas") or [[]])[0]
        dists = (res.get("distances") or [[]])[0]
        for i, rid in enumerate(ids):
            dist = float(dists[i]) if i < len(dists) else 1.0
            out.append(
                {
                    "id": rid,
                    "score": 1.0 - dist,  # cosine distance → similarity-ish
                    "text": docs[i] if i < len(docs) else "",
                    "metadata": metas[i] if i < len(metas) else {},
                }
            )
        return out

    def count(self) -> int:
        return int(self._col.count())


class PineconeVectorStore:
    name = "pinecone"

    def __init__(self, namespace: str, *, dimension: int) -> None:
        from pinecone import Pinecone

        api_key = os.environ.get("PINECONE_API_KEY") or os.environ.get("CODEEVOLVE_PINECONE_API_KEY")
        if not api_key:
            raise RuntimeError("PINECONE_API_KEY not set")
        index_name = os.environ.get("CODEEVOLVE_PINECONE_INDEX") or os.environ.get("PINECONE_INDEX") or "codeevolve"
        self._ns = namespace[:45]
        self._pc = Pinecone(api_key=api_key)
        existing = {i["name"] for i in self._pc.list_indexes()}
        if index_name not in existing:
            # Serverless create is environment-specific; require pre-created index
            raise RuntimeError(
                f"Pinecone index '{index_name}' not found. Create it (dim={dimension}, cosine) then retry."
            )
        self._index = self._pc.Index(index_name)
        self._dimension = dimension

    def upsert(self, records: list[VectorRecord]) -> int:
        if not records:
            return 0
        vectors = []
        for r in records:
            meta = {k: (v if isinstance(v, (str, int, float, bool)) else str(v)) for k, v in r.metadata.items()}
            meta["text"] = r.text[:800]
            vectors.append({"id": r.id[:64], "values": r.vector, "metadata": meta})
        # batch
        for i in range(0, len(vectors), 100):
            self._index.upsert(vectors=vectors[i : i + 100], namespace=self._ns)
        return len(records)

    def query(self, vector: list[float], *, top_k: int = 8) -> list[dict[str, Any]]:
        res = self._index.query(vector=vector, top_k=top_k, namespace=self._ns, include_metadata=True)
        out = []
        for m in res.get("matches") or []:
            meta = m.get("metadata") or {}
            out.append(
                {
                    "id": m.get("id"),
                    "score": float(m.get("score") or 0.0),
                    "text": meta.get("text", ""),
                    "metadata": meta,
                }
            )
        return out

    def count(self) -> int:
        try:
            stats = self._index.describe_index_stats()
            ns = (stats.get("namespaces") or {}).get(self._ns) or {}
            return int(ns.get("vector_count") or 0)
        except Exception:
            return 0


def open_vector_store(
    namespace: str,
    *,
    dimension: int = 64,
    backend: str | None = None,
) -> VectorStore:
    """Resolve store: pinecone | chromadb | memory (default cascade)."""
    choice = (backend or os.environ.get("CODEEVOLVE_VECTOR_BACKEND") or "auto").lower()
    if choice in {"pinecone", "auto"} and (
        os.environ.get("PINECONE_API_KEY") or os.environ.get("CODEEVOLVE_PINECONE_API_KEY")
    ):
        if choice == "pinecone" or os.environ.get("CODEEVOLVE_VECTOR_BACKEND", "").lower() == "pinecone":
            try:
                return PineconeVectorStore(namespace, dimension=dimension)
            except Exception:
                if choice == "pinecone":
                    raise
    if choice in {"chromadb", "chroma", "auto"}:
        if choice.startswith("chroma") or os.environ.get("CODEEVOLVE_USE_CHROMA", "").lower() in {
            "1",
            "true",
            "yes",
        }:
            try:
                return ChromaVectorStore(namespace)
            except Exception:
                if choice.startswith("chroma"):
                    raise
        # auto: try chroma quietly
        if choice == "auto":
            try:
                import chromadb  # noqa: F401

                return ChromaVectorStore(namespace)
            except Exception:
                pass
    return MemoryVectorStore(namespace)
