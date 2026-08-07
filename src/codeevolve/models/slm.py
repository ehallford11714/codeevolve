"""Real default SLM runtime: on-demand Qwen2.5-0.5B for taxonomy guidance."""

from __future__ import annotations

import json
import os
import threading
from typing import Any, Optional

from codeevolve.models.tiers import tier_spec

_LOCK = threading.Lock()
_CACHE: dict[str, Any] = {"tok": None, "model": None, "id": None}


DEFAULT_SLM = "Qwen/Qwen2.5-0.5B-Instruct"


def slm_enabled() -> bool:
    if os.environ.get("CODEEVOLVE_SKIP_HF", "").lower() in {"1", "true", "yes"}:
        return False
    if os.environ.get("CODEEVOLVE_TAXONOMY_HEURISTIC", "").lower() in {"1", "true", "yes"}:
        return False
    return True


def ensure_default_slm(*, download: bool | None = None) -> dict[str, Any]:
    """
    Ensure the default SLM is importable; download weights when allowed.

    Default: download on first use unless CODEEVOLVE_SLM_NO_DOWNLOAD=1.
    """
    mid = os.environ.get("CODEEVOLVE_HF_MODEL") or tier_spec("slm").hf_model or DEFAULT_SLM
    if not slm_enabled():
        return {"ok": False, "model": mid, "reason": "SLM disabled by env"}
    try:
        import torch  # noqa: F401
        from transformers import AutoModelForCausalLM, AutoTokenizer  # noqa: F401
    except Exception as exc:
        return {"ok": False, "model": mid, "reason": f"missing deps: {exc}"}

    no_dl = os.environ.get("CODEEVOLVE_SLM_NO_DOWNLOAD", "").lower() in {"1", "true", "yes"}
    do_download = (True if download is None else download) and not no_dl
    # Prefer explicit download flag
    if os.environ.get("CODEEVOLVE_HF_DOWNLOAD", "").lower() in {"1", "true", "yes"}:
        do_download = True
    if os.environ.get("CODEEVOLVE_SLM_DOWNLOAD", "").lower() in {"0", "false", "no"}:
        do_download = False

    if not do_download:
        return {
            "ok": True,
            "model": mid,
            "downloaded": False,
            "reason": "deps ok; set CODEEVOLVE_HF_DOWNLOAD=1 or leave default for first-use download",
        }

    try:
        _load_slm(mid)
        return {"ok": True, "model": mid, "downloaded": True, "reason": "SLM ready"}
    except Exception as exc:
        return {"ok": False, "model": mid, "reason": str(exc), "downloaded": False}


def _load_slm(model_id: str) -> tuple[Any, Any]:
    with _LOCK:
        if _CACHE["model"] is not None and _CACHE["id"] == model_id:
            return _CACHE["tok"], _CACHE["model"]
        from transformers import AutoModelForCausalLM, AutoTokenizer
        import torch

        tok = AutoTokenizer.from_pretrained(model_id, trust_remote_code=True)
        model = AutoModelForCausalLM.from_pretrained(
            model_id,
            trust_remote_code=True,
            torch_dtype=torch.float16 if torch.cuda.is_available() else torch.float32,
            device_map="auto" if torch.cuda.is_available() else None,
            low_cpu_mem_usage=True,
        )
        _CACHE["tok"], _CACHE["model"], _CACHE["id"] = tok, model, model_id
        return tok, model


def slm_complete(system: str, user: str, *, max_new_tokens: int = 512) -> Optional[str]:
    """Run a short completion on the default SLM. Returns None if unavailable."""
    if not slm_enabled():
        return None
    mid = os.environ.get("CODEEVOLVE_HF_MODEL") or DEFAULT_SLM
    # Auto-download by default for real SLM path
    status = ensure_default_slm(download=None)
    if not status.get("ok"):
        # try load without forcing download if already cached locally
        try:
            tok, model = _load_slm(mid)
        except Exception:
            return None
    else:
        try:
            tok, model = _load_slm(mid)
        except Exception:
            return None

    import torch

    prompt = (
        f"<|im_start|>system\n{system}<|im_end|>\n"
        f"<|im_start|>user\n{user[:8000]}<|im_end|>\n"
        f"<|im_start|>assistant\n"
    )
    inputs = tok(prompt, return_tensors="pt")
    if torch.cuda.is_available():
        inputs = {k: v.to(model.device) for k, v in inputs.items()}
    with torch.no_grad():
        out = model.generate(**inputs, max_new_tokens=max_new_tokens, do_sample=False)
    text = tok.decode(out[0], skip_special_tokens=True)
    if "assistant" in text:
        text = text.split("assistant")[-1].strip()
    return text or None


def slm_json(system: str, payload: dict[str, Any]) -> Optional[dict[str, Any]]:
    raw = slm_complete(system, json.dumps(payload, default=str), max_new_tokens=700)
    if not raw:
        return None
    raw = raw.strip()
    try:
        data = json.loads(raw)
        return data if isinstance(data, dict) else None
    except json.JSONDecodeError:
        import re

        m = re.search(r"\{[\s\S]*\}", raw)
        if not m:
            return None
        try:
            data = json.loads(m.group(0))
            return data if isinstance(data, dict) else None
        except json.JSONDecodeError:
            return None
