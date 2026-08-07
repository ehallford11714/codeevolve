# Evaluation & rigor

CodeEvolve treats evolutionary “laws” and ecological stages as **hypotheses**, not grades. Eval suites prove detectors and deliberation substrates fire on planted or public evidence — not that a repo is “good.”

## Layers

1. **Hypothesis panel** — `support | weak | contradict | insufficient` + confidence  
2. **Signal confidence** — hero ranking (coupling · churn×complexity · offboarding)  
3. **Synthetic fixtures** — planted ground truth (detection agreement)  
4. **Taxonomy gold + RAG** — path→type_path prefixes + RAG index/typed clades/engine meta  
5. **Ecology calibration** — PELT changepoints + lifecycle events (see [ECOLOGY.md](ECOLOGY.md))  
6. **Dynamics + provenance** — trajectory, impulses/basins, micro kinds, pack schema (see [DYNAMICS.md](DYNAMICS.md), [PROVENANCE.md](PROVENANCE.md))  
7. **Public-repo scorecard** — real GitHub tags; smoke + before/after directional checks  

### Why each layer

| Layer | Rationale |
|-------|-----------|
| Hypotheses / confidence | Keep claims graded; avoid fake precision |
| Synthetic | Fast CI: detectors see planted patterns |
| Taxonomy gold | Credibility for type hierarchy + RAG path |
| Ecology | Stages must move with events/CPs, not churn cutoffs alone |
| Dynamics | Trajectory + pack schema are the deliberation contract |
| Public scorecard | Tool survives real tags without claiming absolute truth |

## Run evaluation

```powershell
$env:CODEEVOLVE_SKIP_HF="1"
$env:CODEEVOLVE_TAXONOMY_HEURISTIC="1"
$env:CODEEVOLVE_SKIP_EMBED="1"

# Default: synthetic + taxonomy + ecology + dynamics + public
python -m codeevolve evaluate --md-out eval.md --out eval.json

python -m codeevolve evaluate --suite synthetic
python -m codeevolve evaluate --suite taxonomy
$env:CODEEVOLVE_SKIP_GHSA = "1"
python -m codeevolve evaluate --suite ecology
python -m codeevolve evaluate --suite dynamics
python -m codeevolve evaluate --suite public --md-out public.md
python -m codeevolve evaluate --suite all --offline
```

Exit code `0` when present suites meet floors: synthetic ≥ 0.70, taxonomy ≥ 0.70, ecology ≥ 0.70, **dynamics ≥ 0.70**, public ≥ 0.55 (if any public cases ran), and combined ≥ 0.55.

Combined overall when suites run: **0.25·taxonomy + 0.25·ecology + 0.20·dynamics + 0.20·public + 0.10·synthetic** (missing suites dropped and weights renormalized).

### Synthetic fixtures

| Case | Planted truth | Expect |
|------|---------------|--------|
| `coupled_hotspot` | co-change + complex core | coupling + hotspot |
| `bus_factor_trap` | single-author hotspot | bus factor / offboarding |
| `stable_mature` | multi-author modest churn | stability band |
| `debt_disaster` | FIXME + revert | hotspot + revert surface |
| `decouple_before_after` | coupled → isolated | coupling weight drops |

### Taxonomy gold + RAG

| Case | What it proves |
|------|----------------|
| `taxonomy_type_gold` | Path → type_path prefix agreement on curated paths |
| `taxonomy_rag_pipeline` | Chunk index, typed clades, guidance RAG meta; `CODEEVOLVE_LIVE_SLM=1` requires `hf-slm-rag` |

### Ecology calibration

See [ECOLOGY.md](ECOLOGY.md). Planted regimes → changepoints; event hints; fixture calibration.

### Dynamics + deliberation provenance

**Rationale:** without an eval suite, trajectory/pack/schema drift silently breaks agents.

| Case | What it proves |
|------|----------------|
| `dynamics_state_trajectory` | Enough monthly samples; z-scored coordinates present |
| `dynamics_impulse_basins` | Impulse responses + basins on planted events/segments |
| `dynamics_ledger_schema` | Ledger has state/blast/symbol/CST kinds; pack validates JSON Schema; risk frame links blast |

```powershell
python -m codeevolve evaluate --suite dynamics --md-out eval_dynamics.md
```

### Public scorecard cases

| Case | Repo / refs | Kind | Expect |
|------|-------------|------|--------|
| `click_smoke_8.4.0` | pallets/click@8.4.0 | smoke | digest fields + hero ranking |
| `flask_smoke_3.0.0` | pallets/flask@3.0.0 | smoke | same |
| `requests_smoke_2.31.0` | psf/requests@v2.31.0 | smoke | same |
| `click_8.3_to_8.4_release` | 8.3.0→8.4.0 | before/after | stability/risk within tol; heroes+hypotheses remain |
| `click_8.4.0_to_8.4.2_patch` | 8.4.0→8.4.2 | before/after | patch stream does not worsen proxies |
| `flask_2.3_to_3.0_major` | 2.3.3→3.0.0 | before/after | coherent heroes; stability within wider tol |

Each analyze runs **detached at the tag** with `git log <ref>` so hotspots/complexity match that tree.

## Related

- [PROVENANCE.md](PROVENANCE.md)
- [DYNAMICS.md](DYNAMICS.md)
- [ECOLOGY.md](ECOLOGY.md)
- [TUTORIAL.md](TUTORIAL.md)
