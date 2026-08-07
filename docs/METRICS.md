# Metrics

## Revert rate
`revert_count / commit_count` where subjects/bodies match revert patterns or `git revert` commits.

## Code stability (0–1)
`1 / (1 + α·avg_churn + β·revert_rate + γ·hotspot_concentration)`

## Dependency rate
Fraction of commits that touch manifests/lockfiles (`requirements*.txt`, `pyproject.toml`, `package.json`, `go.mod`, `Cargo.toml`, …).

## Momentum
`(recent_churn_rate - older_churn_rate) / (older_churn_rate + 1)` over the newest third of history.

## Improvement trend
Rise when recent revert rate and churn fall relative to older windows.

## Semantic drift
`1 - cosine(mean_embed(early), mean_embed(late))` on commit subjects/bodies.

## Debt score
Weighted mix of deprecation hits, TODO/FIXME markers, and architectural mistake patterns inferred from history (hotspot gravity, test lag, utility sink, repeated revert surfaces).
