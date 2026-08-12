"""Select report/agent backend: auto | heuristic | slm | hf-qwen | openai | anthropic | grok | kimi | …"""

from __future__ import annotations

import os
from typing import Literal

from codeevolve.models.hardware import recommend_execution

BackendName = Literal[
    "heuristic",
    "slm",
    "hf-qwen",
    "openai",
    "anthropic",
    "openai_compatible",
    "grok",
    "kimi",
    "kimik3",
    "openrouter",
    "custom",
]


def resolve_backend_name(llm: str | bool | None = None) -> BackendName:
    """
    ``llm`` may be False/None (heuristic), True/'auto', or an explicit backend/provider name.
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
        if b in {"hf-qwen", "anthropic", "heuristic", "slm", "grok", "kimi"}:
            return b  # type: ignore[return-value]
        return "heuristic"

    name = str(llm).lower().strip()
    aliases = {
        "gpt": "openai",
        "claude": "anthropic",
        "xai": "grok",
        "moonshot": "kimi",
        "kimi-k3": "kimik3",
        "kimi_k3": "kimik3",
        "qwen": "hf-qwen",
        "huggingface": "hf-qwen",
        "hf": "hf-qwen",
        "local": "slm",
        "cloud": "openai_compatible",
    }
    name = aliases.get(name, name)
    if name in {"openai", "cloud"}:
        return "openai_compatible"
    if name in {
        "openai_compatible",
        "hf-qwen",
        "anthropic",
        "heuristic",
        "slm",
        "grok",
        "kimi",
        "kimik3",
        "openrouter",
        "custom",
    }:
        return name  # type: ignore[return-value]
    if name == "auto":
        return resolve_backend_name("auto")
    return "heuristic"
