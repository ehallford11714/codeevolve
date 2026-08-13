# Context graph and agentic flow

A **context graph** joins phylogeny (commits, types, clades), provenance frames, agent traces, and **coding pivots** into one searchable graph. It does not invent history — silent records stay unlabeled (`insufficient`).

The 2026 literature unit of value is the **judgment** (why allowed / overridden), not an entity snapshot. CodeEvolve stores that as decision traces with policy nodes, validity windows, and write-back at each agent round.

## Graph families

| Family | Kinds | Primitives (edges) | Pivot use |
|--------|--------|--------------------|-----------|
| `taxon` | `commit`, `type`, `clade`, `niche`, `path` | `parent_of`, `typed_as`, `in_clade`, `in_niche`, `contains`, `touches`, `gene_flow` | When a path is chosen, join `type_path` + clade neighborhood |
| `context` | `context`, `window`, `focus`, `fence`, `blast`, `delta` | `focuses`, `in_window`, `fenced_by`, `blast_of` + `valid_from`/`valid_to` | Each round writes fence/focus with a validity window |
| `knowledge` | `frame`, `record`, `policy`, `authority`, `claim` | `cites`, `allowed_by`, `constrained_by`, `falsified_by` | Proposals cite frames + policies (`insufficient-if-silent` is a policy node) |
| `decision` | `decision`, `proposal`, `score`, `reflection` | `allowed_because`, `overridden`, `refused`, `precedes`, `scored` | Every round writes a decision node (live write-back) |
| `pivot` | `pivot` | `pivots`, `joins`, `next_pivot` | Join point across families at a coding step |
| `flow` | `run`, `round`, `kernel`, `subagent`, `tool`, `rag`, `morpheme`, `memory`, `patch`, `test` | `next`, `spawned`, `invoked`, `proposed`, `scored`, `retrieved`, `reflects`, `focuses` | Walk `sense → deliberate → act → verify` |

**Pivot types:** `sense`, `deliberate`, `act`, `verify`, plus coding pivots `choose_path`, `propose`, `apply_or_dry_run`, `score`, `spawn`, `rollback`.

**Policies (always ingested):** `policy:insufficient-if-silent`, `policy:no-chaos`, `policy:dry-run-before-apply`, `policy:falsifier-required`, `policy:path-fence`, under `authority:codeevolve`.

PROV-lite on nodes: `source`, `confidence`, `authority`, `valid_from`, `valid_to`. Not W3C PROV-O / RDF-star.

Ecology stage, debt score, and risk/blast rows are ingested **only if present** on `report.json`. GitLab MRs/pipelines are not invented.

## Traversal (search engine)

Token overlap is the seed. Traversal finds the neighborhood:

| Mode | Algorithm |
|------|-----------|
| `wave` (default) | Multi-source BFS wavefront: hop distance + token score |
| `bfs` / `dfs` | Bounded-depth expansion (rel / kind / family filters, `max_nodes`) |
| `flow` | Walk `FLOW_RELS` + `next_pivot` in stage order |
| `pivot` | Fan out from pivot `joins` into family neighborhoods |
| `rw` | Spreading visit scores (decay to neighbors; not FastRP / PageRank-claimed) |
| `off` | Token ranking only |

Also: unweighted shortest path, bidirectional meet-in-the-middle, phylogeny ancestor/descendant (`parent_of`, cycle-safe), Steiner-ish join (union of shortest paths to a seed) so hits return a **connected** explanation subgraph.

Caps: `max_nodes`, `max_depth`, `max_paths`.

## Write-back

Each agent round appends `.codeevolve/graph/decisions.jsonl` and `pivots.jsonl`. The next `parse_context` loads them.

## CLI

```powershell
python -m codeevolve graph --from-report .codeevolve/report.json --from-agent .codeevolve/agent --out graph.json
python -m codeevolve graph --from-agent .codeevolve/agent --search investigate --flow --traverse wave
python -m codeevolve graph --from-agent .codeevolve/agent --kernel investigate --flow
python -m codeevolve graph --from-report .codeevolve/report.json --search "architecture/api" --kind type
python -m codeevolve graph --from-report .codeevolve/report.json --family taxon
python -m codeevolve graph --from-agent .codeevolve/agent --pivot propose
python -m codeevolve graph --from-agent .codeevolve/agent --search TODO --precedent
python -m codeevolve graph --from-report .codeevolve/report.json --previous old.json --delta --surface
```

Defaults: `.codeevolve/report.json` and/or `.codeevolve/agent` when present.

## MCP

`context_graph` with `from_report`, `from_agent`, `search`, `flow`, `kernel`, `kind`, `family`, `pivot`, `precedent`, `previous`, `delta`, `surface`, `traverse`, `depth`, `limit`.

## Agent tool

`graph_search` (`query`, `flow`, `kernel`, `family`, `pivot`, `traverse`, `precedent`, `depth`) is on the default registry and on the `investigate` / `search` kernels. Use it at coding pivots to pull taxon + knowledge + prior decisions before proposing.

## Python

```python
from codeevolve.graph import (
    parse_context, query_context, search_graph, agentic_flow,
    family_slice, pivot_join, at_pivot, precedent_search,
    delta_detect, write_pivot, bfs_expand, shortest_path, wavefront,
)

g = parse_context(report=report, agent=run.to_dict(), agent_dir=".codeevolve/agent")
print(family_slice(g, "knowledge").kinds())
print(at_pivot(g, "propose"))
print(search_graph(g, "investigate", traverse="wave"))
print(agentic_flow(g, kernel="investigate")["summary"])
print(query_context(report=report, agent_dir=".codeevolve/agent", search="TODO", flow=True, family="decision"))
```

Do not claim chaos/Lyapunov or unpublished Precision@5 / MTT-surface metrics from this graph.
