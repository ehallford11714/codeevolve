"""Embedding helpers — hash vectors by default; optional numpy / external models later."""

from __future__ import annotations

import hashlib
import math
import re
from typing import Iterable, Sequence


_TOKEN = re.compile(r"[A-Za-z_][A-Za-z0-9_]{2,}")


def tokenize(text: str) -> list[str]:
    return [t.lower() for t in _TOKEN.findall(text or "")]


def embed_text(text: str, *, dim: int = 64) -> list[float]:
    """Deterministic bag-of-tokens hashing trick embedding (no heavy deps)."""
    vec = [0.0] * dim
    for tok in tokenize(text):
        h = hashlib.sha256(tok.encode("utf-8")).hexdigest()
        idx = int(h[:8], 16) % dim
        sign = 1.0 if int(h[8:10], 16) % 2 == 0 else -1.0
        vec[idx] += sign
    norm = math.sqrt(sum(v * v for v in vec)) or 1.0
    return [v / norm for v in vec]


def cosine(a: Sequence[float], b: Sequence[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    return float(sum(x * y for x, y in zip(a, b)))


def mean_embed(texts: Iterable[str], *, dim: int = 64) -> list[float]:
    acc = [0.0] * dim
    n = 0
    for t in texts:
        v = embed_text(t, dim=dim)
        for i, x in enumerate(v):
            acc[i] += x
        n += 1
    if n == 0:
        return acc
    return [x / n for x in acc]
