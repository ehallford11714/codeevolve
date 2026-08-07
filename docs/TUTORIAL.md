# Tutorial: measure how a codebase evolves

CodeEvolve reads **git history** and turns it into stability, debt, phylogeny, and a planner-written trend report. Use it when you want a top-down read on whether a repo is cooling, thrashing, or accumulating architectural smells.

## 0. Install

```powershell
git clone https://github.com/ehallford11714/codeevolve.git
cd codeevolve
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
python -m codeevolve --version
```

You need `git` on `PATH`. Analyze any local clone that is a real git repository.

## 1. Mental model

```
git log (+ numstat)
    → metrics     (revert, stability, deps, momentum, improvement)
    → semantics   (themes + hierarchy taxonomy via embeddings)
    → phylogeny   (parent DAG, generations, ecological stage)
    → debt        (deprecations, FIXME, historical arch mistakes)
    → top-down plan → trend report (heuristic | OpenAI-compatible LLM)
```

| Question | Signal to look at |
|----------|-------------------|
| Are we undoing work? | `revert_rate` |
| Is the tree settling? | `code_stability`, ecological `stage` |
| Are deps thrashing? | `dependency_rate` |
| Are themes shifting? | semantics `theme_distribution`, `semantic_drift` |
| What went wrong before? | debt `architectural_mistakes` |
| Are we improving? | `improvement_trend`, `momentum` |

## 2. Full analysis (CLI)

Point `--repo` at any git checkout:

```powershell
python -m codeevolve --repo path\to\your\repo analyze
python -m codeevolve --repo path\to\your\repo analyze --out report.json --md-out trend.md
python -m codeevolve --repo path\to\your\repo analyze --since 180.days --max-commits 500
```

Stdout prints a short JSON summary (metrics, stage, debt score, priorities) and, unless `--out` is set, the markdown trend narrative.

**Walkthrough:** run `analyze` on this repo (or Linguini / your app). Open `trend.md` for the planner narrative; open `report.json` for full numbers (hot files, themes, phylogeny, debt findings).

## 3. Slice commands

Use focused subcommands when you only need one lens:

```powershell
python -m codeevolve --repo path\to\repo metrics
python -m codeevolve --repo path\to\repo semantics
python -m codeevolve --repo path\to\repo phylogeny
python -m codeevolve --repo path\to\repo debt
```

| Command | What you get |
|---------|----------------|
| `metrics` | Revert rate, stability, dependency rate, momentum, improvement, hot files |
| `semantics` | Theme mix (feature/fix/refactor/…) + path hierarchy clusters |
| `phylogeny` | Generations, branch factor, ecological stage |
| `debt` | Deprecation / TODO hits + historical architecture mistakes |

## 4. Python API

```python
from codeevolve import CodeEvolve

report = CodeEvolve("path/to/repo").analyze(max_commits=400)

print(report.metrics.revert_rate)
print(report.metrics.code_stability)
print(report.metrics.dependency_rate)
print(report.metrics.momentum, report.metrics.improvement_trend)
print(report.phylogeny.current_stage)
print(report.debt.score)
print(report.semantics.theme_distribution)
print(report.trend.markdown)  # planner narrative
```

Or run the bundled example:

```powershell
python examples/analyze_repo.py path\to\repo
```

## 5. Reading the five core signals

### Revert rate
Share of commits that look like reverts (`Revert "…"`, `git revert`, etc.). High values mean churn is undoing prior work — pair with hot files to see which surfaces keep bouncing.

### Semantic trends
Commit subjects/bodies are embedded (hash-trick vectors by default) and clustered into themes. Rising `semantic_drift` means early vs late history talk about different work — useful for “did the product pivot?” questions.

### Hierarchy taxonomy
Paths are layered (e.g. core / tests / docs / config) and clustered by embedding similarity. Use this to see whether change concentrates in a catch-all `utils` sink or stays in domain modules.

### Code stability
Higher is better (0–1). Penalizes average churn, revert rate, and hotspot concentration. A “busy but healthy” repo can have high churn and still score moderately if work is spread out and rarely reverted.

### Dependency rate
Fraction of commits that touch manifests/lockfiles (`pyproject.toml`, `package.json`, `go.mod`, …). Spikes often line up with ecosystem upgrades or dependency thrash.

See [METRICS.md](METRICS.md) for formulas.

## 6. Phylogeny and ecological stages

Phylogeny builds a parent DAG from commit parents, then derives generations and branching. The **ecological stage** is a coarse label for where the history sits:

| Stage | Typical pattern |
|-------|-----------------|
| `pioneer` | Few commits, exploratory surface |
| `growth` | Rising churn, expanding file set |
| `disturbance` | Reverts / hotspot spikes |
| `consolidation` | Churn cools, structure settles |
| `maturity` | Stable, lower momentum |
| `decline` | Activity drops or debt-heavy thrash |

Treat the stage as a hypothesis to check against metrics and debt — not a judgment by itself.

## 7. Technical debt and past architectural mistakes

`debt` scans the working tree for deprecation / FIXME-style markers and infers **historical** smells from git:

- hotspot gravity (few files absorb most touches)
- test lag (features without proportional test touches)
- utility sink growth
- repeated revert surfaces

```powershell
python -m codeevolve --repo path\to\repo debt
```

In the full report, `debt.findings` and `debt.architectural_mistakes` feed the trend planner’s “mistakes” section.

## 8. Global trend report (planner + SLM / cloud)

Every full `analyze` runs a **top-down planner** that orders sections: mistakes → improvement → momentum → stage → priorities. By default a **heuristic** backend writes the markdown (no API key).

Optional OpenAI-compatible narrative:

```powershell
$env:CODEEVOLVE_LLM_API_KEY = "sk-..."
# optional:
# $env:CODEEVOLVE_LLM_BASE_URL = "https://api.openai.com/v1"
# $env:CODEEVOLVE_LLM_MODEL = "gpt-4o-mini"
python -m codeevolve --repo path\to\repo analyze --llm --md-out trend.md
```

The planner still supplies structure; the LLM fills prose from the same JSON context (metrics, semantics, phylogeny, debt).

## 9. End-to-end checklist

1. Install editable + confirm `python -m codeevolve --version`.
2. `analyze` a repo you know; save `--out` / `--md-out`.
3. Skim `code_stability`, `revert_rate`, `stage`, `debt_score`.
4. Open hot files + architectural mistakes — decide one remediation.
5. Re-run with `--since 90.days` next month and compare `improvement_trend` / `momentum`.

## Related docs

- [ARCHITECTURE.md](ARCHITECTURE.md) — pipeline modules
- [METRICS.md](METRICS.md) — formulas
- [README.md](../README.md) — install & quick start
