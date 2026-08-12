"""LLM backends: heuristic, SLM, HF Qwen, OpenAI-compatible, Anthropic."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any, Protocol

from codeevolve.models.endpoints import EndpointConfig, resolve_endpoint
from codeevolve.models.hardware import pick_qwen_model
from codeevolve.models.router import resolve_backend_name


class NarrativeBackend(Protocol):
    name: str

    def write(self, system: str, user_payload: dict[str, Any]) -> str: ...


class ChatBackend(Protocol):
    """Coding-agent chat completion backend."""

    name: str
    endpoint: EndpointConfig

    def complete(self, system: str, user: str, *, temperature: float = 0.2, max_tokens: int = 4096) -> str: ...


class HeuristicNarrative:
    name = "heuristic"

    def write(self, system: str, user_payload: dict[str, Any]) -> str:
        return (
            f"# Narrative\n\n_Backend: heuristic_\n\n"
            f"System intent: {system[:200]}…\n\n"
            f"```json\n{json.dumps(user_payload, indent=2, default=str)[:4000]}\n```\n"
        )


class HeuristicChat:
    name = "heuristic"

    def __init__(self, endpoint: EndpointConfig | None = None) -> None:
        self.endpoint = endpoint or EndpointConfig(
            provider="heuristic", kind="heuristic", model="heuristic", source="default"
        )

    def complete(self, system: str, user: str, *, temperature: float = 0.2, max_tokens: int = 4096) -> str:
        return (
            f"# Heuristic (no LLM configured)\n\n{system[:300]}\n\n"
            f"User request excerpt:\n{user[:2000]}\n"
        )

    def write(self, system: str, user_payload: dict[str, Any]) -> str:
        return HeuristicNarrative().write(system, user_payload)


def _openai_chat(
    *,
    base_url: str,
    api_key: str,
    model: str,
    system: str,
    user: str,
    temperature: float,
    max_tokens: int,
    timeout: int = 180,
) -> str:
    payload = {
        "model": model,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    }
    req = urllib.request.Request(
        f"{base_url.rstrip('/')}/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310
        data = json.loads(resp.read().decode("utf-8"))
    return str(data["choices"][0]["message"]["content"])


def _anthropic_chat(
    *,
    api_key: str,
    model: str,
    system: str,
    user: str,
    max_tokens: int,
    timeout: int = 180,
) -> str:
    payload = {
        "model": model,
        "max_tokens": max_tokens,
        "system": system,
        "messages": [{"role": "user", "content": user}],
    }
    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310
        data = json.loads(resp.read().decode("utf-8"))
    blocks = data.get("content") or []
    texts = [b.get("text", "") for b in blocks if isinstance(b, dict)]
    return "\n".join(texts)


class OpenAICompatibleBackend:
    """OpenAI / Grok / Kimi / OpenRouter / custom OpenAI-compatible chat."""

    def __init__(self, endpoint: EndpointConfig) -> None:
        self.endpoint = endpoint
        self.name = endpoint.provider
        self.api_key = endpoint.api_key or ""
        self.base_url = (endpoint.base_url or "https://api.openai.com/v1").rstrip("/")
        self.model = endpoint.model

    def complete(self, system: str, user: str, *, temperature: float = 0.2, max_tokens: int = 4096) -> str:
        if not self.api_key:
            return HeuristicChat(self.endpoint).complete(system, user)
        try:
            return _openai_chat(
                base_url=self.base_url,
                api_key=self.api_key,
                model=self.model,
                system=system,
                user=user,
                temperature=temperature,
                max_tokens=max_tokens,
            )
        except (urllib.error.URLError, urllib.error.HTTPError, KeyError, json.JSONDecodeError, TimeoutError, OSError) as exc:
            return HeuristicChat(self.endpoint).complete(system, user) + f"\n\n_API error ({self.name}): {exc}_\n"

    def write(self, system: str, user_payload: dict[str, Any]) -> str:
        return self.complete(system, json.dumps(user_payload, default=str))


# Back-compat alias
class OpenAICompatibleNarrative(OpenAICompatibleBackend):
    def __init__(self, endpoint: EndpointConfig | None = None) -> None:
        if endpoint is None:
            endpoint = resolve_endpoint("openai_compatible")
        super().__init__(endpoint)


class AnthropicBackend:
    name = "anthropic"

    def __init__(self, endpoint: EndpointConfig | None = None) -> None:
        self.endpoint = endpoint or resolve_endpoint("anthropic")
        self.api_key = self.endpoint.api_key or ""
        self.model = self.endpoint.model

    def complete(self, system: str, user: str, *, temperature: float = 0.2, max_tokens: int = 4096) -> str:
        del temperature  # Anthropic Messages API uses defaults; keep signature
        if not self.api_key:
            return HeuristicChat(self.endpoint).complete(system, user)
        try:
            return _anthropic_chat(
                api_key=self.api_key,
                model=self.model,
                system=system,
                user=user,
                max_tokens=max_tokens,
            )
        except (urllib.error.URLError, urllib.error.HTTPError, KeyError, json.JSONDecodeError, TimeoutError, OSError) as exc:
            return HeuristicChat(self.endpoint).complete(system, user) + f"\n\n_Anthropic error: {exc}_\n"

    def write(self, system: str, user_payload: dict[str, Any]) -> str:
        return self.complete(system, json.dumps(user_payload, default=str))


AnthropicNarrative = AnthropicBackend


class SLMBackend:
    """Local small LM via codeevolve.models.slm."""

    name = "slm"

    def __init__(self, endpoint: EndpointConfig | None = None) -> None:
        self.endpoint = endpoint or resolve_endpoint("slm")
        if self.endpoint.model:
            os.environ.setdefault("CODEEVOLVE_HF_MODEL", self.endpoint.model)

    def complete(self, system: str, user: str, *, temperature: float = 0.2, max_tokens: int = 4096) -> str:
        del temperature
        from codeevolve.models.slm import slm_complete

        # Temporarily allow HF for SLM even if agent analyze skipped it
        prev = os.environ.get("CODEEVOLVE_SKIP_HF")
        prev_tax = os.environ.get("CODEEVOLVE_TAXONOMY_HEURISTIC")
        try:
            os.environ["CODEEVOLVE_SKIP_HF"] = "0"
            os.environ["CODEEVOLVE_TAXONOMY_HEURISTIC"] = "0"
            text = slm_complete(system, user, max_new_tokens=min(max_tokens, 2048))
        finally:
            if prev is None:
                os.environ.pop("CODEEVOLVE_SKIP_HF", None)
            else:
                os.environ["CODEEVOLVE_SKIP_HF"] = prev
            if prev_tax is None:
                os.environ.pop("CODEEVOLVE_TAXONOMY_HEURISTIC", None)
            else:
                os.environ["CODEEVOLVE_TAXONOMY_HEURISTIC"] = prev_tax
        if text:
            return text
        return HeuristicChat(self.endpoint).complete(system, user) + "\n\n_Note: SLM unavailable._\n"

    def write(self, system: str, user_payload: dict[str, Any]) -> str:
        return self.complete(system, json.dumps(user_payload, default=str))


class HFQwenBackend:
    """Local Hugging Face Qwen sized by GPU ladder."""

    name = "hf-qwen"

    def __init__(self, endpoint: EndpointConfig | None = None) -> None:
        self.endpoint = endpoint or resolve_endpoint("hf-qwen")

    def complete(self, system: str, user: str, *, temperature: float = 0.2, max_tokens: int = 4096) -> str:
        del temperature
        if os.environ.get("CODEEVOLVE_SKIP_HF", "").lower() in {"1", "true", "yes"}:
            # Still try if explicitly selected as coding backend
            pass
        model_id = self.endpoint.model or os.environ.get("CODEEVOLVE_HF_MODEL") or pick_qwen_model()
        try:
            from transformers import AutoModelForCausalLM, AutoTokenizer  # type: ignore
            import torch  # type: ignore
        except Exception:
            return (
                HeuristicChat(self.endpoint).complete(system, user)
                + f"\n\n_Note: transformers/torch unavailable; wanted `{model_id}`._\n"
            )

        prompt = (
            f"<|im_start|>system\n{system}<|im_end|>\n"
            f"<|im_start|>user\n{user[:12000]}<|im_end|>\n"
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
            out = model.generate(**inputs, max_new_tokens=min(max_tokens, 2048), do_sample=False)
            text = tok.decode(out[0], skip_special_tokens=True)
            if "assistant" in text:
                text = text.split("assistant")[-1].strip()
            return text or HeuristicChat(self.endpoint).complete(system, user)
        except Exception as exc:
            return HeuristicChat(self.endpoint).complete(system, user) + f"\n\n_HF Qwen error: {exc}_\n"

    def write(self, system: str, user_payload: dict[str, Any]) -> str:
        return self.complete(system, json.dumps(user_payload, default=str))


HFQwenNarrative = HFQwenBackend


def backend_from_endpoint(endpoint: EndpointConfig) -> OpenAICompatibleBackend | AnthropicBackend | SLMBackend | HFQwenBackend | HeuristicChat:
    if endpoint.kind == "anthropic":
        return AnthropicBackend(endpoint)
    if endpoint.kind == "local_slm":
        return SLMBackend(endpoint)
    if endpoint.kind == "local_hf":
        return HFQwenBackend(endpoint)
    if endpoint.kind == "openai_compatible":
        return OpenAICompatibleBackend(endpoint)
    return HeuristicChat(endpoint)


def get_chat_backend(
    provider: str | bool | None = "auto",
    *,
    model: str | None = None,
    base_url: str | None = None,
    api_key: str | None = None,
    repo: Any = None,
) -> ChatBackend:
    """Coding-agent backend from provider/model/endpoint settings."""
    endpoint = resolve_endpoint(
        provider,
        model=model,
        base_url=base_url,
        api_key=api_key,
        repo=repo,
    )
    return backend_from_endpoint(endpoint)  # type: ignore[return-value]


def get_narrative_backend(llm: str | bool | None = None) -> NarrativeBackend:
    """Back-compat narrative selector (also accepts grok/kimi/slm/…)."""
    if llm is None or llm is False or llm == "" or llm == "heuristic":
        name = resolve_backend_name(llm)
        if name == "heuristic":
            return HeuristicNarrative()
        endpoint = resolve_endpoint(name)
        return backend_from_endpoint(endpoint)  # type: ignore[return-value]
    endpoint = resolve_endpoint(llm if llm is not True else "auto")
    return backend_from_endpoint(endpoint)  # type: ignore[return-value]


def chat_complete(
    system: str,
    user: str,
    *,
    provider: str | bool | None = "auto",
    model: str | None = None,
    base_url: str | None = None,
    api_key: str | None = None,
    repo: Any = None,
    temperature: float = 0.2,
    max_tokens: int = 4096,
) -> tuple[str, EndpointConfig]:
    """One-shot completion; returns (text, endpoint used)."""
    endpoint = resolve_endpoint(
        provider, model=model, base_url=base_url, api_key=api_key, repo=repo
    )
    backend = backend_from_endpoint(endpoint)
    text = backend.complete(system, user, temperature=temperature, max_tokens=max_tokens)
    return text, endpoint
