# Phylogeny visualization

Zero-dependency SVG/HTML/Newick views plus an interactive **3D phylogeny builder**. Built from a CodeEvolve report — it does not invent history.

## What you get

| Scene | Content |
|-------|---------|
| **3D builder** | Orbit/zoom canvas. X = generation, Y = lineage rank, Z = intent / clade / analysis / stage. Click a node for intent + analysis + deliberation frames. |
| **Phylogeny** | Layered commit DAG. Fill = ecological stage window. Stroke = dominant clade. Dashed orange = extra parents (merges / reticulation). |
| **Clades** | Keyword-type hierarchy when present, otherwise the taxonomy clade forest. |
| **Parsimony** | First-parent spanning tree. Character = dominant clade per commit. Fitch reconstruction on tips; tree length = observed clade changes on coded edges. Pink edges are state changes. Stats: steps, CI = m/s, RI = (g−s)/(g−m). |
| **Gene flow** | Circular clade map with weighted arcs from `genetics.gene_flow`. |

Newick is the first-parent spanning tree (not the full DAG).

`analyze --viz-out` uses the in-memory phylogeny (uncapped). `viz --report` uses `report.json`, where `phylogeny.nodes` is capped at 200.

## 3D builder

- **Intent** is classified from the commit *subject* (conventional prefix `feat:` / `fix:` / …, or theme keywords). Silent subjects are `unknown` with stance `insufficient` — not a motive.
- **Analysis** on a node: clade, Fitch reconstructed clade, stage, allocation churn, clade risk, clade debt, merge/parsimony flags, linked `frame:*` ids (`claim → evidence → falsifier`).
- Repo panel (empty selection): stage, basin, Fitch CI/RI, debt/risk summaries, intent histogram, `frame:stage` / `frame:basin` / `frame:delta:*`.
- Controls: color mode, Z axis, tree / merge / parsimony edges, text filter. Drag = orbit, Shift-drag = pan, wheel = zoom.

## CLI

```powershell
python -m codeevolve --repo . analyze --no-ensure-slm --out .codeevolve/report.json --viz-out .codeevolve/viz.html
python -m codeevolve viz --report .codeevolve/report.json --out .codeevolve/viz.html
python -m codeevolve viz --report .codeevolve/report.json --out .codeevolve/builder.html --kind 3d
python -m codeevolve viz --report .codeevolve/report.json --out .codeevolve/viz --kind all
python -m codeevolve viz --report .codeevolve/report.json --out tree.nwk --format newick
python -m codeevolve viz --report .codeevolve/report.json --out phylo.svg --kind phylogeny --format svg
```

Directory `--out` writes `gallery.html`, `builder.html`, per-scene SVGs, `tree.nwk`, and `viz.json`.

## MCP

`viz_phylogeny` with `from_report` (and optional `out`, `kind`=`all`|`3d`|…, `format`, `collapse_unary`).

## Python

```python
from codeevolve.viz import write_viz, build_model, builder_payload

write_viz(report, "viz.html")                 # gallery (3D first tab)
write_viz(report, "builder.html", kind="3d")  # full-page 3D builder
model = build_model(report)
print(model.parsimony.steps, model.intent_counts)
print(builder_payload(model)["axes"])
```

## Parsimony (what it is / is not)

- Character is **unordered clade id**, not DNA.
- Tree is the **first-parent** spanning tree of git history (merges are extra DAG edges, not extra Fitch branches).
- **m** = (distinct coded clades) − 1; **s** = changing edges; extra steps are homoplasy on that tree.
- Do not read CI/RI as biological support or a Lyapunov exponent.
