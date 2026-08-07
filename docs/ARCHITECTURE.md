# Architecture

```
CLI / CodeEvolve.analyze
        │
        ├─ gitlog.load_commits          (git log + numstat)
        ├─ metrics.compute_metrics      (revert, stability, deps, momentum)
        ├─ semantics.analyze_semantics  (embedding themes + hierarchy)
        ├─ phylogeny.analyze_phylogeny  (DAG + ecological stages)
        ├─ debt.analyze_debt            (deprecations, TODOs, arch mistakes)
        └─ report.write_trend_report    (top-down plan → heuristic|LLM markdown)
```

## Design choices (MVP)

- **Git CLI** instead of libgit2 — portable, no compile deps.
- **Hashing-trick embeddings** by default — deterministic, offline; swap-in real models later (`embed` extra).
- **Top-down planner** picks section order + priorities from numeric gates before any prose is written.
- **Heuristic report backend** always works; OpenAI-compatible backend is opt-in via `--llm` / env.

## Ecological stages

| Stage | Typical signals |
|-------|-----------------|
| pioneer | early history, sparse commits |
| growth | high churn, low reverts |
| disturbance | high revert rate / shock churn |
| consolidation | refactors/tests rise, churn cools |
| maturity | high stability, low momentum |
| decline | activity collapse |
