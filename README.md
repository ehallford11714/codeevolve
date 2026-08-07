# CodeEvolve

**Evaluate how a codebase evolves** from git history — taxonomy & phylogeny, Lehman/ecological signals, technical debt, ranked failure points, a **provenance ledger for deliberation**, a drafted repository report, and an evidence-linked refactor plan.

```
GitHub URL | local path
    → taxonomy + clade allocation
    → genetics (lineage, gene flow) + ecology (stages, Lehman proxies)
    → metrics + debt + weaknesses
    → provenance ledger (claim → evidence → falsifier)
    → repo report + refactor plan
    → narrative (heuristic | HF Qwen | cloud)
```

## Install

```powershell
git clone https://github.com/ehallford11714/codeevolve.git
cd codeevolve
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
# optional local Qwen:
# pip install -e ".[hf]"
```

## Quick start

```powershell
# Default: SLM-guided taxonomy (tier=slm)
python -m codeevolve --repo path\to\repo analyze --out report.json --report-out repo_report.md --refactor-out refactor_plan.md

# Swap up for sharper evolutionary studies
python -m codeevolve --model-tier large --repo path\to\repo analyze
python -m codeevolve tiers

# GitHub URL or owner/repo (cloned under ~/.codeevolve/repos)
python -m codeevolve --repo https://github.com/org/repo analyze --max-commits 300

python -m codeevolve --repo org/repo taxonomy
python -m codeevolve --repo org/repo fatigue
python -m codeevolve --repo org/repo risk
python -m codeevolve --repo org/repo report --md-out repo_report.md
python -m codeevolve --repo org/repo refactor --md-out refactor_plan.md
python -m codeevolve hardware
```

```python
from codeevolve import CodeEvolve

report = CodeEvolve("https://github.com/org/repo").analyze()
print(report.ecology.global_stage, report.debt.score)
print(report.risk.failure_points[0].title)
print(report.refactor_plan.markdown)
```

### LLM backends (optional)

```powershell
python -m codeevolve --repo . analyze --llm auto
# or: --llm hf-qwen | openai | anthropic | heuristic

$env:CODEEVOLVE_LLM_API_KEY = "..."          # OpenAI-compatible
$env:OPENAI_API_KEY = "..."
$env:ANTHROPIC_API_KEY = "..."
$env:CODEEVOLVE_HF_MODEL = "Qwen/Qwen2.5-0.5B-Instruct"
$env:CODEEVOLVE_SKIP_HF = "1"                # force no local download
```

`hardware` / `--llm auto` picks local Qwen vs cloud vs heuristic from RAM/VRAM/disk (iQueue-style ladder).

## What it tracks

| Signal | Meaning |
|--------|---------|
| **Taxonomy / clades** | Keyword type hierarchy + co-change clusters; every delta allocated to a clade |
| **Build hierarchy** | Deep nested “what was built” tree + ecological trend narratives |
| **Genetics** | File lineage, fitness, gene flow, HGT suspects |
| **Ecology** | Global + per-clade stages; Lehman law proxies |
| **Revert / stability / deps / momentum** | Core change-rate metrics |
| **Debt** | Deprecations, TODOs, historical architecture smells |
| **Weaknesses** | Ranked failure points (hotspot blast, reverts, bus factor, test gap, …) |
| **Repo report** | Drafted markdown brief of evolutionary state |
| **Refactor plan** | Stabilize → contain → pay down → evolve (evidence-linked) |
| **Provenance** | Ledger + dynamics trajectory (basins, impulses, selection, inter-report diffs) |

## Docs

- [Tutorial](docs/TUTORIAL.md) — end-to-end workflow incl. provenance & dynamics
- [Architecture](docs/ARCHITECTURE.md) — pipeline and package map
- [Provenance / deliberation](docs/PROVENANCE.md) — ledger, frames, MCP/schema
- [Dynamics](docs/DYNAMICS.md) — state trajectory rationale (FEAST-aligned)
- [Dynamics demo](docs/DEMO_DYNAMICS.md) — real-tag walkthrough (`examples/demo_dynamics.py`)
- [Ecology](docs/ECOLOGY.md) — event/changepoint stage calibration
- [Evaluation](docs/EVAL.md) — synthetic / taxonomy / ecology / dynamics / public
- [Metrics](docs/METRICS.md)
- [Hierarchy](docs/HIERARCHY.md) · [RAG](docs/RAG.md) · [Semantic](docs/SEMANTIC.md)
- [Cloud / HF Qwen](docs/CLOUD.md)

**0.16** adds blast/symbol/CST micro-provenance, deliberation **JSON Schema + MCP tools**, and `evaluate --suite dynamics`. **0.15** state trajectory / selection / diffs. See [docs/PROVENANCE.md](docs/PROVENANCE.md).

```powershell
python -m codeevolve --repo . provenance --pack --frame frame:basin
python -m codeevolve provenance --schema-out schemas
python -m codeevolve evaluate --suite dynamics
python examples/demo_dynamics.py
python -m codeevolve --repo . analyze --previous report.prev.json --out report.json
```

```powershell
# Diff + dashboard + PR comment + CI gate
python -m codeevolve --repo owner/repo analyze --out report.json --previous report.prev.json --dashboard-out dash.html
python -m codeevolve --repo . coupling
python -m codeevolve --repo . clones
python -m codeevolve --repo . dependencies
python -m codeevolve --repo . offboarding
python -m codeevolve --repo . word2vec
python -m codeevolve --repo . semantic-taxonomy
# pip install -e ".[semantic]"  # MiniLM + gensim + chromadb
python -m codeevolve hardware --ensure-embed
python -m codeevolve evaluate --suite synthetic --md-out eval.md
python -m codeevolve evaluate --suite public --md-out public.md   # clones OSS tags
python -m codeevolve comment --report report.json --out pr.md
python -m codeevolve ci --report report.json --previous report.prev.json
```

## License

MIT
