# Demo: dynamics + provenance on a real public tag

This walkthrough uses **live git history** (default: [pallets/click](https://github.com/pallets/click) `@8.4.0`). No synthetic commits.

## Why this demo

| Step | What you see | Rationale |
|------|----------------|-----------|
| Clone real tag | Same artifacts CI uses | Trajectory claims must survive real release history |
| Dynamics summary | months, impulses, basins | Black-box \(x(t)\) before any “stage” storytelling |
| Frames | claim → falsifier | Unit of deliberation for agents/humans |
| Impulse / basin lines | Shock response + occupancy | Events should move the trajectory, not sit unused |
| Path pack | Hot file episodes + blast | Pre-edit Chesterton pack |
| Schema OK | Pack validates | Agent contract |

## Quick run

```powershell
cd codeevolve
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"

# Default: Click 8.4.0
python examples/demo_dynamics.py

# Flask major era (impulse-oriented)
python examples/demo_dynamics.py --repo pallets/flask --ref 3.0.0 --max-commits 280

# Save deliberation pack
python examples/demo_dynamics.py --out demo_pack.json
```

## Expected console shape

```
=== Dynamics (real history) ===
Dynamics: N state samples, … impulse responses, … basins, …
samples=… impulses=… basins=…

=== Deliberation frames (top) ===
- frame:stage […] …
- frame:basin […] …
…

=== Path pack: <hot path> ===
clade=… episodes=…
? What first introduced …
```

Then open `demo_pack.json` (if written) or re-query:

```powershell
python -m codeevolve --repo pallets/click provenance --from-report demo_pack.json
# Or live:
python -m codeevolve --repo pallets/click provenance --pack --frame frame:basin
```

## Eval (same real tags)

```powershell
python -m codeevolve evaluate --suite dynamics --md-out eval_dynamics.md
```

Cases (all public tags):

| Case | Repo@ref | Focus |
|------|----------|--------|
| `click_trajectory_8.4.0` | pallets/click@8.4.0 | Trajectory + pack schema |
| `flask_major_impulse_3.0.0` | pallets/flask@3.0.0 | Lifecycle events + impulse responses |
| `requests_basin_2.31.0` | psf/requests@v2.31.0 | Basin / stage frames + path pack |

Offline / missing clones **skip** (do not fail):

```powershell
python -m codeevolve evaluate --suite dynamics --offline
```

## Deliberation loop (after the demo)

1. Pick `frame:basin` or `frame:response:*`
2. `provenance --frame <id>` / `--resolve <id>`
3. Check falsifier before acting
4. Re-run with `--previous` later for `frame:delta:report`

See [PROVENANCE.md](PROVENANCE.md) and [DYNAMICS.md](DYNAMICS.md).
