from pathlib import Path

from codeevolve import CodeEvolve
from codeevolve.models.guide import guide_taxonomy
from codeevolve.models.tiers import resolve_tier, tier_spec
def test_default_tier_is_slm() -> None:
    assert resolve_tier(None) == "slm"
    assert "0.5B" in tier_spec("slm").hf_model


def test_taxonomy_slm_guide_heuristic(sample_repo: Path, monkeypatch) -> None:
    monkeypatch.setenv("CODEEVOLVE_TAXONOMY_HEURISTIC", "1")
    monkeypatch.setenv("CODEEVOLVE_SKIP_HF", "1")
    r = CodeEvolve(sample_repo, model_tier="slm").analyze(
        max_commits=50,
        use_llm=False,
        include_hardware=False,
        include_selection=False,
        guide_taxonomy=True,
    )
    assert r.taxonomy.guidance.get("guided") is True
    assert r.model_tier == "slm"
    assert any(c.role for c in r.taxonomy.clades) or r.taxonomy.guidance.get("model")


def test_guide_taxonomy_json_shape() -> None:
    g = guide_taxonomy(
        [{"id": "clade_00", "label": "src", "layer": "core", "files": ["a.py"], "touch_count": 2, "churn": 10}],
        tier="slm",
        force_heuristic=True,
    )
    assert g["clades"][0]["id"] == "clade_00"
    assert g["tier"] == "slm"


def test_fatigue_and_stability(sample_repo: Path, monkeypatch) -> None:
    monkeypatch.setenv("CODEEVOLVE_TAXONOMY_HEURISTIC", "1")
    monkeypatch.setenv("CODEEVOLVE_SKIP_HF", "1")
    r = CodeEvolve(sample_repo).analyze(
        max_commits=50,
        use_llm=False,
        include_hardware=False,
        include_selection=False,
    )
    assert r.fatigue is not None
    assert 0 <= r.fatigue.fatigue_score <= 1
    assert r.cognitive_load is not None
    assert r.drift is not None
    assert r.stability is not None
    assert "composite" in r.stability.to_dict()
    assert "Stability decomposition" in (r.repo_report.markdown if r.repo_report else "")


def test_cli_tiers() -> None:
    from codeevolve.cli import main

    assert main(["tiers"]) == 0
