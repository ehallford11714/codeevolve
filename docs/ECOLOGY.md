# Ecology calibration (0.13)

Stages are **hypotheses** grounded in lifecycle events and activity changepoints
(Walden et al. [arXiv:2103.11013](https://arxiv.org/abs/2103.11013)), not churn cutoffs alone.

```
commits → monthly series → PELT-lite changepoints
tags / GHSA / revert storms → lifecycle events
     → align (±45d) → labeled segments → calibrated global_stage
```

## Outputs

| Field | Meaning |
|-------|---------|
| `ecology.calibration.global_stage` | Event/CP-aware stage (also mirrored on `ecology.global_stage`) |
| `ecology.calibration.method` | `event_changepoint` \| `event_anchor` \| `heuristic_fallback` |
| `ecology.calibration.events` | Tags, majors/minors/patches, security, revert storms, pioneer |
| `ecology.calibration.changepoints` | Monthly commits/authors/reverts/churn regime shifts |
| `ecology.calibration.anchors` | Event ↔ nearest CP with Δdays |
| `ecology.calibration.hit_rate` | Fraction of large CPs within ±45d of an event |

## Commands

```powershell
python -m codeevolve --repo . analyze --out report.json
# inspect report.ecology.calibration

python -m codeevolve evaluate --suite ecology --md-out eval_ecology.md

# Skip GitHub advisories
$env:CODEEVOLVE_SKIP_GHSA = "1"
```

## Stage ↔ event hints

| Event | Stage hint |
|-------|------------|
| pioneer_window / history start | pioneer |
| major / minor release | growth |
| patch release | maturity |
| security advisory / CVE tag | disturbance |
| revert storm | disturbance |
| CP commits/churn down after growth | consolidation |

## Eval

`evaluate --suite ecology` runs:

1. Synthetic regime shifts → PELT-lite detects ups/downs  
2. Event stage-hint mapping  
3. Full calibration on a fixture repo  

Still hypotheses — success means detectors fire and anchors attach, not that a repo is “mature.”

## Downstream: dynamics & provenance

Calibrated events and segments feed the **dynamics** layer as impulse triggers and basin intervals (`report.dynamics`), then become ledger records and frames (`frame:response:*`, `frame:basin`). See [DYNAMICS.md](DYNAMICS.md) and [PROVENANCE.md](PROVENANCE.md).
