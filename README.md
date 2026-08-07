# CodeEvolve

**Evaluate how a codebase evolves** by reading git history — then quantify revert rate, semantic trends, hierarchy taxonomy (embeddings), code stability, dependency churn, technical debt, phylogeny / ecological stage, and a top-down planner report (heuristic SLM or cloud LLM).

```
git history → metrics + semantics + phylogeny + debt
           → top-down plan
           → global trend report (heuristic | OpenAI-compatible)
```

## Install

```powershell
git clone https://github.com/ehallford11714/codeevolve.git
cd codeevolve
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
```

## Quick start

```powershell
python -m codeevolve --repo path\to\repo analyze
python -m codeevolve --repo path\to\repo analyze --out report.json --md-out trend.md
python -m codeevolve --repo path\to\repo metrics
python -m codeevolve --repo path\to\repo debt
python -m codeevolve --repo path\to\repo phylogeny
python -m codeevolve --repo path\to\repo semantics
```

```python
from codeevolve import CodeEvolve

report = CodeEvolve("path/to/repo").analyze()
print(report.metrics.revert_rate, report.phylogeny.current_stage)
print(report.trend.markdown)
```

Cloud / SLM narrative (optional):

```powershell
$env:CODEEVOLVE_LLM_API_KEY = "..."
python -m codeevolve --repo . analyze --llm
```

## What it tracks (MVP)

| Signal | Meaning |
|--------|---------|
| **Revert rate** | Share of commits that are reverts |
| **Semantic trends** | Theme mix (feature/fix/refactor/…) via embeddings |
| **Hierarchy taxonomy** | Path-layer tree (core/tests/docs/…) + embedding clusters |
| **Code stability** | Inverse of churn, reverts, hotspot concentration |
| **Dependency rate** | Share of commits touching lockfiles / manifests |
| **Momentum** | Recent vs older churn |
| **Improvement trend** | Recent reverts/churn cooling vs past |
| **Tech debt** | Deprecation / FIXME scans + historical architecture smells |
| **Phylogeny** | Commit parent graph, generations, branch factor |
| **Ecological stage** | pioneer → growth → disturbance → consolidation → maturity → decline |

## Docs

- [Tutorial](docs/TUTORIAL.md) — install, CLI walkthrough, reading signals, LLM report
- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)
- [docs/METRICS.md](docs/METRICS.md)

## License

MIT
