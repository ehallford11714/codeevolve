"""In-memory agent stores: working, episodic, and semantic notes (+ embedded retrieval)."""

from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from codeevolve.embeddings import cosine, embed_text


MemoryKind = Literal["working", "episodic", "semantic", "tool", "reflection", "compact"]


@dataclass
class MemoryItem:
    id: str
    kind: MemoryKind
    content: str
    score: float = 1.0
    tags: list[str] = field(default_factory=list)
    meta: dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)
    vector: list[float] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "kind": self.kind,
            "content": self.content,
            "score": self.score,
            "tags": list(self.tags),
            "meta": dict(self.meta),
            "created_at": self.created_at,
            "embedded": self.vector is not None,
        }


class AgentMemory:
    """Process-local memory with optional JSON persistence under ``.codeevolve/agent``."""

    def __init__(self, *, persist_dir: Path | str | None = None, max_items: int = 500) -> None:
        self.persist_dir = Path(persist_dir) if persist_dir else None
        self.max_items = max_items
        self._items: dict[str, MemoryItem] = {}
        if self.persist_dir:
            self.persist_dir.mkdir(parents=True, exist_ok=True)
            self._load()

    def _load(self) -> None:
        path = self.persist_dir / "memory.json" if self.persist_dir else None
        if not path or not path.is_file():
            return
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            for row in data.get("items") or []:
                vec = row.get("vector")
                item = MemoryItem(
                    id=str(row.get("id") or uuid.uuid4().hex[:10]),
                    kind=row.get("kind") or "working",  # type: ignore[arg-type]
                    content=str(row.get("content") or ""),
                    score=float(row.get("score") or 1.0),
                    tags=list(row.get("tags") or []),
                    meta=dict(row.get("meta") or {}),
                    created_at=float(row.get("created_at") or time.time()),
                    vector=list(vec) if isinstance(vec, list) else None,
                )
                self._items[item.id] = item
        except (OSError, json.JSONDecodeError, TypeError, ValueError):
            return

    def save(self) -> None:
        if not self.persist_dir:
            return
        path = self.persist_dir / "memory.json"
        payload = {
            "items": [
                {**i.to_dict(), "vector": i.vector}
                for i in self._items.values()
            ]
        }
        path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")

    def add(
        self,
        content: str,
        *,
        kind: MemoryKind = "working",
        tags: list[str] | None = None,
        meta: dict[str, Any] | None = None,
        score: float = 1.0,
        embed: bool = True,
    ) -> MemoryItem:
        text = content[:8000]
        vector = None
        if embed and kind in {"working", "episodic", "semantic", "reflection", "compact"}:
            try:
                vector = embed_text(text)
            except Exception:  # noqa: BLE001
                vector = None
        item = MemoryItem(
            id=uuid.uuid4().hex[:12],
            kind=kind,
            content=text,
            score=score,
            tags=list(tags or []),
            meta=dict(meta or {}),
            vector=vector,
        )
        self._items[item.id] = item
        self._trim()
        return item

    def _trim(self) -> None:
        if len(self._items) <= self.max_items:
            return
        ordered = sorted(self._items.values(), key=lambda x: (x.score, x.created_at))
        for item in ordered[: max(0, len(self._items) - self.max_items)]:
            self._items.pop(item.id, None)

    def get(self, item_id: str) -> MemoryItem | None:
        return self._items.get(item_id)

    def list(
        self,
        *,
        kind: MemoryKind | None = None,
        tag: str | None = None,
        limit: int = 40,
    ) -> list[MemoryItem]:
        rows = list(self._items.values())
        if kind:
            rows = [r for r in rows if r.kind == kind]
        if tag:
            rows = [r for r in rows if tag in r.tags]
        rows.sort(key=lambda r: (-r.score, -r.created_at))
        return rows[:limit]

    def search(self, query: str, *, limit: int = 12) -> list[MemoryItem]:
        """Keyword search (legacy). Prefer ``retrieve`` for embedding similarity."""
        q = (query or "").lower().strip()
        if not q:
            return self.list(limit=limit)
        tokens = [t for t in q.split() if t]
        scored: list[tuple[float, MemoryItem]] = []
        for item in self._items.values():
            blob = (item.content + " " + " ".join(item.tags)).lower()
            hit = sum(1 for t in tokens if t in blob)
            if hit:
                scored.append((hit + item.score * 0.1, item))
        scored.sort(key=lambda x: -x[0])
        return [i for _, i in scored[:limit]]

    def retrieve(
        self,
        query: str,
        *,
        limit: int = 12,
        path: str | None = None,
        kinds: list[MemoryKind] | None = None,
    ) -> list[MemoryItem]:
        """Embedded retrieval over episodic/semantic/working notes (hash/MiniLM)."""
        q = (query or "").strip()
        if not q:
            return self.list(limit=limit)
        try:
            qv = embed_text(q)
        except Exception:  # noqa: BLE001
            return self.search(q, limit=limit)

        scored: list[tuple[float, MemoryItem]] = []
        for item in self._items.values():
            if kinds and item.kind not in kinds:
                continue
            if path and path not in item.content and path not in " ".join(item.tags):
                # soft filter — still allow high semantic matches later via score
                path_bonus = 0.0
            else:
                path_bonus = 0.05 if path else 0.0
            vec = item.vector
            if vec is None:
                try:
                    vec = embed_text(item.content)
                    item.vector = vec
                except Exception:  # noqa: BLE001
                    continue
            sim = cosine(qv, vec) + path_bonus + item.score * 0.01
            scored.append((sim, item))
        scored.sort(key=lambda x: -x[0])
        return [i for _, i in scored[:limit]]

    def retrieve_block(self, query: str, *, path: str | None = None, limit: int = 8) -> str:
        rows = self.retrieve(
            query,
            limit=limit,
            path=path,
            kinds=["working", "episodic", "semantic", "reflection", "compact"],
        )
        if not rows:
            return "(no embedded memory hits)"
        return "\n".join(f"- [{r.kind}] {r.content[:350]}" for r in rows)

    def working_snapshot(self, *, limit: int = 16) -> str:
        rows = self.list(kind="working", limit=limit) + self.list(kind="reflection", limit=4)
        if not rows:
            return "(empty working memory)"
        return "\n".join(f"- [{r.kind}] {r.content[:400]}" for r in rows[:limit])

    def to_dict(self) -> dict[str, Any]:
        by_kind: dict[str, int] = {}
        for item in self._items.values():
            by_kind[item.kind] = by_kind.get(item.kind, 0) + 1
        return {
            "count": len(self._items),
            "by_kind": by_kind,
            "items": [i.to_dict() for i in self.list(limit=80)],
        }
