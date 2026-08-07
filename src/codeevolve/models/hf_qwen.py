"""Ensure / probe local Hugging Face Qwen availability."""

from __future__ import annotations

import os
from typing import Any

from codeevolve.models.hardware import pick_qwen_model


def ensure_hf_qwen(model_id: str | None = None) -> dict[str, Any]:
    """
    Probe whether local HF Qwen can be used.

    Does not download by default unless CODEEVOLVE_HF_DOWNLOAD=1.
    """
    mid = model_id or os.environ.get("CODEEVOLVE_HF_MODEL") or pick_qwen_model()
    if os.environ.get("CODEEVOLVE_SKIP_HF", "").lower() in {"1", "true", "yes"}:
        return {"ok": False, "model": mid, "reason": "CODEEVOLVE_SKIP_HF set"}
    try:
        import torch  # noqa: F401
        from transformers import AutoConfig  # noqa: F401
    except Exception as exc:
        return {"ok": False, "model": mid, "reason": f"missing deps: {exc}"}

    download = os.environ.get("CODEEVOLVE_HF_DOWNLOAD", "").lower() in {"1", "true", "yes"}
    if not download:
        return {
            "ok": True,
            "model": mid,
            "reason": "transformers/torch importable; set CODEEVOLVE_HF_DOWNLOAD=1 to prefetch",
            "downloaded": False,
        }
    try:
        from transformers import AutoTokenizer

        AutoTokenizer.from_pretrained(mid, trust_remote_code=True)
        return {"ok": True, "model": mid, "reason": "tokenizer fetched", "downloaded": True}
    except Exception as exc:
        return {"ok": False, "model": mid, "reason": f"download failed: {exc}", "downloaded": False}
