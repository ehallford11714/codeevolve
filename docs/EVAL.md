# Evaluation & rigor

CodeEvolve treats evolutionary “laws” and ecological stages as **hypotheses**, not grades.

## Layers

1. **Hypothesis panel** — `support | weak | contradict | insufficient` + confidence  
2. **Signal confidence** — hero ranking (coupling · churn×complexity · offboarding)  
3. **Synthetic fixtures** — planted ground truth (detection agreement)  
4. **Public-repo scorecard** — real GitHub tags; smoke + before/after directional checks  

## Run evaluation

```powershell
$env:CODEEVOLVE_SKIP_HF="1"
$env:CODEEVOLVE_TAXONOMY_HEURISTIC="1"
$env:CODEEVOLVE_SKIP_EMBED="1"

# Default: synthetic + public (public skips cleanly if offline / no cache)
python -m codeevolve evaluate --md-out eval.md --out eval.json

# Fixtures only (CI-friendly)
python -m codeevolve evaluate --suite synthetic

# Public scorecard (clones into ~/.codeevolve/repos)
python -m codeevolve evaluate --suite public --md-out public.md

# Offline: only cached clones; missing repos are skipped (not failed)
python -m codeevolve evaluate --suite all --offline

# Live single case
python -m codeevolve evaluate --suite public --public-case click_smoke_8.4.0
```

Exit code `0` when synthetic ≥ 0.70 (if run), public ≥ 0.55 (if any public cases ran), and combined ≥ 0.55.

Combined overall when both run: **0.45·synthetic + 0.55·public**.

### Synthetic fixtures

| Case | Planted truth | Expect |
|------|---------------|--------|
| `coupled_hotspot` | co-change + complex core | coupling + hotspot |
| `bus_factor_trap` | single-author hotspot | bus factor / offboarding |
| `stable_mature` | multi-author modest churn | stability band |
| `debt_disaster` | FIXME + revert | hotspot + revert surface |
| `decouple_before_after` | coupled → isolated | coupling weight drops |

### Public scorecard cases

| Case | Repo / refs | Kind | Expect |
|------|-------------|------|--------|
| `click_smoke_8.4.0` | pallets/click@8.4.0 | smoke | digest fields + hero ranking |
| `flask_smoke_3.0.0` | pallets/flask@3.0.0 | smoke | same |
| `requests_smoke_2.31.0` | psf/requests@v2.31.0 | smoke | same |
| `click_8.3_to_8.4_release` | 8.3.0→8.4.0 | before/after | stability/risk within tol; heroes+hypotheses remain (feature releases may raise coupling) |
| `click_8.4.0_to_8.4.2_patch` | 8.4.0→8.4.2 | before/after | patch stream does not worsen proxies |
| `flask_2.3_to_3.0_major` | 2.3.3→3.0.0 | before/after | coherent heroes; stability within wider tol |

Each analyze runs **detached at the tag** with `git log <ref>` so hotspots/complexity match that tree.

Optional live pytest: `CODEEVOLVE_LIVE_EVAL=1 pytest -m integration`.

## Interpreting scores

- **High synthetic** — detectors fire on planted patterns.  
- **High public** — tool runs on real tags; before/after moves stay inside calibrated tolerances.  
- **Skipped public** — offline / clone failure; not a detector failure.  
- Tolerances matter: majors may churn; we do **not** require debt to always fall after every release.

## Anti-goals

- Do not present stage labels as maturity grades.  
- Do not treat `support` as proof of a Lehman law.  
- Do not let SLM prose override numeric ranking.  
- Do not treat synthetic 96% as proof of real-world validity without the public scorecard.
