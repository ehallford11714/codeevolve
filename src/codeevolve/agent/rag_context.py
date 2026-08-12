"""Agent-facing RAG: semantic chunks indexed in-memory (or chroma/pinecone)."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from codeevolve.taxonomy.rag import RagHit, RagIndex, build_rag_index, retrieve


@dataclass
class AgentRag:
    """Lazy RAG index for the coding agent (defaults to in-memory vector store)."""

    repo: Path
    backend: str = "memory"
    max_files: int = 200
    max_chunks: int = 800
    index: RagIndex | None = None
    last_hits: list[dict[str, Any]] = field(default_factory=list)

    def ensure(self, paths: list[str] | None = None) -> RagIndex:
        if self.index is None or (paths and not self.index.chunk_count):
            self.index = build_rag_index(
                self.repo,
                paths=paths,
                max_files=self.max_files,
                max_chunks=self.max_chunks,
                backend=self.backend,
            )
        return self.index

    def query(
        self,
        text: str,
        *,
        top_k: int = 8,
        paths: list[str] | None = None,
        rebuild: bool = False,
    ) -> list[RagHit]:
        if rebuild:
            self.index = None
        idx = self.ensure(paths)
        hits = retrieve(idx, text, top_k=top_k, path_filter=set(paths) if paths else None)
        self.last_hits = [h.to_dict() for h in hits]
        return hits

    def context_block(self, query: str, *, top_k: int = 6, paths: list[str] | None = None) -> str:
        hits = self.query(query, top_k=top_k, paths=paths)
        if not hits:
            return "(no RAG hits)"
        lines = ["# RAG semantic chunks", ""]
        for h in hits:
            lines.append(f"## {h.path}:{h.start_line}-{h.end_line} (score={h.score:.3f})")
            lines.append(h.text[:900])
            lines.append("")
        return "\n".join(lines)

    def to_dict(self) -> dict[str, Any]:
        return {
            "index": self.index.to_dict() if self.index else None,
            "backend": self.backend,
            "last_hits": list(self.last_hits)[:12],
        }
