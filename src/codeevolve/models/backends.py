"""Narrative backends: heuristic, OpenAI-compatible, Anthropic, HF Qwen."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any, Protocol

from codeevolve.models.hardware import pick_qwen_model
from codeevolve.models.router import BackendName, resolve_backend_name


class NarrativeBackend(Protocol):
    name: str

    def write(self, system: str, user_payload: dict[str, Any]) -> str: ...


class HeuristicNarrative:
    name = "heuristic"

    def write(self, system: str, user_payload: dict[str, Any]) -> str:
        # Caller should prefer dedicated template writers; this is a thin fallback.
        return (
            f"# Narrative\n\n_Backend: heuristic_\n\n"
            f"System intent: {system[:200]}…\n\n"
            f"```json\n{json.dumps(user_payload, indent=2, default=str)[:4000]}\n```\n"
        )


class OpenAICompatibleNarrative:
    name = "openai_compatible"

    def __init__(self) -> None:
        self.api_key = os.environ.get("CODEEVOLVE_LLM_API_KEY") or os.environ.get("OPENAI_API_KEY")
        self.base_url = (os.environ.get("CODEEVOLVE_LLM_BASE_URL") or "https://api.openai.com/v1").rstrip("/")
        self.model = os.environ.get("CODEEVOLVE_LLM_MODEL") or "gpt-4o-mini"

    def write(self, system: str, user_payload: dict[str, Any]) -> str:
        if not self.api_key:
            return HeuristicNarrative().write(system, user_payload)
        payload = {
            "model": self.model,
            "temperature": 0.3,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": json.dumps(user_payload, default=str)},
            ],
        }
        req = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=90) as resp:  # noqa: S310
                data = json.loads(resp.read().decode("utf-8"))
            return data["choices"][0]["message"]["content"]
        except (urllib.error.URLError, urllib.error.HTTPError, KeyError, json.JSONDecodeError, TimeoutError):
            return HeuristicNarrative().write(system, user_payload)


class AnthropicNarrative:
    name = "anthropic"

    def __init__(self) -> None:
        self.api_key = os.environ.get("ANTHROPIC_API_KEY")
        self.model = os.environ.get("CODEEVOLVE_ANTHROPIC_MODEL") or "claude-sonnet-4-20250514"

    def write(self, system: str, user_payload: dict[str, Any]) -> str:
        if not self.api_key:
            return HeuristicNarrative().write(system, user_payload)
        payload = {
            "model": self.model,
            "max_tokens": 4096,
            "system": system,
            "messages": [{"role": "user", "content": json.dumps(user_payload, default=str)}],
        }
        req = urllib.request.Request(
            "https://api.anthropic.com/v1/messages",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "x-api-key": self.api_key,
                "anthropic-version": "2023-06-01",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=90) as resp:  # noqa: S310
                data = json.loads(resp.read().decode("utf-8"))
            blocks = data.get("content") or []
            texts = [b.get("text", "") for b in blocks if isinstance(b, dict)]
            return "\n".join(texts) or HeuristicNarrative().write(system, user_payload)
        except (urllib.error.URLError, urllib.error.HTTPError, KeyError, json.JSONDecodeError, TimeoutError):
            return HeuristicNarrative().write(system, user_payload)


class HFQwenNarrative:
    """Local Hugging Face Qwen — optional heavy deps; falls back to heuristic."""

    name = "hf-qwen"

    def write(self, system: str, user_payload: dict[str, Any]) -> str:
        if os.environ.get("CODEEVOLVE_SKIP_HF", "").lower() in {"1", "true", "yes"}:
            return HeuristicNarrative().write(system, user_payload)
        model_id = os.environ.get("CODEEVOLVE_HF_MODEL") or pick_qwen_model()
        try:
            from transformers import AutoModelForCausalLM, AutoTokenizer  # type: ignore
            import torch  # type: ignore
        except Exception:
            return (
                HeuristicNarrative().write(system, user_payload)
                + f"\n\n_Note: transformers/torch unavailable; wanted `{model_id}`._\n"
            )

        prompt = (
            f"<|im_start|>system\n{system}<|im_end|>\n"
            f"<|im_start|>user\n{json.dumps(user_payload, default=str)[:12000]}<|im_end|>\n"
            f"<|im_start|>assistant\n"
        )
        try:
            tok = AutoTokenizer.from_pretrained(model_id, trust_remote_code=True)
            model = AutoModelForCausalLM.from_pretrained(
                model_id,
                trust_remote_code=True,
                torch_dtype=torch.float16 if torch.cuda.is_available() else torch.float32,
                device_map="auto" if torch.cuda.is_available() else None,
            )
            inputs = tok(prompt, return_tensors="pt")
            if torch.cuda.is_available():
                inputs = {k: v.to(model.device) for k, v in inputs.items()}
            out = model.generate(**inputs, max_new_tokens=900, do_sample=False)
            text = tok.decode(out[0], skip_special_tokens=True)
            if "assistant" in text:
                text = text.split("assistant")[-1].strip()
            return text or HeuristicNarrative().write(system, user_payload)
        except Exception as exc:
            return HeuristicNarrative().write(system, user_payload) + f"\n\n_HF Qwen error: {exc}_\n"


def get_narrative_backend(llm: str | bool | None = None) -> NarrativeBackend:
    name: BackendName = resolve_backend_name(llm)
    if name == "hf-qwen":
        return HFQwenNarrative()
    if name == "anthropic":
        return AnthropicNarrative()
    if name in {"openai_compatible", "openai"}:  # type: ignore[comparison-overlap]
        return OpenAICompatibleNarrative()
    return HeuristicNarrative()
