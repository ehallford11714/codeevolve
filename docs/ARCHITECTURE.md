# Architecture

```
CLI / CodeEvolve(repo|github-url)
        │
        ├─ ingest.resolve_repo          (local | clone/cache GitHub)
        ├─ gitlog.load_commits
        ├─ metrics.compute_metrics
        ├─ semantics.analyze_semantics
        ├─ taxonomy.build_taxonomy      (keywords, RAG, SLM, MiniLM/W2V, symbols)
        ├─ genetics.analyze_genetics    (lineage, gene flow, fitness)
        ├─ ecology.analyze_ecology      (stages + event/changepoint calibration)
        ├─ hierarchy_trends             (typed branch heating/cooling, experiments)
        ├─ coupling / clones / reticulation / CST / deps / offboarding / fork lineage
        ├─ phylogeny.analyze_phylogeny  (commit DAG + global stage)
        ├─ debt.analyze_debt
        ├─ risk.analyze_risk            (FailurePoints; churn×complexity hotspots)
        ├─ blast_radius_table
        ├─ selection / fatigue / stability / hypotheses / signal confidence
        ├─ provenance.build_dynamics    (state trajectory, impulses, basins, episodes)
        ├─ provenance.build_ledger      (records + deliberation frames)
        ├─ report.write_trend_report
        ├─ report.write_repo_report     (includes provenance frame summary)
        ├─ refactor.build_refactor_plan
        ├─ pr_comment / dashboard / viz / ci  (surface frames + phylogeny)
        └─ models.hardware / backends   (heuristic | hf-qwen | cloud)
```

## Why this pipeline order

| Stage | Rationale |
|-------|-----------|
| Taxonomy before genetics/ecology | Allocations and clades are the spatial units later layers annotate |
| Ecology calibration after raw stages | Events/CPs relabel regimes without throwing away heuristics as fallback |
| Dynamics after ecology + fatigue/selection | Trajectory needs monthly series *and* process forcing coordinates |
| Provenance last among analyzers | Ledger is a projection for deliberation, not a new sensor |
| Report/PR/dashboard/viz after provenance | Human surfaces should cite the same `frame:*` ids agents resolve |

## Package layout

| Package | Role |
|---------|------|
| `ingest/` | GitHub URL → cache; Issues/PR selection pressure (+ recent issue/PR samples) |
| `taxonomy/` | Keyword ontology + RAG + SLM guide + MiniLM/W2V + symbols + CST |
| `ecology/` | Event/changepoint calibration, stages, Lehman, hierarchy trends |
| `genetics/` | Rename-aware lineage, gene flow, fitness, clones, reticulation, alleles |
| `risk/` | Failure points + blast radius + coupling + dependencies |
| `provenance/` | Dynamics + ledger + schema/MCP dispatch |
| `mcp/` | Stdio MCP server (Content-Length JSON-RPC) + JSONL legacy mode |
| `agent/` | Cognitive coding agent (memory, RAG, morphemes, reflect/act/compact, kernel subagents, tools) |
| `eval/` | Synthetic, taxonomy gold, ecology, **dynamics**, public scorecard, agent outcomes |
| `viz/` | 3D phylogeny builder (intent + analysis) + clade tree + Fitch parsimony + gene-flow |
| `refactor/` | Phased plan + effort heuristics |
| `models/` | Tiers (slm→frontier), SLM taxonomy guide, HF/cloud |
| `psychology/` | Fatigue / sprint rhythm + cognitive-load proxies |
| `report/` | Drafted repo report |
| `metrics_stability.py` | Stability v2 decomposition |

## Ecological stages

| Stage | Typical signals |
|-------|-----------------|
| pioneer | early / sparse |
| growth | high churn, low reverts |
| disturbance | high revert rate / security / storms |
| consolidation | churn cools, structure settles |
| maturity | high stability, low momentum |
| decline | activity collapse |

Stages are computed **globally** and **per clade**, then optionally **recalibrated** from lifecycle events + changepoints ([ECOLOGY.md](ECOLOGY.md)). Dynamics exposes them as **basin occupancy** for deliberation ([DYNAMICS.md](DYNAMICS.md)).

## Provenance surface

| API | Role |
|-----|------|
| `report.dynamics` | Black-box trajectory artifacts |
| `report.provenance` | Full ledger + frames |
| `provenance` CLI | pack / path-pack / frame / resolve / timeline / schema |
| `schemas/` | Deliberation pack JSON Schema + MCP tool list |
| `python -m codeevolve.mcp` | MCP stdio (`analyze_repo` + provenance_* + `viz_phylogeny` + `evolve_toward_objective`) |
| `python -m codeevolve viz` | 3D phylogeny builder (intent/analysis) + 2D clade/parsimony/gene-flow |
| `python -m codeevolve.agent` | Objective improve loop (dry-run or `--apply`) |

Rationale and kinds: [PROVENANCE.md](PROVENANCE.md).

## LLM routing

`assess_hardware` → Qwen ladder (0.5B→7B). `recommend_execution` chooses `hf-qwen` | cloud | `heuristic`. Planner and provenance stay numeric/evidence-first; models only polish prose when requested.
