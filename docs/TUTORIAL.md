# Tutorial: evolve, report, deliberate

CodeEvolve turns **git history** (local or GitHub) into taxonomy, phylogeny, debt, failure points, a **drafted repo report**, an **evidence-linked refactor plan**, and a **provenance ledger** for deliberation over how the codebase evolved.

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

**Why this shape:** git already records *what* changed. CodeEvolve adds evolutionary structure (clades, stages, risks) and then a deliberation substrate (provenance) so humans and agents can argue from evidence — without inventing a “why” when the record is silent.

```
ingest → taxonomy/clades → genetics + ecology (events/changepoints)
       → metrics + debt + weaknesses
       → dynamics (state trajectory) → provenance ledger + frames
       → repo report + refactor plan + PR/dashboard surfaces
       → optional HF Qwen / cloud narrative
```

| Layer | Job | Rationale |
|-------|-----|-----------|
| Taxonomy / genetics | Structure the history | Co-change and lineage are the natural units of evolution |
| Ecology | Regime hypotheses | Stages must be falsifiable against releases/shocks (see [ECOLOGY.md](ECOLOGY.md)) |
| Risk / debt | Actionable pressure | Refactor needs ranked surfaces, not only narratives |
| Dynamics | Joined state over time | Separate series (churn, reverts, fatigue) only become deliberable as one trajectory |
| Provenance | Claim → evidence → falsifier | Agents and humans need a queryable substrate, not a reasoner ([PROVENANCE.md](PROVENANCE.md)) |

## 2. Analyze a local repo

```powershell
python -m codeevolve --repo . analyze `
  --out report.json `
  --report-out repo_report.md `
  --refactor-out refactor_plan.md
```

Open `repo_report.md` for the brief; `refactor_plan.md` for phased steps (`stabilize` → `contain` → `pay_down` → `evolve`). Every refactor step cites `W*` failure-point IDs. The report also surfaces top **deliberation frames** so the brief points into the provenance loop.

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
| `hierarchy` | Nested “what was built” + heating/cooling |
| `phylogeny` / ecology via analyze | Commit DAG + calibrated stages |
| `debt` | Deprecations + arch mistakes |
| `risk` | Ranked failure points |
| `provenance` | Ledger query / pack / frames (see §9) |
| `report` | Drafted markdown repo report |
| `refactor` | Phased refactor plan |
| `hardware` | RAM/VRAM + recommended Qwen / cloud |

## 5. Reading signals

- **Clades** — co-changing file groups; deltas are allocated to `clade_id`.
- **Fitness** — low fitness lineages often appear as failure points.
- **Lehman proxies** — continuing change, complexity, growth, quality decline, familiarity, feedback volatility.
- **Failure points** — hotspot blast radius, revert surfaces, bus factor, test gap, dependency shock.
- **Refactor waves** — stop bleeding first (`stabilize`), then boundaries (`contain`), debt (`pay_down`), structure (`evolve`).
- **Frames** — `frame:stage`, `frame:basin`, `frame:risk:*`, etc. — claims you can accept/reject against evidence.

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
from pathlib import Path

r = CodeEvolve("owner/repo").analyze(max_commits=300, use_llm="auto")
print(r.taxonomy.clades[0].label)
print(r.risk.failure_points[0].to_dict())
print(r.refactor_plan.steps[0].evidence_refs)
print(r.dynamics["summary"])
print(r.provenance.frames[0].id, r.provenance.frames[0].claim)
Path("repo_report.md").write_text(r.repo_report.markdown, encoding="utf-8")
```

## 8. Symbols & GitHub selection pressure

**Why:** symbols give micro-structure for hotspots; Issues/PRs are the richest *stated* external evidence (bug backlog, merge health) that ecology alone cannot see.

```powershell
python -m codeevolve --repo . symbols
python -m codeevolve --repo pallets/flask selection
$env:GITHUB_TOKEN = "ghp_..."
python -m codeevolve --repo pallets/flask analyze --out report.json
```

Selection pressure scores bug labels, reopen-like language, open backlog, and PR merge rate. In 0.15+ those samples also become `selection_item` provenance records and `frame:selection`.

## 9. Provenance ledger (deliberation)

**Why this exists:** CodeEvolve does **not** model reasoning. After ecology/risk/hypotheses, scattered signals are hard to use in CI, PR review, or agent tools. The ledger normalizes them into records + **deliberation frames** (claim → evidence → falsifier → measure).

```powershell
# Compact pack for agents / reviews
python -m codeevolve --repo . provenance --pack

# Path-centric (lineage, episodes, blast, symbols, CST)
python -m codeevolve --repo . provenance --path-pack src/api.py

# Expand one claim
python -m codeevolve --repo . provenance --frame frame:basin
python -m codeevolve --repo . provenance --resolve frame:stage --depth 2

# Offline from a saved report
python -m codeevolve provenance --from-report report.json --pack --out deliberation.json
```

### Deliberation loop

1. Pick a frame (`frame:stage`, `frame:basin`, `frame:selection`, `frame:delta:report`, `frame:risk:*`, …)
2. Expand / resolve evidence
3. Check **falsifier** and **measure** before acting
4. Re-ask `suggested_questions` on fresh git (or re-analyze)

If evidence is missing, stance stays `insufficient` — that is a valid outcome, not a prompt to invent motive.

Full reference: [PROVENANCE.md](PROVENANCE.md).

## 10. Dynamics (state trajectory)

**Why:** ecology events and monthly series were adjacent but not joined. Dynamical-systems *black-box* methods (FEAST / Lehman feedback tradition) say the useful object is a **trajectory** \(x(t)\), not isolated scalars. We do **not** claim chaos or fit ODEs on short histories.

```powershell
python -m codeevolve --repo . analyze --out report.json
# report.dynamics: samples, impulses, basins, episodes
python -m codeevolve --repo . provenance --timeline
python -m codeevolve --repo . provenance --frame frame:response:v2.0.0
```

| Dynamics object | Use in deliberation |
|-----------------|---------------------|
| `state_sample` | Monthly joined coordinates (activity, churn, instability, load, …) |
| `trajectory` | Whole-repo γ for “are we leaving the basin?” |
| `impulse_response` | Δx after release / GHSA / revert storm |
| `regime_basin` | Occupancy → stage confidence |
| `path_episode` | Clustered lives of a file for path packs |

Details: [DYNAMICS.md](DYNAMICS.md).

## 11. Compare across reports (temporal deliberation)

**Why:** a single analyze is a snapshot. CI and PR review need “what flipped since last run.”

```powershell
python -m codeevolve --repo . analyze --out report.json --previous report.prev.json `
  --dashboard-out dash.html
python -m codeevolve comment --report report.json --previous report.prev.json --out pr.md
python -m codeevolve provenance --from-report report.json --frame frame:delta:report
```

`report.diff` becomes `report_delta` records and `frame:delta:report`. The PR comment and dashboard list top frames so humans and agents share one deliberation surface.

## 12. Schema, MCP tools, and eval

**Why:** packs must be stable for agents. JSON Schema validates shape; MCP-shaped tools expose pack / expand / path / resolve / timeline without inventing a new API language.

```powershell
python -m codeevolve provenance --schema-out schemas
python -m codeevolve evaluate --suite dynamics   # real public tags only
python examples/demo_dynamics.py                 # Click@8.4.0 walkthrough
# optional JSON-lines tool server:
# python -m codeevolve.mcp.server
```

See [DEMO_DYNAMICS.md](DEMO_DYNAMICS.md) and [EVAL.md](EVAL.md).

## Related

- [PROVENANCE.md](PROVENANCE.md) — ledger, frames, kinds, MCP
- [DYNAMICS.md](DYNAMICS.md) — state trajectory rationale
- [ECOLOGY.md](ECOLOGY.md) — event/changepoint calibration
- [ARCHITECTURE.md](ARCHITECTURE.md)
- [METRICS.md](METRICS.md)
- [CLOUD.md](CLOUD.md)
- [EVAL.md](EVAL.md)
