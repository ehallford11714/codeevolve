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
        ├─ ecology.analyze_ecology      (clade stages, Lehman proxies)
        ├─ phylogeny.analyze_phylogeny  (commit DAG + global stage)
        ├─ debt.analyze_debt
        ├─ risk.analyze_risk            (FailurePoints)
        ├─ report.write_trend_report
        ├─ report.write_repo_report
        ├─ refactor.build_refactor_plan
        └─ models.hardware / backends   (heuristic | hf-qwen | cloud)
```

## Package layout

| Package | Role |
|---------|------|
| `ingest/` | GitHub URL → `~/.codeevolve/repos` cache |
| `taxonomy/` | Hierarchy + co-change clades + delta allocation |
| `genetics/` | Lineage, gene flow, HGT suspects, fitness |
| `ecology/` | Succession stages + Lehman proxies |
| `risk/` | Weakness / failure ranking |
| `refactor/` | Phased evidence-linked plan |
| `models/` | Hardware ladder, backend router, HF/cloud |
| `report/` | Drafted repo report |
| `report_trend.py` | Trend planner (MVP) |

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
