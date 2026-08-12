"""Hardware assessment → Hugging Face Qwen ladder (iQueue-style)."""

from __future__ import annotations

import os
import platform
from dataclasses import dataclass, field
from typing import Any

QWEN_LADDER: list[tuple[str, float, float]] = [
    ("Qwen/Qwen2.5-0.5B-Instruct", 4.0, 2.0),
    ("Qwen/Qwen2.5-1.5B-Instruct", 8.0, 4.0),
    ("Qwen/Qwen2.5-3B-Instruct", 12.0, 8.0),
    ("Qwen/Qwen2.5-7B-Instruct", 24.0, 16.0),
]


@dataclass
class HardwareProfile:
    ram_gb: float
    vram_gb: float | None
    cuda_available: bool
    cpu_count: int
    platform: str
    recommended_model: str
    notes: list[str] = field(default_factory=list)
    disk_free_gb: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "ram_gb": self.ram_gb,
            "vram_gb": self.vram_gb,
            "cuda_available": self.cuda_available,
            "cpu_count": self.cpu_count,
            "platform": self.platform,
            "recommended_model": self.recommended_model,
            "notes": list(self.notes),
            "disk_free_gb": self.disk_free_gb,
        }


def _ram_gb() -> float:
    env = os.environ.get("CODEEVOLVE_RAM_GB") or os.environ.get("IQUEUE_RAM_GB")
    if env:
        try:
            return float(env)
        except ValueError:
            pass
    try:
        import psutil

        return float(psutil.virtual_memory().total) / (1024**3)
    except Exception:
        return 8.0


def _vram() -> tuple[bool, float | None]:
    try:
        import torch

        if torch.cuda.is_available():
            props = torch.cuda.get_device_properties(0)
            return True, float(props.total_memory) / (1024**3)
    except Exception:
        pass
    return False, None


def _disk_free() -> float | None:
    try:
        import shutil

        target = os.environ.get("CODEEVOLVE_HF_CACHE") or os.path.expanduser("~")
        return float(shutil.disk_usage(target).free) / (1024**3)
    except Exception:
        return None


def assess_hardware(prefer_small: bool = False) -> HardwareProfile:
    ram = _ram_gb()
    cuda, vram = _vram()
    disk = _disk_free()
    notes: list[str] = []
    recommended = QWEN_LADDER[0][0]

    if cuda and vram is not None:
        for mid, need_ram, need_vram in QWEN_LADDER:
            if ram >= need_ram and vram >= need_vram:
                recommended = mid
        notes.append(f"CUDA VRAM ≈ {vram:.1f} GB")
    else:
        for mid, need_ram in (
            ("Qwen/Qwen2.5-0.5B-Instruct", 4.0),
            ("Qwen/Qwen2.5-1.5B-Instruct", 10.0),
        ):
            if ram >= need_ram:
                recommended = mid
        notes.append("No CUDA — capped recommendation at ≤1.5B for CPU")

    if prefer_small:
        recommended = QWEN_LADDER[0][0]
        notes.append("prefer_small=True → forced 0.5B")

    if disk is not None:
        notes.append(f"Disk free ≈ {disk:.1f} GB")
        if disk < 5.0:
            notes.append("Low disk (<5GB) — prefer cloud / skip HF downloads")

    override = os.environ.get("CODEEVOLVE_HF_MODEL") or os.environ.get("IQUEUE_HF_MODEL")
    if override:
        recommended = override
        notes.append(f"Overridden by HF model env={override}")

    return HardwareProfile(
        ram_gb=round(ram, 2),
        vram_gb=round(vram, 2) if vram is not None else None,
        cuda_available=cuda,
        cpu_count=os.cpu_count() or 1,
        platform=platform.platform(),
        recommended_model=recommended,
        notes=notes,
        disk_free_gb=round(disk, 2) if disk is not None else None,
    )


def pick_qwen_model(profile: HardwareProfile | None = None) -> str:
    return (profile or assess_hardware()).recommended_model


def recommend_execution(profile: HardwareProfile | None = None) -> dict[str, Any]:
    """Recommend local HF Qwen / SLM vs cloud vs heuristic for report generation."""
    hw = profile or assess_hardware()
    has_openai = bool(os.environ.get("CODEEVOLVE_LLM_API_KEY") or os.environ.get("OPENAI_API_KEY"))
    has_anthropic = bool(os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("CODEEVOLVE_ANTHROPIC_API_KEY"))
    has_grok = bool(os.environ.get("XAI_API_KEY") or os.environ.get("GROK_API_KEY") or os.environ.get("CODEEVOLVE_GROK_API_KEY"))
    has_kimi = bool(os.environ.get("MOONSHOT_API_KEY") or os.environ.get("KIMI_API_KEY") or os.environ.get("CODEEVOLVE_KIMI_API_KEY"))
    has_cloud = has_openai or has_anthropic or has_grok or has_kimi
    skip_hf = os.environ.get("CODEEVOLVE_SKIP_HF", "").lower() in {"1", "true", "yes"}
    local_ok = (not skip_hf) and hw.ram_gb >= 4.0 and (hw.disk_free_gb is None or hw.disk_free_gb >= 2.0)
    strong_gpu = bool(hw.cuda_available and (hw.vram_gb or 0) >= 8.0)

    if local_ok and strong_gpu:
        return {
            "run_local": True,
            "offload_cloud": False,
            "backend": "hf-qwen",
            "local_model": hw.recommended_model,
            "reason": "GPU VRAM sufficient for larger local Qwen",
        }
    if local_ok and (hw.cuda_available or hw.ram_gb >= 8.0):
        return {
            "run_local": True,
            "offload_cloud": False,
            "backend": "slm" if (hw.vram_gb or 0) < 8.0 else "hf-qwen",
            "local_model": hw.recommended_model,
            "reason": "Hardware sufficient for local SLM/Qwen",
        }
    if has_cloud:
        if has_openai:
            backend = "openai"
        elif has_anthropic:
            backend = "anthropic"
        elif has_grok:
            backend = "grok"
        else:
            backend = "kimi"
        return {
            "run_local": False,
            "offload_cloud": True,
            "backend": backend,
            "local_model": hw.recommended_model,
            "reason": "Local HF constrained — using cloud API key",
        }
    return {
        "run_local": False,
        "offload_cloud": False,
        "backend": "heuristic",
        "local_model": hw.recommended_model,
        "reason": "No GPU headroom and no cloud key — heuristic report",
    }
