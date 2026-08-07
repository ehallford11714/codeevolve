"""Select report backend: auto | heuristic | hf-qwen | openai | anthropic."""

from __future__ import annotations

import os
from typing import Literal

from codeevolve.models.hardware import recommend_execution

BackendName = Literal["heuristic", "hf-qwen", "openai", "anthropic", "openai_compatible"]


def resolve_backend_name(llm: str | bool | None = None) -> BackendName:
    """
    ``llm`` may be False/None (heuristic), True/'auto', or an explicit backend name.
    """
    if llm is None or llm is False or llm == "" or llm == "heuristic":
        env = os.environ.get("CODEEVOLVE_LLM_BACKEND", "").lower().strip()
        if not env or env == "heuristic":
            if os.environ.get("CODEEVOLVE_USE_LLM", "").lower() in {"1", "true", "yes"}:
                return "openai_compatible"
            return "heuristic"
        llm = env

    if llm is True or llm == "auto":
        rec = recommend_execution()
        b = str(rec.get("backend") or "heuristic")
        if b == "openai":
            return "openai_compatible"
        if b in {"hf-qwen", "anthropic", "heuristic"}:
            return b  # type: ignore[return-value]
        return "heuristic"

    name = str(llm).lower().strip()
    if name in {"openai", "openai_compatible", "cloud"}:
        return "openai_compatible"
    if name in {"hf-qwen", "qwen", "huggingface"}:
        return "hf-qwen"
    if name == "anthropic":
        return "anthropic"
    if name == "auto":
        return resolve_backend_name("auto")
    return "heuristic"
