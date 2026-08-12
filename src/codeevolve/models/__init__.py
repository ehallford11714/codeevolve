from codeevolve.models.backends import chat_complete, get_chat_backend, get_narrative_backend
from codeevolve.models.endpoints import (
    EndpointConfig,
    list_providers,
    load_models_config,
    recommend_agent_endpoint,
    resolve_endpoint,
)
from codeevolve.models.hardware import HardwareProfile, assess_hardware, pick_qwen_model, recommend_execution
from codeevolve.models.hf_qwen import ensure_hf_qwen
from codeevolve.models.router import resolve_backend_name
from codeevolve.models.slm import ensure_default_slm, slm_complete, slm_enabled
from codeevolve.models.taxonomy_embed import (
    DEFAULT_TAXONOMY_EMBED_MODEL,
    ensure_taxonomy_embedder,
    embed_taxonomy_texts,
)
from codeevolve.models.tiers import TIERS, apply_tier_env, resolve_tier, tier_spec

__all__ = [
    "HardwareProfile",
    "assess_hardware",
    "pick_qwen_model",
    "recommend_execution",
    "ensure_hf_qwen",
    "ensure_default_slm",
    "slm_complete",
    "slm_enabled",
    "DEFAULT_TAXONOMY_EMBED_MODEL",
    "ensure_taxonomy_embedder",
    "embed_taxonomy_texts",
    "resolve_backend_name",
    "TIERS",
    "resolve_tier",
    "tier_spec",
    "apply_tier_env",
    "EndpointConfig",
    "list_providers",
    "load_models_config",
    "recommend_agent_endpoint",
    "resolve_endpoint",
    "get_chat_backend",
    "get_narrative_backend",
    "chat_complete",
]
