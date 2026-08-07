# Dynamics: black-box state trajectories (0.15+)

CodeEvolve’s dynamics layer treats a repository as an **observed trajectory** in a low-dimensional state space. It is a deliberation aid for provenance — not a physics simulator and not a model of developer cognition.

## Why a dynamics layer

| Gap before 0.15 | Dynamics fix |
|-----------------|--------------|
| Monthly commits/authors/reverts/churn analyzed separately | One `state_sample` vector per month |
| Stages were labels next to series | `regime_basin` occupancy from trajectory + segments |
| Lifecycle events sat unused beside metrics | `impulse_response`: Δx after event |
| Path history was flat delta lists | `path_episode` clusters for path packs |
| Lehman claims lacked mechanism-shaped evidence | Progressive pressure visible as coordinates + impulses |

This follows the FEAST / Lehman **feedback system** tradition: observe black-box metric dynamics before white-box policy simulation. White-box stock-flow sims remain **deferred** until trajectories are routinely queryable and falsifiable.

## Pipeline

```
commits (+ fatigue, selection, branch heat)
    → monthly_activity
    → z-scored state_sample[]  (= x(t))
    → impulse_response(event, horizon)
    → regime_basin(segments | heuristics)
    → path_episode(allocations)
    → provenance ledger + frames
```

Implementation: `src/codeevolve/provenance/dynamics.py`, attached on analyze as `report.dynamics` and ingested by `build_provenance_ledger`.

## State vector (v1)

| Coordinate | Source | Deliberation use |
|------------|--------|------------------|
| `activity` | monthly commits (z) | growth vs dormancy |
| `authors` | unique authors (z) | participation pressure |
| `churn` | insertions+deletions (z) | expansion pressure |
| `instability` | reverts/commits (z) | negative-feedback strength |
| `load` | fatigue weekly intensity | process oscillator |
| `selection` | GitHub pressure score | external forcing |
| `typed_heat` | hierarchy branch heat | where flow concentrates |

**Rationale for z-scores:** cross-repo and within-repo scale differ wildly; deliberation cares about *relative* regime, not raw LOC.

**Epistemic guard:** if fewer than ~12 months of samples, `insufficient` is tagged on the trajectory — do not claim strong DST results.

## Impulse responses

For each lifecycle event (release, security, revert storm, …), compare mean state in the `horizon` months before vs after.

**Rationale:** ecology calibration already detects events and changepoints ([ECOLOGY.md](ECOLOGY.md)). Impulse responses answer the deliberation question those detectors raise: *did the shock move the trajectory, and how?*

Frames: `frame:response:<label>`.

## Regime basins

Basins prefer calibrated `stage_segment`s when present; otherwise heuristic terciles on activity/instability.

**Rationale:** calling a stage an “attractor” without occupancy is metaphorical. Occupancy + mean state make `frame:basin` falsifiable (“occupancy drops >25%”).

## Path episodes

Allocations on a path are chunked into episodes (touch gaps).

**Rationale:** a file’s “life” is not one lineage scalar — it has eras. Path packs expose episodes next to blast/symbol/CST for edit decisions.

## What we do not claim

- Lyapunov exponents / chaos on typical git windows  
- Causal identification (impulse response is observational)  
- Optimal refactor policy from simulation  

## Commands & eval

```powershell
python -m codeevolve --repo . analyze --out report.json
python -m codeevolve --repo . provenance --timeline
python -m codeevolve --repo . provenance --frame frame:basin

# Real public tags only (Click / Flask / Requests) — no synthetic history
python -m codeevolve evaluate --suite dynamics --md-out eval_dynamics.md

# Interactive demo
python examples/demo_dynamics.py
```

`evaluate --suite dynamics` clones real GitHub tags and scores trajectory / major-era impulses / basin frames. Offline or clone failures **skip** cases. Walkthrough: [DEMO_DYNAMICS.md](DEMO_DYNAMICS.md).

## Related

- [PROVENANCE.md](PROVENANCE.md) — ledger consumption of dynamics  
- [ECOLOGY.md](ECOLOGY.md) — events and changepoints as \(u(t)\) / breakpoints  
- [EVAL.md](EVAL.md) — suite wiring  
