"""Embedding helpers — hash vectors; taxonomy prefers lightweight MiniLM."""

from __future__ import annotations

import hashlib
import math
import os
import re
from typing import Iterable, Sequence

_TOKEN = re.compile(r"[A-Za-z_][A-Za-z0-9_]{2,}")
_ST_MODEL = None


def tokenize(text: str) -> list[str]:
    return [t.lower() for t in _TOKEN.findall(text or "")]


def _use_sentence_transformers() -> bool:
    if os.environ.get("CODEEVOLVE_EMBED_MODEL"):
        return True
    return os.environ.get("CODEEVOLVE_USE_ST_EMBED", "").lower() in {"1", "true", "yes"}


def embed_text(text: str, *, dim: int = 64, for_taxonomy: bool = False) -> list[float]:
    """Embed text. Taxonomy path prefers MiniLM; else optional ST / hash."""
    if for_taxonomy:
        from codeevolve.models.taxonomy_embed import embed_taxonomy_texts

        vecs, _ = embed_taxonomy_texts([text or ""], dim=dim)
        return vecs[0] if vecs else _hash_embed(text, dim=dim)
    if _use_sentence_transformers():
        vec = _st_embed(text)
        if vec is not None:
            return vec
    return _hash_embed(text, dim=dim)


def embed_texts(texts: Sequence[str], *, dim: int = 64, for_taxonomy: bool = False) -> list[list[float]]:
    if for_taxonomy:
        from codeevolve.models.taxonomy_embed import embed_taxonomy_texts

        vecs, _ = embed_taxonomy_texts(texts, dim=dim)
        return vecs
    return [embed_text(t, dim=dim) for t in texts]


def _hash_embed(text: str, *, dim: int = 64) -> list[float]:
    vec = [0.0] * dim
    for tok in tokenize(text):
        h = hashlib.sha256(tok.encode("utf-8")).hexdigest()
        idx = int(h[:8], 16) % dim
        sign = 1.0 if int(h[8:10], 16) % 2 == 0 else -1.0
        vec[idx] += sign
    norm = math.sqrt(sum(v * v for v in vec)) or 1.0
    return [v / norm for v in vec]


def _st_embed(text: str) -> list[float] | None:
    global _ST_MODEL
    try:
        from sentence_transformers import SentenceTransformer
    except Exception:
        return None
    mid = os.environ.get("CODEEVOLVE_EMBED_MODEL") or "sentence-transformers/all-MiniLM-L6-v2"
    try:
        if _ST_MODEL is None or getattr(_ST_MODEL, "_ce_id", None) != mid:
            _ST_MODEL = SentenceTransformer(mid)
            setattr(_ST_MODEL, "_ce_id", mid)
        v = _ST_MODEL.encode(text or "", normalize_embeddings=True)
        return [float(x) for x in v]
    except Exception:
        return None


def cosine(a: Sequence[float], b: Sequence[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    return float(sum(x * y for x, y in zip(a, b)))


def mean_embed(texts: Iterable[str], *, dim: int = 64, for_taxonomy: bool = False) -> list[float]:
    items = list(texts)
    if not items:
        return [0.0] * dim
    if for_taxonomy:
        vecs = embed_texts(items, dim=dim, for_taxonomy=True)
    else:
        vecs = [embed_text(t, dim=dim) for t in items]
    acc = [0.0] * len(vecs[0])
    for v in vecs:
        for i, x in enumerate(v):
            acc[i] += x
    n = float(len(vecs))
    return [x / n for x in acc]
