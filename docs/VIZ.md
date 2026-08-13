# Phylogeny visualization

Zero-dependency SVG/HTML/Newick views plus an interactive **3D phylogeny builder**. Built from a CodeEvolve report — it does not invent history.

## What you get

| Scene | Content |
|-------|---------|
| **3D builder** | Orbit/zoom canvas. X = generation, Y = lineage rank, Z = **semantic type** / intent / clade / analysis / stage. Click a node for type_path, niche, intent, analysis, and deliberation frames. |
| **Phylogeny** | Layered commit DAG. Fill = ecological stage window. Stroke = semantic type (keyword `type_path`). Lineages of the same type sit together. Dashed orange = extra parents (merges / reticulation). |
| **Clades** | Keyword-type hierarchy when present, otherwise the taxonomy clade forest. |
| **Parsimony** | First-parent spanning tree. Character = keyword `type_path` per commit (fallback: dominant clade). Fitch reconstruction on tips and at each ontology depth (domain → family → kind → specialty). Pink edges are type changes. Stats: steps, CI = m/s, RI = (g−s)/(g−m). |
| **Gene flow** | Circular clade map with weighted arcs from `genetics.gene_flow`. |

Newick is the first-parent spanning tree (not the full DAG); tip labels include the type key.

`analyze --viz-out` uses the in-memory phylogeny (uncapped) and full `path_types` / niche maps. `viz --report` uses `report.json`, where `phylogeny.nodes` is capped at 200 and taxonomy maps may be truncated.

## Semantic taxonomy on each division

Every split on the tree is a **taxon**, not only a co-change clade id:

1. Each commit votes over allocated paths using `taxonomy.keyword_taxonomy.path_types` (`type_path` = domain/family/kind/specialty).
2. Optional `taxonomy.semantic.path_to_niche` supplies a niche label when embeddings ran.
3. If the type record is silent, the division falls back to dominant `clade_id`, then `insufficient` — we do not invent a type.
4. Layout DFS-sorts siblings by that division so the same type occupies adjacent lineages. Unary collapse uses the same key.
5. Fitch runs on the full `type_key` and again on each prefix depth so internal nodes carry reconstructed ranks (`reconstructed_depths`).

## 3D builder

- **Type** (default color and Z): keyword `type_path` + niche. Silent types stay unlabeled.
- **Intent** is classified from the commit *subject* (conventional prefix `feat:` / `fix:` / …, or theme keywords). Silent subjects are `unknown` with stance `insufficient` — not a motive.
- **Analysis** on a node: type_path, niche, Fitch reconstructed type (and per-depth prefixes), clade, stage, allocation churn, clade risk, clade debt, merge/parsimony flags, linked `frame:*` ids (`claim → evidence → falsifier`).
- Repo panel (empty selection): stage, basin, Fitch CI/RI + character, type histogram, debt/risk summaries, intent histogram, `frame:stage` / `frame:basin` / `frame:delta:*`.
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
print(model.parsimony.character, model.parsimony.steps, model.division_counts)
print(builder_payload(model)["axes"])
```

## Parsimony (what it is / is not)

- Character is **unordered semantic type** (`type_path`), falling back to clade id when types are silent — not DNA.
- Tree is the **first-parent** spanning tree of git history (merges are extra DAG edges, not extra Fitch branches).
- Depth-wise Fitch reconstructs domain, then family, then kind, then specialty on the same tree.
- **m** = (distinct coded states) − 1; **s** = changing edges; extra steps are homoplasy on that tree.
- Do not read CI/RI as biological support or a Lyapunov exponent.
