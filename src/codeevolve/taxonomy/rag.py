"""Chunk the codebase, index with embeddings, retrieve evidence for SLM taxonomy."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

from codeevolve.models.taxonomy_embed import embed_taxonomy_texts
from codeevolve.taxonomy.vector_store import VectorRecord, open_vector_store, repo_namespace

_SKIP_DIRS = {
    ".git",
    ".venv",
    "venv",
    "node_modules",
    "__pycache__",
    ".tox",
    "dist",
    "build",
    ".mypy_cache",
    ".pytest_cache",
    ".codeevolve",
    ".codeevolve_eval",
}
_CODE_EXT = {
    ".py",
    ".ts",
    ".tsx",
    ".js",
    ".jsx",
    ".go",
    ".rs",
    ".java",
    ".kt",
    ".rb",
    ".php",
    ".cs",
    ".cpp",
    ".c",
    ".h",
    ".md",
    ".toml",
    ".yml",
    ".yaml",
    ".json",
    ".sql",
    ".proto",
}


@dataclass
class CodeChunk:
    id: str
    path: str
    index: int
    text: str
    start_line: int
    end_line: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "path": self.path,
            "index": self.index,
            "start_line": self.start_line,
            "end_line": self.end_line,
            "text": self.text[:1200],
            "chars": len(self.text),
        }


@dataclass
class RagHit:
    chunk_id: str
    path: str
    score: float
    text: str
    start_line: int = 0
    end_line: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "chunk_id": self.chunk_id,
            "path": self.path,
            "score": round(self.score, 4),
            "start_line": self.start_line,
            "end_line": self.end_line,
            "text": self.text[:700],
        }


@dataclass
class RagIndex:
    namespace: str
    backend: str
    chunk_count: int = 0
    file_count: int = 0
    embedder: dict[str, Any] = field(default_factory=dict)
    store: Any = None
    chunks_by_path: dict[str, list[str]] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "namespace": self.namespace,
            "backend": self.backend,
            "chunk_count": self.chunk_count,
            "file_count": self.file_count,
            "embedder": dict(self.embedder),
            "paths_indexed": len(self.chunks_by_path),
        }


def chunk_text(text: str, *, max_chars: int = 700, overlap: int = 80) -> list[tuple[int, int, str]]:
    """Split text into overlapping chunks; returns (start_line, end_line, chunk)."""
    lines = text.splitlines()
    if not lines:
        return []
    chunks: list[tuple[int, int, str]] = []
    buf: list[str] = []
    start = 1
    size = 0
    for i, ln in enumerate(lines, start=1):
        # Prefer splitting on blank lines / def/class headers when buffer is large
        boundary = (not ln.strip()) or bool(re.match(r"^\s*(def |class |function |export |pub )", ln))
        buf.append(ln)
        size += len(ln) + 1
        if size >= max_chars and (boundary or size >= max_chars * 1.4):
            chunk = "\n".join(buf).strip()
            if chunk:
                chunks.append((start, i, chunk[: max_chars + 200]))
            # overlap: keep trailing lines
            keep: list[str] = []
            keep_size = 0
            for prev in reversed(buf):
                keep_size += len(prev) + 1
                keep.append(prev)
                if keep_size >= overlap:
                    break
            buf = list(reversed(keep))
            start = max(1, i - len(buf) + 1)
            size = sum(len(x) + 1 for x in buf)
    if buf:
        chunk = "\n".join(buf).strip()
        if chunk:
            chunks.append((start, start + len(buf) - 1, chunk[: max_chars + 200]))
    return chunks[:40]  # per-file cap


def chunk_file(repo: Path, path: str, *, max_chars: int = 700) -> list[CodeChunk]:
    fp = repo / path
    if not fp.is_file():
        return []
    try:
        text = fp.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    if len(text) > 120_000:
        text = text[:120_000]
    out: list[CodeChunk] = []
    for ix, (a, b, body) in enumerate(chunk_text(text, max_chars=max_chars)):
        digest = hashlib.sha1(f"{path}:{ix}:{body[:80]}".encode()).hexdigest()[:12]
        out.append(
            CodeChunk(
                id=f"{path}:{ix}:{digest}",
                path=path,
                index=ix,
                text=f"FILE {path} L{a}-{b}\n{body}",
                start_line=a,
                end_line=b,
            )
        )
    return out


def _iter_paths(repo: Path, paths: Iterable[str] | None, *, max_files: int) -> list[str]:
    if paths:
        return [p.replace("\\", "/") for p in list(paths)[:max_files]]
    found: list[str] = []
    for p in repo.rglob("*"):
        if not p.is_file():
            continue
        rel = p.relative_to(repo).as_posix()
        if any(part in _SKIP_DIRS for part in rel.split("/")):
            continue
        if p.suffix.lower() not in _CODE_EXT:
            continue
        found.append(rel)
        if len(found) >= max_files:
            break
    return found


def build_rag_index(
    repo: Path | str,
    paths: Iterable[str] | None = None,
    *,
    display: str | None = None,
    max_files: int = 250,
    max_chunks: int = 1200,
    backend: str | None = None,
    chunk_chars: int = 700,
) -> RagIndex:
    """Chunk source files, embed, and upsert into the vector store."""
    repo = Path(repo)
    ns = repo_namespace(repo, display) + "-rag"
    file_paths = _iter_paths(repo, paths, max_files=max_files)
    chunks: list[CodeChunk] = []
    by_path: dict[str, list[str]] = {}
    for path in file_paths:
        file_chunks = chunk_file(repo, path, max_chars=chunk_chars)
        if not file_chunks:
            continue
        by_path[path] = [c.id for c in file_chunks]
        chunks.extend(file_chunks)
        if len(chunks) >= max_chunks:
            chunks = chunks[:max_chunks]
            break

    if not chunks:
        store = open_vector_store(ns, dimension=64, backend=backend or "memory")
        return RagIndex(namespace=ns, backend=getattr(store, "name", "memory"), store=store)

    texts = [c.text for c in chunks]
    vectors, info = embed_taxonomy_texts(texts)
    dim = len(vectors[0]) if vectors else 64
    store = open_vector_store(ns, dimension=dim, backend=backend)
    records = [
        VectorRecord(
            id=c.id[:120],
            text=c.text,
            vector=vectors[i] if i < len(vectors) else [0.0] * dim,
            metadata={
                "path": c.path,
                "chunk_index": c.index,
                "start_line": c.start_line,
                "end_line": c.end_line,
            },
        )
        for i, c in enumerate(chunks)
    ]
    store.upsert(records)
    return RagIndex(
        namespace=ns,
        backend=getattr(store, "name", backend or "memory"),
        chunk_count=len(records),
        file_count=len(by_path),
        embedder=info.to_dict() if hasattr(info, "to_dict") else {"engine": getattr(info, "engine", "unknown")},
        store=store,
        chunks_by_path=by_path,
    )


def retrieve(
    index: RagIndex,
    query: str,
    *,
    top_k: int = 8,
    path_filter: set[str] | None = None,
) -> list[RagHit]:
    """Embed query and return top chunks; optional path filter (soft preference)."""
    if not index.store or not query.strip():
        return []
    vecs, _ = embed_taxonomy_texts([query])
    if not vecs:
        return []
    # Over-fetch then filter
    fetch_k = top_k * 4 if path_filter else top_k
    raw = index.store.query(vecs[0], top_k=min(40, max(fetch_k, top_k)))
    hits: list[RagHit] = []
    for row in raw:
        meta = row.get("metadata") or {}
        path = str(meta.get("path") or "")
        text = str(row.get("text") or "")
        score = float(row.get("score") or 0.0)
        if path_filter and path and path not in path_filter:
            score *= 0.55  # soft downrank outside clade
        hits.append(
            RagHit(
                chunk_id=str(row.get("id") or ""),
                path=path,
                score=score,
                text=text,
                start_line=int(meta.get("start_line") or 0),
                end_line=int(meta.get("end_line") or 0),
            )
        )
    hits.sort(key=lambda h: -h.score)
    return hits[:top_k]


def retrieve_for_clade(
    index: RagIndex,
    clade: dict[str, Any],
    *,
    top_k: int = 6,
) -> list[RagHit]:
    files = [str(f) for f in (clade.get("files") or [])[:40]]
    code_type = clade.get("code_type") or "/".join(clade.get("type_path") or [])
    label = clade.get("label") or clade.get("id")
    query = (
        f"taxonomy role for clade {clade.get('id')} labeled {label} "
        f"type {code_type} layer {clade.get('layer')} "
        f"files {' '.join(files[:12])}"
    )
    return retrieve(index, query, top_k=top_k, path_filter=set(files) if files else None)


def evidence_bundle(
    index: RagIndex,
    clades: list[dict[str, Any]],
    *,
    per_clade: int = 5,
    max_clades: int = 12,
) -> dict[str, Any]:
    """Build RAG evidence payload for the SLM taxonomy guide."""
    by_clade: dict[str, list[dict[str, Any]]] = {}
    for c in clades[:max_clades]:
        cid = str(c.get("id") or "")
        hits = retrieve_for_clade(index, c, top_k=per_clade)
        by_clade[cid] = [h.to_dict() for h in hits]
    return {
        "rag": index.to_dict(),
        "evidence": by_clade,
        "instructions": (
            "Use retrieved code chunks as ground truth for labels and roles. "
            "Do not invent APIs that are not evidenced. Prefer type_path refinement "
            "when chunks clearly show api/data/ui/test/infra concerns."
        ),
    }
