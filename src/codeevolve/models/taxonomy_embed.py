"""Lightweight open-source embedder for taxonomy construction (MiniLM)."""

from __future__ import annotations

import os
import threading
from dataclasses import dataclass
from typing import Any, Sequence

# ~22M params, strong quality/size tradeoff for local taxonomy work
DEFAULT_TAXONOMY_EMBED_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
# Even lighter alternative
LIGHT_TAXONOMY_EMBED_MODEL = "sentence-transformers/paraphrase-MiniLM-L3-v2"

_LOCK = threading.Lock()
_CACHE: dict[str, Any] = {"model": None, "id": None}


@dataclass
class EmbedderInfo:
    model_id: str
    engine: str  # sentence_transformers | hash_fallback
    ok: bool
    dim: int = 0
    reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "model_id": self.model_id,
            "engine": self.engine,
            "ok": self.ok,
            "dim": self.dim,
            "reason": self.reason,
        }


def taxonomy_embed_enabled() -> bool:
    if os.environ.get("CODEEVOLVE_SKIP_EMBED", "").lower() in {"1", "true", "yes"}:
        return False
    # Reuse HF-skip in CI unless explicitly forcing embeds
    if os.environ.get("CODEEVOLVE_SKIP_HF", "").lower() in {"1", "true", "yes"}:
        if os.environ.get("CODEEVOLVE_FORCE_EMBED", "").lower() not in {"1", "true", "yes"}:
            return False
    return True


def resolve_taxonomy_embed_model() -> str:
    if os.environ.get("CODEEVOLVE_EMBED_MODEL"):
        return os.environ["CODEEVOLVE_EMBED_MODEL"]
    if os.environ.get("CODEEVOLVE_EMBED_LIGHT", "").lower() in {"1", "true", "yes"}:
        return LIGHT_TAXONOMY_EMBED_MODEL
    return DEFAULT_TAXONOMY_EMBED_MODEL


def ensure_taxonomy_embedder(*, download: bool | None = None) -> EmbedderInfo:
    """Ensure MiniLM-class embedder is available; download on first use when allowed."""
    mid = resolve_taxonomy_embed_model()
    if not taxonomy_embed_enabled():
        return EmbedderInfo(mid, "hash_fallback", False, reason="embedder disabled by env")
    try:
        import numpy  # noqa: F401
        from sentence_transformers import SentenceTransformer  # noqa: F401
    except Exception as exc:
        return EmbedderInfo(mid, "hash_fallback", False, reason=f"missing deps: {exc}")

    no_dl = os.environ.get("CODEEVOLVE_EMBED_NO_DOWNLOAD", "").lower() in {"1", "true", "yes"}
    do_download = (True if download is None else download) and not no_dl
    if os.environ.get("CODEEVOLVE_EMBED_DOWNLOAD", "").lower() in {"0", "false", "no"}:
        do_download = False

    if not do_download:
        return EmbedderInfo(
            mid,
            "sentence_transformers",
            True,
            reason="deps ok; first taxonomy build downloads weights unless CODEEVOLVE_EMBED_NO_DOWNLOAD=1",
        )
    try:
        model = _load(mid)
        dim = int(model.get_sentence_embedding_dimension())
        return EmbedderInfo(mid, "sentence_transformers", True, dim=dim, reason="embedder ready")
    except Exception as exc:
        return EmbedderInfo(mid, "hash_fallback", False, reason=str(exc))


def _load(model_id: str) -> Any:
    with _LOCK:
        if _CACHE["model"] is not None and _CACHE["id"] == model_id:
            return _CACHE["model"]
        from sentence_transformers import SentenceTransformer

        model = SentenceTransformer(model_id)
        _CACHE["model"], _CACHE["id"] = model, model_id
        return model


def embed_taxonomy_texts(texts: Sequence[str], *, dim: int = 64) -> tuple[list[list[float]], EmbedderInfo]:
    """
    Batch-embed documents for taxonomy niches.

    Prefers lightweight MiniLM; falls back to hashing-trick vectors.
    """
    from codeevolve.embeddings import _hash_embed

    mid = resolve_taxonomy_embed_model()
    if not texts:
        return [], EmbedderInfo(mid, "hash_fallback", False, dim=dim, reason="empty")

    if taxonomy_embed_enabled():
        try:
            model = _load(mid)
            vecs = model.encode(
                list(texts),
                normalize_embeddings=True,
                show_progress_bar=False,
                batch_size=min(64, max(8, len(texts))),
            )
            out = [[float(x) for x in row] for row in vecs]
            return out, EmbedderInfo(
                mid,
                "sentence_transformers",
                True,
                dim=len(out[0]) if out else 0,
                reason="batch MiniLM taxonomy embeddings",
            )
        except Exception as exc:
            info = EmbedderInfo(mid, "hash_fallback", False, dim=dim, reason=f"st failed: {exc}")
    else:
        info = EmbedderInfo(mid, "hash_fallback", False, dim=dim, reason="embedder disabled")

    return [_hash_embed(t, dim=dim) for t in texts], info
