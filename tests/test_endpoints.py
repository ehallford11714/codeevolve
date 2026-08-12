"""Provider / endpoint resolution for the coding agent."""

from __future__ import annotations

import json
from pathlib import Path

from codeevolve.models.backends import get_chat_backend
from codeevolve.models.endpoints import (
    list_providers,
    normalize_provider,
    recommend_agent_endpoint,
    resolve_endpoint,
)
from codeevolve.models.router import resolve_backend_name


def test_provider_aliases() -> None:
    assert normalize_provider("xai") == "grok"
    assert normalize_provider("moonshot") == "kimi"
    assert normalize_provider("kimi-k3") == "kimik3"
    assert normalize_provider("claude") == "anthropic"
    assert normalize_provider("qwen") == "hf-qwen"


def test_list_providers_includes_clouds() -> None:
    names = {p["name"] for p in list_providers()}
    assert {"slm", "hf-qwen", "openai", "anthropic", "grok", "kimi", "kimik3", "openrouter", "custom"} <= names


def test_resolve_openai_and_grok(monkeypatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.delenv("CODEEVOLVE_SKIP_HF", raising=False)
    ep = resolve_endpoint("openai", model="gpt-4o")
    assert ep.provider == "openai"
    assert ep.model == "gpt-4o"
    assert ep.configured
    assert ep.base_url and "openai.com" in ep.base_url

    monkeypatch.setenv("XAI_API_KEY", "xai-test")
    grok = resolve_endpoint("grok")
    assert grok.provider == "grok"
    assert grok.configured
    assert grok.base_url and "x.ai" in grok.base_url


def test_resolve_auto_prefers_cloud_when_hf_skipped(monkeypatch) -> None:
    monkeypatch.setenv("CODEEVOLVE_SKIP_HF", "1")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "ant-test")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("CODEEVOLVE_LLM_API_KEY", raising=False)
    monkeypatch.delenv("XAI_API_KEY", raising=False)
    monkeypatch.delenv("MOONSHOT_API_KEY", raising=False)
    ep = resolve_endpoint("auto")
    assert ep.provider == "anthropic"
    assert ep.configured


def test_resolve_auto_heuristic_without_keys(monkeypatch) -> None:
    monkeypatch.setenv("CODEEVOLVE_SKIP_HF", "1")
    for k in (
        "OPENAI_API_KEY",
        "CODEEVOLVE_LLM_API_KEY",
        "ANTHROPIC_API_KEY",
        "XAI_API_KEY",
        "GROK_API_KEY",
        "MOONSHOT_API_KEY",
        "KIMI_API_KEY",
        "OPENROUTER_API_KEY",
    ):
        monkeypatch.delenv(k, raising=False)
    ep = resolve_endpoint("auto")
    assert ep.provider == "heuristic"


def test_models_json_config(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("CODEEVOLVE_SKIP_HF", "1")
    monkeypatch.setenv("MOONSHOT_API_KEY", "ms-test")
    cfg_dir = tmp_path / ".codeevolve"
    cfg_dir.mkdir()
    (cfg_dir / "models.json").write_text(
        json.dumps(
            {
                "provider": "kimik3",
                "endpoints": {"kimik3": {"model": "kimi-custom"}},
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    ep = resolve_endpoint("auto", repo=tmp_path)
    assert ep.provider == "kimik3"
    assert ep.model == "kimi-custom"


def test_custom_base_url(monkeypatch) -> None:
    monkeypatch.setenv("CODEEVOLVE_LLM_API_KEY", "k")
    ep = resolve_endpoint(
        "custom",
        model="local-model",
        base_url="http://127.0.0.1:8080/v1",
        api_key="k",
    )
    assert ep.kind == "openai_compatible"
    assert ep.base_url == "http://127.0.0.1:8080/v1"
    backend = get_chat_backend("custom", model="local-model", base_url=ep.base_url, api_key="k")
    assert backend.name == "custom"


def test_router_accepts_grok() -> None:
    assert resolve_backend_name("grok") == "grok"
    assert resolve_backend_name("kimik3") == "kimik3"


def test_recommend_agent_endpoint_shape(monkeypatch) -> None:
    monkeypatch.setenv("CODEEVOLVE_SKIP_HF", "1")
    data = recommend_agent_endpoint()
    assert "endpoint" in data and "providers" in data
