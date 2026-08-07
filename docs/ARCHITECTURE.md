# Architecture

```
CLI / CodeEvolve(repo|github-url)
        │
        ├─ ingest.resolve_repo          (local | clone/cache GitHub)
        ├─ gitlog.load_commits
        ├─ metrics.compute_metrics
        ├─ semantics.analyze_semantics
        ├─ taxonomy.build_taxonomy      (layers, clades, allocations)
        ├─ genetics.analyze_genetics    (lineage, gene flow, fitness)
        ├─ ecology.analyze_ecology      (clade stages, Lehman + Mann–Kendall)
        ├─ coupling / clones / reticulation / CST / deps / offboarding / fork lineage
        ├─ phylogeny.analyze_phylogeny  (commit DAG + global stage)
        ├─ debt.analyze_debt
        ├─ risk.analyze_risk            (FailurePoints; churn×complexity hotspots)
        ├─ report.write_trend_report
        ├─ report.write_repo_report
        ├─ refactor.build_refactor_plan (SQALE-like person-days)
        └─ models.hardware / backends   (heuristic | hf-qwen | cloud)
```

## Package layout

| Package | Role |
|---------|------|
| `ingest/` | GitHub URL → cache; Issues/PR API selection pressure |
| `taxonomy/` | Keyword ontology + RAG chunks + SLM guide + MiniLM/W2V + symbols |
| `ecology/` | Stages, Lehman/Mann–Kendall, hierarchy trend narratives |
| `genetics/` | Rename-aware lineage, gene flow, fitness |
| `ecology/` | Stages, niches, Lehman proxies |
| `risk/` | Failure points + blast radius |
| `refactor/` | Phased plan + effort heuristics |
| `models/` | Tiers (slm→frontier), SLM taxonomy guide, HF/cloud |
| `psychology/` | Fatigue / sprint rhythm + cognitive-load proxies |
| `metrics_stability.py` | Stability v2 decomposition |
| `report/` | Drafted repo report |
| `report_trend.py` | Trend planner |

## Ecological stages

| Stage | Typical signals |
|-------|-----------------|
| pioneer | early / sparse |
| growth | high churn, low reverts |
| disturbance | high revert rate |
| consolidation | churn cools, structure settles |
| maturity | high stability, low momentum |
| decline | activity collapse |

Stages are computed **globally** and **per clade**.

## LLM routing

`assess_hardware` → Qwen ladder (0.5B→7B). `recommend_execution` chooses `hf-qwen` | cloud | `heuristic`. Planner stays numeric-first; models only polish prose.
