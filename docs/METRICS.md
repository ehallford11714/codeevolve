# Metrics

## Revert rate
`revert_count / commit_count` where subjects/bodies match revert patterns or `git revert` commits.

## Code stability (legacy 0–1)
`1 / (1 + α·avg_churn + β·revert_rate + γ·hotspot_concentration)`

## Stability v2 (decomposed)
| Component | Signal |
|-----------|--------|
| structural | Inverse hotspot concentration + utility overcrowding + load |
| behavioral | Inverse revert rate |
| dependency | Inverse dependency churn rate |
| test | Test/prod co-touch ratio |
| rhythm | Inverse fatigue score |
| **composite** | Weighted mix of the above |

## Dependency rate
Fraction of commits that touch manifests/lockfiles.

## Momentum / improvement trend
Recent vs older churn; cooling reverts/churn → positive improvement.

## Semantic / genetic drift
- Global: `1 - cosine(mean_embed(early), mean_embed(late))` on commit text
- Per-clade drift in `drift.clade_drift`
- Neutral churn: high late activity with low semantic change

## Fatigue / sprint KPIs
After-hours rate, weekend rate, intensity creep, recovery ratio, end-of-sprint dump → `fatigue_score`.

## Cognitive load proxies
Context-switch rate (clades/commit), attention entropy, ownership stress → `load_index`.

## Debt score
Deprecations, TODOs, historical architecture smells.

## Taxonomy guidance
Default **SLM tier** labels clade niches/roles (`taxonomy.guidance`).
