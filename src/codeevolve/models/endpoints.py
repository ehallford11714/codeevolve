"""Configurable model endpoints for the coding agent and narrative backends.

Supports:
- local SLM / GPU-sized HF Qwen (hardware ladder)
- OpenAI, Anthropic
- OpenAI-compatible clouds: Grok (xAI), Kimi/Moonshot, OpenRouter, Azure, custom base URLs

Users can specify provider + model + base_url + api_key via CLI, MCP, env, or
``.codeevolve/models.json``.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal


ProviderKind = Literal[
    "auto",
    "heuristic",
    "slm",
    "hf-qwen",
    "openai",
    "anthropic",
    "grok",
    "kimi",
    "kimik3",
    "openrouter",
    "custom",
    "openai_compatible",
]


@dataclass
class ProviderPreset:
    name: str
    kind: str  # openai_compatible | anthropic | local_slm | local_hf | heuristic
    label: str
    default_base_url: str | None
    default_model: str
    env_keys: list[str] = field(default_factory=list)
    env_base_url: str | None = None
    env_model: str | None = None
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "kind": self.kind,
            "label": self.label,
            "default_base_url": self.default_base_url,
            "default_model": self.default_model,
            "env_keys": list(self.env_keys),
            "env_base_url": self.env_base_url,
            "env_model": self.env_model,
            "notes": self.notes,
        }


PROVIDERS: dict[str, ProviderPreset] = {
    "auto": ProviderPreset(
        name="auto",
        kind="auto",
        label="Auto (GPU SLM/HF ladder → configured cloud → heuristic)",
        default_base_url=None,
        default_model="",
        notes="Picks local model from VRAM/RAM when possible, else first configured API",
    ),
    "heuristic": ProviderPreset(
        name="heuristic",
        kind="heuristic",
        label="Heuristic (no LLM)",
        default_base_url=None,
        default_model="heuristic",
    ),
    "slm": ProviderPreset(
        name="slm",
        kind="local_slm",
        label="Local SLM (default Qwen2.5-0.5B)",
        default_base_url=None,
        default_model="Qwen/Qwen2.5-0.5B-Instruct",
        env_model="CODEEVOLVE_HF_MODEL",
        notes="Uses codeevolve.models.slm; respects model tier",
    ),
    "hf-qwen": ProviderPreset(
        name="hf-qwen",
        kind="local_hf",
        label="Local HF Qwen sized by GPU/RAM",
        default_base_url=None,
        default_model="Qwen/Qwen2.5-1.5B-Instruct",
        env_model="CODEEVOLVE_HF_MODEL",
        notes="Hardware ladder up to 7B+ when VRAM allows",
    ),
    "openai": ProviderPreset(
        name="openai",
        kind="openai_compatible",
        label="OpenAI",
        default_base_url="https://api.openai.com/v1",
        default_model="gpt-4o-mini",
        env_keys=["OPENAI_API_KEY", "CODEEVOLVE_LLM_API_KEY"],
        env_base_url="CODEEVOLVE_OPENAI_BASE_URL",
        env_model="CODEEVOLVE_OPENAI_MODEL",
    ),
    "anthropic": ProviderPreset(
        name="anthropic",
        kind="anthropic",
        label="Anthropic Claude",
        default_base_url="https://api.anthropic.com/v1",
        default_model="claude-sonnet-4-20250514",
        env_keys=["ANTHROPIC_API_KEY", "CODEEVOLVE_ANTHROPIC_API_KEY"],
        env_model="CODEEVOLVE_ANTHROPIC_MODEL",
    ),
    "grok": ProviderPreset(
        name="grok",
        kind="openai_compatible",
        label="xAI Grok",
        default_base_url="https://api.x.ai/v1",
        default_model="grok-3-mini",
        env_keys=["XAI_API_KEY", "GROK_API_KEY", "CODEEVOLVE_GROK_API_KEY", "CODEEVOLVE_LLM_API_KEY"],
        env_base_url="CODEEVOLVE_GROK_BASE_URL",
        env_model="CODEEVOLVE_GROK_MODEL",
        notes="OpenAI-compatible chat completions at api.x.ai",
    ),
    "kimi": ProviderPreset(
        name="kimi",
        kind="openai_compatible",
        label="Moonshot Kimi",
        default_base_url="https://api.moonshot.ai/v1",
        default_model="moonshot-v1-128k",
        env_keys=["MOONSHOT_API_KEY", "KIMI_API_KEY", "CODEEVOLVE_KIMI_API_KEY", "CODEEVOLVE_LLM_API_KEY"],
        env_base_url="CODEEVOLVE_KIMI_BASE_URL",
        env_model="CODEEVOLVE_KIMI_MODEL",
    ),
    "kimik3": ProviderPreset(
        name="kimik3",
        kind="openai_compatible",
        label="Kimi K3 (Moonshot OpenAI-compatible)",
        default_base_url="https://api.moonshot.ai/v1",
        default_model="kimi-k2-0905-preview",
        env_keys=["MOONSHOT_API_KEY", "KIMI_API_KEY", "CODEEVOLVE_KIMI_API_KEY", "CODEEVOLVE_LLM_API_KEY"],
        env_base_url="CODEEVOLVE_KIMI_BASE_URL",
        env_model="CODEEVOLVE_KIMIK3_MODEL",
        notes="Alias for Kimi K-series coding models; override model via CODEEVOLVE_KIMIK3_MODEL",
    ),
    "openrouter": ProviderPreset(
        name="openrouter",
        kind="openai_compatible",
        label="OpenRouter",
        default_base_url="https://openrouter.ai/api/v1",
        default_model="openai/gpt-4o-mini",
        env_keys=["OPENROUTER_API_KEY", "CODEEVOLVE_OPENROUTER_API_KEY", "CODEEVOLVE_LLM_API_KEY"],
        env_base_url="CODEEVOLVE_OPENROUTER_BASE_URL",
        env_model="CODEEVOLVE_OPENROUTER_MODEL",
    ),
    "custom": ProviderPreset(
        name="custom",
        kind="openai_compatible",
        label="Custom OpenAI-compatible endpoint",
        default_base_url=None,
        default_model="gpt-4o-mini",
        env_keys=["CODEEVOLVE_LLM_API_KEY", "OPENAI_API_KEY"],
        env_base_url="CODEEVOLVE_LLM_BASE_URL",
        env_model="CODEEVOLVE_LLM_MODEL",
        notes="Requires --base-url or CODEEVOLVE_LLM_BASE_URL",
    ),
    "openai_compatible": ProviderPreset(
        name="openai_compatible",
        kind="openai_compatible",
        label="Generic OpenAI-compatible (CODEEVOLVE_LLM_*)",
        default_base_url="https://api.openai.com/v1",
        default_model="gpt-4o-mini",
        env_keys=["CODEEVOLVE_LLM_API_KEY", "OPENAI_API_KEY"],
        env_base_url="CODEEVOLVE_LLM_BASE_URL",
        env_model="CODEEVOLVE_LLM_MODEL",
    ),
}


@dataclass
class EndpointConfig:
    """Resolved endpoint the agent / narrative layer will call."""

    provider: str
    kind: str
    model: str
    base_url: str | None = None
    api_key: str | None = None
    source: str = "default"  # cli | env | config | auto | default
    extras: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "kind": self.kind,
            "model": self.model,
            "base_url": self.base_url,
            "api_key_set": bool(self.api_key),
            "source": self.source,
            "extras": dict(self.extras),
        }

    @property
    def configured(self) -> bool:
        if self.kind in {"heuristic"}:
            return True
        if self.kind in {"local_slm", "local_hf"}:
            return True
        if self.kind == "anthropic":
            return bool(self.api_key)
        if self.kind == "openai_compatible":
            return bool(self.api_key and self.base_url)
        return False


def _first_env(names: list[str]) -> str | None:
    for n in names:
        v = os.environ.get(n)
        if v:
            return v
    return None


def load_models_config(repo: Path | str | None = None) -> dict[str, Any]:
    """Load optional ``.codeevolve/models.json`` from repo or cwd."""
    candidates: list[Path] = []
    if repo:
        candidates.append(Path(repo) / ".codeevolve" / "models.json")
    candidates.append(Path.cwd() / ".codeevolve" / "models.json")
    home = Path.home() / ".codeevolve" / "models.json"
    candidates.append(home)
    for path in candidates:
        if path.is_file():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    data["_config_path"] = str(path)
                    return data
            except (OSError, json.JSONDecodeError):
                continue
    return {}


def list_providers() -> list[dict[str, Any]]:
    return [p.to_dict() for p in PROVIDERS.values()]


def normalize_provider(name: str | None) -> str:
    if not name:
        return "auto"
    raw = str(name).lower().strip()
    aliases = {
        "gpt": "openai",
        "chatgpt": "openai",
        "claude": "anthropic",
        "xai": "grok",
        "x.ai": "grok",
        "moonshot": "kimi",
        "kimi-k3": "kimik3",
        "kimi_k3": "kimik3",
        "k3": "kimik3",
        "qwen": "hf-qwen",
        "huggingface": "hf-qwen",
        "hf": "hf-qwen",
        "local": "slm",
        "small": "slm",
        "cloud": "openai_compatible",
        "none": "heuristic",
        "off": "heuristic",
    }
    raw = aliases.get(raw, raw)
    if raw in PROVIDERS:
        return raw
    return "custom" if raw not in {"auto"} else "auto"


def resolve_endpoint(
    provider: str | bool | None = "auto",
    *,
    model: str | None = None,
    base_url: str | None = None,
    api_key: str | None = None,
    repo: Path | str | None = None,
    prefer_local: bool | None = None,
) -> EndpointConfig:
    """Resolve a concrete endpoint from CLI/MCP args, config file, and env."""
    cfg = load_models_config(repo)

    # bool True → auto; False/None empty → check CODEEVOLVE_AGENT_PROVIDER / LLM backend
    if provider is True:
        prov_name = "auto"
    elif provider is False or provider is None or provider == "":
        prov_name = (
            os.environ.get("CODEEVOLVE_AGENT_PROVIDER")
            or cfg.get("provider")
            or os.environ.get("CODEEVOLVE_LLM_BACKEND")
            or "auto"
        )
    else:
        prov_name = str(provider)

    prov_name = normalize_provider(prov_name)

    # Merge config-file endpoint overrides
    file_ep = cfg.get("endpoints") if isinstance(cfg.get("endpoints"), dict) else {}
    file_for_prov = file_ep.get(prov_name) if isinstance(file_ep, dict) else None
    if not isinstance(file_for_prov, dict):
        file_for_prov = {}

    if prov_name == "auto":
        return _resolve_auto(
            model=model or cfg.get("model") or file_for_prov.get("model"),
            base_url=base_url or cfg.get("base_url"),
            api_key=api_key or cfg.get("api_key"),
            repo=repo,
            prefer_local=prefer_local,
            cfg=cfg,
        )

    preset = PROVIDERS.get(prov_name) or PROVIDERS["custom"]
    resolved_model = (
        model
        or file_for_prov.get("model")
        or cfg.get("model")
        or (os.environ.get(preset.env_model) if preset.env_model else None)
        or os.environ.get("CODEEVOLVE_LLM_MODEL")
        or preset.default_model
    )
    resolved_base = (
        base_url
        or file_for_prov.get("base_url")
        or cfg.get("base_url")
        or (os.environ.get(preset.env_base_url) if preset.env_base_url else None)
        or os.environ.get("CODEEVOLVE_LLM_BASE_URL")
        or preset.default_base_url
    )
    resolved_key = (
        api_key
        or file_for_prov.get("api_key")
        or cfg.get("api_key")
        or _first_env(preset.env_keys)
    )

    source = "cli" if (model or base_url or api_key or (provider not in (None, True, "auto"))) else "env"
    if cfg.get("_config_path") and not (model or base_url or api_key):
        source = "config"

    if preset.kind == "local_hf":
        from codeevolve.models.hardware import pick_qwen_model

        if not model and not file_for_prov.get("model"):
            resolved_model = os.environ.get("CODEEVOLVE_HF_MODEL") or pick_qwen_model()

    if preset.kind == "local_slm":
        from codeevolve.models.tiers import tier_spec

        if not model:
            resolved_model = (
                os.environ.get("CODEEVOLVE_HF_MODEL")
                or tier_spec(os.environ.get("CODEEVOLVE_MODEL_TIER")).hf_model
            )

    return EndpointConfig(
        provider=preset.name,
        kind=preset.kind,
        model=str(resolved_model),
        base_url=str(resolved_base).rstrip("/") if resolved_base else None,
        api_key=resolved_key,
        source=source,
        extras={"config_path": cfg.get("_config_path")},
    )


def _configured_clouds(cfg: dict[str, Any]) -> list[EndpointConfig]:
    """Return cloud endpoints that have credentials available, preference order."""
    order = list(cfg.get("provider_order") or ["openai", "anthropic", "grok", "kimik3", "kimi", "openrouter", "openai_compatible"])
    out: list[EndpointConfig] = []
    for name in order:
        if name in {"auto", "heuristic", "slm", "hf-qwen"}:
            continue
        ep = resolve_endpoint(name, repo=None)
        # avoid recursive auto; resolve_endpoint with concrete name is fine
        if ep.provider == "auto":
            continue
        if ep.configured and ep.kind in {"openai_compatible", "anthropic"}:
            out.append(ep)
    return out


def _resolve_auto(
    *,
    model: str | None,
    base_url: str | None,
    api_key: str | None,
    repo: Path | str | None,
    prefer_local: bool | None,
    cfg: dict[str, Any],
) -> EndpointConfig:
    from codeevolve.models.hardware import assess_hardware

    hw = assess_hardware()
    skip_hf = os.environ.get("CODEEVOLVE_SKIP_HF", "").lower() in {"1", "true", "yes"}
    prefer = prefer_local if prefer_local is not None else (
        os.environ.get("CODEEVOLVE_AGENT_PREFER_LOCAL", "").lower() in {"1", "true", "yes"}
        or bool(cfg.get("prefer_local"))
    )

    # Explicit custom URL+key wins
    if base_url and (api_key or _first_env(["CODEEVOLVE_LLM_API_KEY", "OPENAI_API_KEY"])):
        return EndpointConfig(
            provider="custom",
            kind="openai_compatible",
            model=model or os.environ.get("CODEEVOLVE_LLM_MODEL") or "gpt-4o-mini",
            base_url=base_url.rstrip("/"),
            api_key=api_key or _first_env(["CODEEVOLVE_LLM_API_KEY", "OPENAI_API_KEY"]),
            source="auto",
            extras={"reason": "explicit base_url", "hardware": hw.to_dict()},
        )

    local_ok = (not skip_hf) and hw.ram_gb >= 4.0 and (hw.disk_free_gb is None or hw.disk_free_gb >= 2.0)
    strong_gpu = bool(hw.cuda_available and (hw.vram_gb or 0) >= 8.0)
    modest_gpu = bool(hw.cuda_available and (hw.vram_gb or 0) >= 2.0)

    if prefer or local_ok:
        if strong_gpu or (local_ok and hw.cuda_available and (hw.vram_gb or 0) >= 4.0):
            ep = resolve_endpoint("hf-qwen", model=model, repo=repo)
            ep.source = "auto"
            ep.extras = {"reason": "GPU VRAM allows larger local Qwen", "hardware": hw.to_dict()}
            return ep
        if modest_gpu or (local_ok and hw.ram_gb >= 8.0 and not _configured_clouds(cfg)):
            ep = resolve_endpoint("slm", model=model, repo=repo)
            ep.source = "auto"
            ep.extras = {"reason": "Local SLM (modest GPU/CPU)", "hardware": hw.to_dict()}
            # If clouds exist and GPU is weak, fall through unless prefer_local
            if prefer or not _configured_clouds(cfg):
                return ep

    clouds = _configured_clouds(cfg)
    if clouds:
        # If user set default provider in config
        default_prov = cfg.get("provider")
        if default_prov and normalize_provider(str(default_prov)) not in {"auto", "heuristic"}:
            chosen = resolve_endpoint(str(default_prov), model=model, base_url=base_url, api_key=api_key, repo=repo)
            if chosen.configured:
                chosen.source = "auto"
                chosen.extras = {"reason": "config default provider", "hardware": hw.to_dict()}
                return chosen
        chosen = clouds[0]
        if model:
            chosen.model = model
        chosen.source = "auto"
        chosen.extras = {"reason": f"cloud credential for {chosen.provider}", "hardware": hw.to_dict()}
        return chosen

    if local_ok and not skip_hf:
        ep = resolve_endpoint("slm", model=model, repo=repo)
        ep.source = "auto"
        ep.extras = {"reason": "fallback local SLM", "hardware": hw.to_dict()}
        return ep

    return EndpointConfig(
        provider="heuristic",
        kind="heuristic",
        model="heuristic",
        source="auto",
        extras={"reason": "no local headroom and no API keys", "hardware": hw.to_dict()},
    )


def recommend_agent_endpoint(repo: Path | str | None = None) -> dict[str, Any]:
    ep = resolve_endpoint("auto", repo=repo)
    return {
        "endpoint": ep.to_dict(),
        "providers": list_providers(),
        "hint": (
            "Set provider via --provider/--llm, CODEEVOLVE_AGENT_PROVIDER, "
            "or .codeevolve/models.json. API keys: OPENAI_API_KEY, ANTHROPIC_API_KEY, "
            "XAI_API_KEY, MOONSHOT_API_KEY, or CODEEVOLVE_LLM_API_KEY + CODEEVOLVE_LLM_BASE_URL."
        ),
    }
