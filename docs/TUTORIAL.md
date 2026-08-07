# Tutorial: evolve, report, refactor

CodeEvolve turns **git history** (local or GitHub) into taxonomy, phylogeny, debt, failure points, a **drafted repo report**, and an **evidence-linked refactor plan**.

## 0. Install

```powershell
git clone https://github.com/ehallford11714/codeevolve.git
cd codeevolve
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
python -m codeevolve --version
```

## 1. Mental model

```
ingest → taxonomy/clades → genetics + ecology
       → metrics + debt + weaknesses
       → repo report + refactor plan
       → optional HF Qwen / cloud narrative
```

## 2. Analyze a local repo

```powershell
python -m codeevolve --repo . analyze `
  --out report.json `
  --report-out repo_report.md `
  --refactor-out refactor_plan.md
```

Open `repo_report.md` for the brief; `refactor_plan.md` for phased steps (`stabilize` → `contain` → `pay_down` → `evolve`). Every refactor step cites `W*` failure-point IDs.

## 3. Analyze a GitHub repository

```powershell
python -m codeevolve --repo https://github.com/pallets/flask analyze --max-commits 200
# shorthand:
python -m codeevolve --repo pallets/flask taxonomy
python -m codeevolve --repo pallets/flask risk
```

Clones are cached under `~/.codeevolve/repos/`.

## 4. Slice commands

| Command | Output |
|---------|--------|
| `metrics` | Revert, stability, deps, momentum |
| `taxonomy` | Layers, languages, clades, allocations |
| `phylogeny` / ecology via analyze | Commit DAG + stages |
| `debt` | Deprecations + arch mistakes |
| `risk` | Ranked failure points |
| `report` | Drafted markdown repo report |
| `refactor` | Phased refactor plan |
| `hardware` | RAM/VRAM + recommended Qwen / cloud |

## 5. Reading signals

- **Clades** — co-changing file groups; deltas are allocated to `clade_id`.
- **Fitness** — low fitness lineages often appear as failure points.
- **Lehman proxies** — continuing change, complexity, growth, quality decline, familiarity, feedback volatility.
- **Failure points** — hotspot blast radius, revert surfaces, bus factor, test gap, dependency shock.
- **Refactor waves** — stop bleeding first (`stabilize`), then boundaries (`contain`), debt (`pay_down`), structure (`evolve`).

## 6. Hardware + LLM

```powershell
python -m codeevolve hardware
python -m codeevolve --repo . analyze --llm auto --report-out repo_report.md
```

| Backend | When |
|---------|------|
| `heuristic` | Default; no keys/GPU required |
| `hf-qwen` | Local transformers + enough RAM/VRAM (`pip install -e ".[hf]"`) |
| `openai` / OpenAI-compatible | `CODEEVOLVE_LLM_API_KEY` or `OPENAI_API_KEY` |
| `anthropic` | `ANTHROPIC_API_KEY` |

Set `CODEEVOLVE_SKIP_HF=1` to skip local model downloads.

## 7. Python API

```python
from codeevolve import CodeEvolve

r = CodeEvolve("owner/repo").analyze(max_commits=300, use_llm="auto")
print(r.taxonomy.clades[0].label)
print(r.risk.failure_points[0].to_dict())
print(r.refactor_plan.steps[0].evidence_refs)
Path("repo_report.md").write_text(r.repo_report.markdown, encoding="utf-8")
```

## 8. Symbols & GitHub selection pressure (Phase E)

```powershell
python -m codeevolve --repo . symbols
python -m codeevolve --repo pallets/flask selection
# authenticated (recommended):
$env:GITHUB_TOKEN = "ghp_..."
python -m codeevolve --repo pallets/flask analyze --out report.json
```

Symbols are extracted with language-aware regex (Python/JS/TS/Go/Rust). Selection pressure scores bug labels, reopen-like language, open backlog, and PR merge rate — and can create a `selection_pressure` failure point that feeds the refactor **stabilize** wave.

See also [CLOUD.md](CLOUD.md) for HF Qwen / cloud routing.

## Related

- [ARCHITECTURE.md](ARCHITECTURE.md)
- [METRICS.md](METRICS.md)
- [CLOUD.md](CLOUD.md)
