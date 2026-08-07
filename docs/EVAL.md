# Evaluation & rigor

CodeEvolve treats evolutionary “laws” and ecological stages as **hypotheses**, not grades.

## What rigor means here

1. **Hypothesis panel** (`hypothesis_panel`) — each Lehman-style claim has:
   - `verdict`: `support` | `weak` | `contradict` | `insufficient`
   - `confidence`: evidence strength from sample size + Mann–Kendall clarity (not truth)
   - `method`, `sample_size`, `evidence`, `caveats`
2. **Signal confidence** (`signal_confidence`) — hero signals ranked by reliability:
   - change coupling
   - hotspot churn × complexity
   - offboarding risk
3. **Benchmark suite** (`codeevolve evaluate`) — synthetic git fixtures with planted ground truth; scores **detection agreement**, not absolute truth about real repos.

## Run evaluation

```powershell
$env:CODEEVOLVE_SKIP_HF="1"
$env:CODEEVOLVE_TAXONOMY_HEURISTIC="1"
python -m codeevolve evaluate --md-out eval.md --out eval.json
```

Exit code `0` if overall score ≥ 0.70.

### Fixture cases

| Case | Planted truth | Expect |
|------|---------------|--------|
| `coupled_hotspot` | `core.py`↔`api.py` always co-change; complex core | coupling edge + hotspot |
| `bus_factor_trap` | single author on hot file | bus factor / offboarding |
| `stable_mature` | multi-author modest churn | stability band; no dep shock |
| `debt_disaster` | FIXME + revert | hotspot + revert surface |
| `decouple_before_after` | coupled then isolated edits | coupling weight drops |

## Interpreting scores

- **High overall** means detectors fire on planted patterns and before/after moves the right way.
- **Low confidence** on a live repo means “don’t overclaim,” not “repo is healthy.”
- Proxy scores in `ecology.lehman` remain for continuity; prefer `hypothesis_panel` for narrative.

## Anti-goals

- Do not present stage labels as maturity grades.
- Do not treat `support` as proof of a Lehman law.
- Do not let SLM prose override numeric ranking.
